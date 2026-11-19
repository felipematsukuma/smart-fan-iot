import { execFileSync } from 'node:child_process';
import { readFileSync, mkdirSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { randomUUID } from 'node:crypto';
import { test, expect } from './fixtures';
import type { FrameReadyV2 } from '../src/lib/contracts-v2.generated';
import type { Command, Observation } from '../src/aiot/control-types';
import type { ModelRecord, Selection } from '../src/aiot/training-types';
const root = resolve('../..');
const docker = (...args: string[]) =>
  execFileSync('docker', args, {
    cwd: root,
    encoding: 'utf8',
    stdio: ['pipe', 'pipe', 'pipe'],
  }).trim();
test('consolidação integrada: um equipamento, artefatos existentes e restauração', async ({
  page,
}) => {
  test.skip(
    process.env.AIOT_CONSOLIDATION !== '1',
    'Opt-in: atua no ventilador e interrompe brevemente o writer; preserva dados e modelos.',
  );
  test.setTimeout(300000);
  page.setDefaultTimeout(15000);
  const output = resolve(root, 'evidence/consolidation', Date.now().toString());
  mkdirSync(output, { recursive: true });
  const report: Record<string, unknown> = {
    started: new Date().toISOString(),
    scope: 'ac_01, artefatos existentes, sem LLM/treino/geração/falha injetada',
    steps: [],
    llm: 'partial_semantic_fidelity_not_retested',
  };
  const steps = report.steps as string[];
  const frames: FrameReadyV2[] = [];
  const commands: Command[] = [];
  let token = '';
  let writerStopped = false;
  let changed = false;
  let cleanupError = '';
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('websocket', (socket) =>
    socket.on('framereceived', ({ payload }) => {
      try {
        const item = JSON.parse(payload.toString());
        if (item.tipo === 'frame.ready' && item.dispositivo === 'ac_01') {
          frames.push(item);
          if (frames.length > 1000) frames.shift();
        }
      } catch {
        /* controls */
      }
    }),
  );
  const headers = () => ({
    Authorization: `Bearer ${token}`,
    Origin: 'http://127.0.0.1:8080',
  });
  const get = async (path: string) => {
    const response = await page.request.get('/api/v1' + path, {
      headers: headers(),
    });
    expect(response.status()).toBe(200);
    return response.json();
  };
  const state = () => get('/devices/ac_01/control') as Promise<Observation>;
  try {
    const services = docker('compose', 'ps', '--format', 'json')
      .split(/\r?\n/)
      .filter(Boolean)
      .map((line) => JSON.parse(line));
    expect(services).toHaveLength(13);
    expect(services.every((service) => service.Health === 'healthy')).toBe(
      true,
    );
    steps.push('13 serviços permanentes saudáveis');
    await page.goto('/entrar');
    await page.getByLabel('Usuário', { exact: true }).fill('admin');
    try {
      await page
        .getByLabel('Senha', { exact: true })
        .fill(
          readFileSync(
            resolve(root, 'secrets/initial_admin_password'),
            'utf8',
          ).trim(),
        );
    } catch {
      throw new Error('Não foi possível preencher a credencial local.');
    }
    const login = page.waitForResponse(
      (r) =>
        r.url().endsWith('/api/v1/auth/login') &&
        r.request().method() === 'POST',
    );
    await page.getByLabel('Senha', { exact: true }).press('Enter');
    token = (await (await login).json()).access_token;
    await expect(
      page.getByRole('heading', { name: 'Visão geral', exact: true }),
    ).toBeVisible();
    await page.getByLabel('Equipamento', { exact: true }).selectOption('ac_01');
    const original = await state();
    expect(original.fresh).toBe(true);
    expect(original.observation?.mode).toBe('auto');
    report.original_control = original;
    steps.push(
      'login real e operação automática existente preservada como referência',
    );
    await expect
      .poll(() => frames.length, { timeout: 20000 })
      .toBeGreaterThan(0);
    const valid = frames.at(-1)!;
    expect(['valid', 'inactive', 'warming_up', 'insufficient_data']).toContain(
      valid.conteudo.insight.status,
    );
    if (valid.conteudo.insight.status === 'inactive') {
      expect(valid.conteudo.telemetry.actuators.compressor_on).toBe(false);
      expect(valid.conteudo.insight.health_score).toBeNull();
      expect(valid.conteudo.insight.rul_calendar_hours).toBeNull();
    }
    report.prediction = {
      at: valid.timestamp,
      source: valid.conteudo.source_event_id,
      ...valid.conteudo.insight,
    };
    const registry = (await get('/models?limit=50')) as {
      items: ModelRecord[];
      selection: Selection;
    };
    const active = (await get(
      '/models/' + registry.selection.active_version,
    )) as ModelRecord;
    if (valid.conteudo.insight.model_version)
      expect(valid.conteudo.insight.model_version).toBe(active.version);
    const previous = await get(
      '/devices/ac_01/insights/history?hours=1&limit=500',
    );
    const historical = previous.items.find(
      (item: { status: string; model_version: string }) =>
        item.status === 'valid' && item.model_version === active.version,
    );
    expect(historical).toBeTruthy();
    report.historical_prediction = {
      sampled_at: historical.sampled_at,
      model_version: historical.model_version,
      health_score: historical.health_score,
      rul_calendar_hours: historical.rul_calendar_hours,
      evidence: 'historical_not_new_live_prediction',
    };
    expect(active.approved).toBe(true);
    for (const target of ['health_score', 'rul_calendar_hours'] as const)
      for (const evaluation of ['test', 'test_baseline'] as const)
        for (const metric of ['mae', 'rmse', 'r2'] as const)
          expect(
            Number.isFinite(active.report?.targets[target][evaluation][metric]),
          ).toBe(true);
    report.model = {
      version: active.version,
      selection: registry.selection,
      dataset_id: active.dataset_id,
      approved: active.approved,
    };
    const dataset = await get('/datasets/' + active.dataset_id);
    expect(dataset.status).toBe('completed');
    expect(dataset.rows).toBeGreaterThanOrEqual(1000000);
    report.reused_dataset = { id: dataset.id, rows: dataset.rows };
    const metrics = await get('/devices/ac_01/metrics?hours=1');
    expect(
      metrics.chart.some(
        (point: { power_w: number | null }) => point.power_w !== null,
      ),
    ).toBe(true);
    report.history = {
      points: metrics.chart.length,
      coverage_fraction: metrics.energy.coverage_fraction,
    };
    // Read-only proof that this frame's original telemetry passed through the writer inbox.
    const source = valid.conteudo.source_event_id;
    expect(source).toMatch(/^[a-f0-9-]{36}$/i);
    const persisted = docker(
      'compose',
      'exec',
      '-T',
      'postgres',
      'psql',
      '-U',
      'smartfan_bootstrap',
      '-d',
      'smartfan',
      '-tAc',
      `SELECT count(*) FROM transport.inbox WHERE owner='writer' AND event_id='${source}'::uuid AND state='completed';`,
    );
    expect(Number(persisted)).toBe(1);
    steps.push(
      'MQTT→gateway→RabbitMQ→writer/Influx→inferência→WebSocket: leitura nova, modelo ativo e histórico reais',
    );
    const dashboard = page.getByTestId('live-metrics');
    const before = await dashboard.getAttribute('data-source-id');
    await expect
      .poll(() => dashboard.getAttribute('data-source-id'))
      .not.toBe(before);
    await page.getByRole('link', { name: 'Mensageria', exact: true }).click();
    const queue = page.locator('[data-queue="q.telemetry.writer"]');
    await expect(queue).toHaveAttribute('data-consumers', '1');
    try {
      writerStopped = true;
      docker('compose', 'stop', 'writer');
      await expect(queue).toHaveAttribute('data-consumers', '0', {
        timeout: 20000,
      });
      await expect
        .poll(async () => Number(await queue.getAttribute('data-ready')), {
          timeout: 15000,
        })
        .toBeGreaterThan(0);
      report.backlog = Number(await queue.getAttribute('data-ready'));
    } finally {
      docker('compose', 'start', 'writer');
      writerStopped = false;
    }
    await expect(queue).toHaveAttribute('data-ready', '0', { timeout: 30000 });
    await expect(queue).toHaveAttribute('data-consumers', '1', {
      timeout: 20000,
    });
    steps.push(
      'Mensageria real: consumidor ausente, acúmulo e drenagem, sem remover mensagens',
    );
    await page.getByRole('link', { name: 'Visão geral', exact: true }).click();
    await page.getByLabel('Equipamento', { exact: true }).selectOption('ac_01');
    for (const [label, action, on] of [
      ['Desligar ventilador', 'fan_off', false],
      ['Ligar ventilador', 'fan_on', true],
      ['Liberar automático', 'release_auto', null],
    ] as const) {
      const button = page.getByRole('button', { name: label, exact: true });
      await expect(button).toBeEnabled();
      const response = page.waitForResponse(
        (r) =>
          r.url().endsWith('/api/v1/devices/ac_01/commands') &&
          r.request().method() === 'POST',
      );
      changed = true;
      await button.click();
      const request = await response;
      expect(request.status()).toBe(202);
      const command = (await request.json()) as Command;
      commands.push(command);
      await expect(
        page.locator(`[data-command-id="${command.id}"]`),
      ).toHaveAttribute('data-command-status', 'confirmed', { timeout: 20000 });
      await expect
        .poll(
          async () => {
            const current = await state();
            if (
              !current.fresh ||
              !current.observation ||
              Date.parse(current.observation.sampled_at) <
                Date.parse(command.created_at)
            )
              return false;
            return on === null
              ? current.observation.mode === 'auto'
              : current.observation.telemetry.actuators.condenser_fan_on === on;
          },
          { timeout: 20000 },
        )
        .toBe(true);
      if (on !== null)
        await expect
          .poll(
            () =>
              frames.some(
                (frame) =>
                  Date.parse(frame.timestamp) >=
                    Date.parse(command.created_at) &&
                  frame.conteudo.telemetry.actuators.condenser_fan_on === on,
              ),
            { timeout: 20000 },
          )
          .toBe(true);
      expect(
        (await get('/devices/ac_01/commands?limit=10')).items.find(
          (item: Command) => item.id === command.id,
        ).ack_event_id,
      ).toBeTruthy();
      report['command_' + action] = {
        id: command.id,
        physical_observation_confirmed: true,
      };
    }
    changed = false;
    steps.push(
      'Web→RabbitMQ→MQTT→simulador: três comandos confirmados e estados físicos posteriores observados; automático restaurado',
    );
    await page
      .getByRole('link', { name: 'Dados sintéticos', exact: true })
      .click();
    const existingGeneration = page
      .locator('.jobs tbody tr')
      .filter({ hasText: 'Concluído' })
      .first();
    await existingGeneration
      .getByRole('button', { name: 'Ver geração', exact: true })
      .click();
    await expect(
      page.getByRole('heading', { name: 'Resultado gerado', exact: true }),
    ).toBeVisible();
    await page.getByRole('link', { name: 'Treinamento', exact: true }).click();
    const existingModel = page
      .locator('.registry tbody tr')
      .filter({ hasText: active.version.slice(0, 8) });
    const modelRow = existingModel.filter({
      hasText: active.version.slice(-4),
    });
    while (
      !(await modelRow.count()) &&
      (await page
        .getByRole('button', { name: 'Mais modelos', exact: true })
        .isVisible())
    )
      await page
        .getByRole('button', { name: 'Mais modelos', exact: true })
        .click();
    await modelRow
      .getByRole('button', { name: 'Ver modelo', exact: true })
      .click();
    await expect(
      page.getByRole('heading', { name: 'Métricas por alvo', exact: true }),
    ).toBeVisible();
    await expect(page.locator('.metric-target')).toHaveCount(2);
    await expect(
      page.getByRole('heading', { name: 'Previsto × real', exact: true }),
    ).toBeVisible();
    steps.push(
      'dataset e modelo existentes consultados na UI, dois alvos e avaliações; sem jobs novos ou promoção',
    );
    await page.getByRole('link', { name: 'Insights', exact: true }).click();
    await page
      .getByLabel('Equipamento dos insights', { exact: true })
      .selectOption('ac_01');
    await expect(page.getByTestId('insight-status')).toBeVisible();
    await page.getByRole('link', { name: 'Cena 3D', exact: true }).click();
    await page
      .getByLabel('Equipamento na cena', { exact: true })
      .selectOption('ac_01');
    await expect(page.getByTestId('scene-status')).toHaveText('Dados recentes');
    await expect
      .poll(async () =>
        Number(
          await page.locator('.scene-card').getAttribute('data-geometries'),
        ),
      )
      .toBeGreaterThan(0);
    steps.push(
      'Insights e Cena recebem o fluxo real após os comandos; previsão pode reaquecer após o anticiclo',
    );
    await page.getByRole('link', { name: 'Auditoria', exact: true }).click();
    await expect(page.locator('[data-audit-id]').first()).toBeVisible();
    expect(
      (await get('/audit?limit=100')).items.some(
        (entry: { entity_id: string }) =>
          commands.some((command) => command.id === entry.entity_id),
      ),
    ).toBe(true);
    expect(errors).toEqual([]);
    await expect
      .poll(
        () =>
          docker('compose', 'ps', '--format', 'json')
            .split(/\r?\n/)
            .filter(Boolean)
            .map((line) => JSON.parse(line))
            .every((item) => item.Health === 'healthy'),
        { timeout: 30000, intervals: [1000] },
      )
      .toBe(true);
    report.errors = errors;
    report.result = 'passed';
  } catch (error) {
    report.result = 'failed';
    report.failure =
      error instanceof Error ? error.message : 'Falha não identificada';
    throw error;
  } finally {
    if (writerStopped) {
      try {
        docker('compose', 'start', 'writer');
      } catch {
        cleanupError = 'Não foi possível retomar writer.';
      }
    }
    if (changed && token) {
      try {
        const response = await page.request.post(
          '/api/v1/devices/ac_01/commands',
          {
            headers: { ...headers(), 'Idempotency-Key': randomUUID() },
            data: { action: 'release_auto' },
          },
        );
        expect(response.status()).toBe(202);
        await expect
          .poll(async () => (await state()).observation?.mode, {
            timeout: 20000,
          })
          .toBe('auto');
      } catch {
        cleanupError +=
          ' Não foi possível confirmar restauração do automático.';
      }
    }
    report.cleanup_error = cleanupError;
    report.finished = new Date().toISOString();
    report.frames_received = frames.length;
    report.final_services = docker('compose', 'ps', '--format', 'json')
      .split(/\r?\n/)
      .filter(Boolean)
      .map((line) => {
        const item = JSON.parse(line);
        return { service: item.Service, health: item.Health };
      });
    writeFileSync(
      resolve(output, 'result.json'),
      JSON.stringify(report, null, 2),
    );
    expect(cleanupError).toBe('');
  }
});
