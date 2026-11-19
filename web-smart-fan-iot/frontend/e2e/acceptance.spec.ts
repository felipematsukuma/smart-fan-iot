import { execFileSync } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { expect, test } from './fixtures';
import type { FrameReadyV2 } from '../src/lib/contracts-v2.generated';
import type { Command, Observation } from '../src/aiot/control-types';
import type { ModelRecord, Selection } from '../src/aiot/training-types';

const root = fileURLToPath(new URL('../../../', import.meta.url));
const docker = (...args: string[]) =>
  execFileSync('docker', args, {
    cwd: root,
    encoding: 'utf8',
    stdio: ['pipe', 'pipe', 'pipe'],
  }).trim();

// Explicit opt-in: runs real jobs, changes scenario and pauses the writer.
test('ensaio contínuo de um equipamento, com cenário fixo e restauração', async ({
  page,
}) => {
  test.skip(
    process.env.AIOT_ACCEPTANCE !== '1',
    'Use AIOT_ACCEPTANCE=1 conforme docs/cenario-demo.md',
  );
  test.setTimeout(1200000);
  page.setDefaultTimeout(15000);
  const started = new Date().toISOString();
  const resume = process.env.AIOT_ACCEPTANCE_RESUME;
  if (resume && !/^\d+$/.test(resume))
    throw new Error('Execução de retomada inválida.');
  const run = resume ?? Date.now().toString();
  const previous = resume
    ? JSON.parse(
        readFileSync(
          resolve(root, 'evidence/acceptance', run, 'result.json'),
          'utf8',
        ),
      )
    : null;
  const directory = resolve(
    root,
    'evidence/acceptance',
    run,
    ...(resume ? ['continuation'] : []),
  );
  mkdirSync(directory, { recursive: true });
  const override = resolve(directory, 'scenario.json');
  const report: Record<string, unknown> = {
    started,
    resumed_after_test_locator_failure: resume ?? null,
    previous_steps: previous?.steps ?? [],
    uninterrupted_sequence: !resume,
    base:
      execFileSync('git', ['rev-parse', 'HEAD'], {
        cwd: root,
        encoding: 'utf8',
      }).trim() + '+working-tree',
    steps: [],
    semantic_review: 'partial_known_fidelity_limitation_no_model_reevaluation',
    scenario: {
      seed: 42,
      rate_per_operating_hour: 12,
      health_raise: 90,
      health_clear: 95,
      rul_raise_hours: 1,
      rul_clear_hours: 2,
      bad_samples: 3,
      good_samples: 10,
    },
  };
  const steps = report.steps as string[];
  const complete = (message: string) => {
    steps.push(message);
    writeFileSync(
      resolve(directory, 'progress.json'),
      JSON.stringify({ at: new Date().toISOString(), steps }, null, 2),
    );
    console.log(message);
  };
  const frames: FrameReadyV2[] = [];
  let token = '';
  let savedRule: { configuration: Record<string, unknown> } | undefined;
  let simulatorChanged = false;
  let manualChanged = false;
  let errors = 0;
  let injectedAt = '';
  page.on('pageerror', () => errors++);
  page.on('websocket', (socket) =>
    socket.on('framereceived', ({ payload }) => {
      try {
        const packet = JSON.parse(payload.toString());
        if (packet.tipo === 'frame.ready' && packet.dispositivo === 'ac_01')
          frames.push(packet);
      } catch {
        /* Non-domain control packets are ignored. */
      }
    }),
  );
  const headers = () => ({
    Authorization: `Bearer ${token}`,
    Origin: 'http://127.0.0.1:8080',
  });
  const get = async (path: string) => {
    const response = await page.request.get(`/api/v1${path}`, {
      headers: headers(),
    });
    expect(response.status()).toBe(200);
    return response.json();
  };
  const scenario = (kind: 'healthy' | 'mechanical_wear') => {
    writeFileSync(
      override,
      JSON.stringify({
        services: {
          'volume-init': {
            volumes: [
              {
                type: 'volume',
                source: 'demo_spool',
                target: '/vol/simulator',
              },
            ],
          },
          simulator: {
            environment: {
              SIM_SCENARIO: kind,
              SIM_INITIAL_DAMAGE: '0',
              SIM_DAMAGE_RATE: '12',
            },
            volumes: [
              { type: 'volume', source: 'demo_spool', target: '/data' },
            ],
          },
        },
        volumes: { demo_spool: { name: `smartfan_demo_${run}` } },
      }),
    );
    return ['compose', '-f', resolve(root, 'compose.yaml'), '-f', override];
  };
  async function login(username: string, password: string) {
    await page.goto('/entrar');
    await page.getByLabel('Usuário', { exact: true }).fill(username);
    try {
      await page.getByLabel('Senha', { exact: true }).fill(password);
    } catch {
      throw new Error('Não foi possível preencher a credencial privada.');
    }
    await page.getByRole('button', { name: 'Entrar', exact: true }).click();
    await expect(
      page.getByRole('link', { name: 'Visão geral', exact: true }),
    ).toBeVisible();
    await page.getByLabel('Equipamento', { exact: true }).selectOption('ac_01');
  }
  const adminPassword = readFileSync(
    process.env.AIOT_TEST_PASSWORD_FILE ??
      resolve(root, 'secrets/initial_admin_password'),
    'utf8',
  ).trim();
  const rolePasswords = {
    operador: readFileSync(
      resolve(root, 'secrets/initial_operator_password'),
      'utf8',
    ).trim(),
    visualizador: readFileSync(
      resolve(root, 'secrets/initial_viewer_password'),
      'utf8',
    ).trim(),
  };
  try {
    const auth = await page.request.post('/api/v1/auth/login', {
      data: { username: 'admin', password: adminPassword },
    });
    expect(auth.status()).toBe(200);
    token = (await auth.json()).access_token;
    for (const [username, password] of Object.entries(rolePasswords)) {
      const access = await page.request.post('/api/v1/auth/login', {
        data: { username, password },
      });
      expect(access.status(), `Acesso prévio: ${username}`).toBe(200);
      const roleToken = (await access.json()).access_token;
      const me = await page.request.get('/api/v1/auth/me', {
        headers: { Authorization: `Bearer ${roleToken}` },
      });
      expect((await me.json()).role).toBe(username);
    }
    report.original_control = await get('/devices/ac_01/control');
    expect((report.original_control as Observation).fresh).toBe(true);
    report.original_selection = (await get('/models?limit=1')).selection;
    report.original_rule = await get('/devices/ac_01/rule');
    savedRule = await get('/devices/ac_01/predictive-rule');
    report.original_predictive_rule = savedRule;
    writeFileSync(
      resolve(directory, 'before.json'),
      JSON.stringify(report, null, 2),
    );
    if (!resume) {
      docker('compose', 'stop');
      docker('compose', 'up', '-d', '--wait', '--wait-timeout', '180');
      const startup = docker('compose', 'ps', '--format', 'json')
        .split(/\r?\n/)
        .filter(Boolean)
        .map((row) => JSON.parse(row));
      expect(startup).toHaveLength(13);
      expect(startup.every((row) => row.Health === 'healthy')).toBe(true);
      report.startup = startup.map((row) => ({
        service: row.Service,
        health: row.Health,
      }));
      complete('1: parada normal e subida pelo Compose; 13 serviços saudáveis');
    }
    const configured = await page.request.patch(
      '/api/v1/devices/ac_01/predictive-rule',
      {
        headers: headers(),
        data: {
          expected_revision: (savedRule as unknown as { revision: number })
            .revision,
          configuration: {
            enabled: true,
            health_raise: 90,
            health_clear: 95,
            rul_raise_hours: 1,
            rul_clear_hours: 2,
            bad_samples: 3,
            good_samples: 10,
          },
        },
      },
    );
    expect(configured.status()).toBe(200);
    report.scenario_revision = (await configured.json()).revision;
    simulatorChanged = true;
    docker('compose', 'stop', 'simulator');
    const args = scenario('healthy');
    docker(...args, 'run', '--rm', '--no-deps', 'volume-init');
    docker(...args, 'up', '-d', '--no-deps', 'simulator');
    report.configuration_fixed_at = new Date().toISOString();
    await expect
      .poll(
        async () => {
          const current = (await get('/devices/ac_01/control')) as Observation;
          return (
            current.fresh &&
            current.observation !== null &&
            Date.parse(current.observation.sampled_at) >=
              Date.parse(String(report.configuration_fixed_at))
          );
        },
        { timeout: 20000 },
      )
      .toBe(true);

    let generation: { dataset_id: string };
    if (!resume) {
      const ps = docker('compose', 'ps', '--format', 'json')
        .split('\n')
        .map((row) => JSON.parse(row));
      await expect
        .poll(
          () =>
            docker('compose', 'ps', '--format', '{{.Health}}')
              .split('\n')
              .filter((value) => value === 'healthy').length,
          { timeout: 30000 },
        )
        .toBe(13);
      report.services = ps.map((row) => row.Service);
      for (const role of ['visualizador', 'operador']) {
        await login(role, rolePasswords[role as keyof typeof rolePasswords]);
        if (role === 'visualizador')
          await expect(
            page.getByRole('button', {
              name: 'Ligar ventilador',
              exact: true,
            }),
          ).toHaveCount(0);
        else
          await expect(
            page.getByRole('button', {
              name: 'Ligar ventilador',
              exact: true,
            }),
          ).toBeVisible();
        await page.getByRole('button', { name: 'Sair', exact: true }).click();
      }
      await login('admin', adminPassword);
      complete(
        '2: três contas existentes autenticadas no navegador; comandos disponíveis somente ao operador/administrador',
      );
      await expect
        .poll(() => frames.length, { timeout: 20000 })
        .toBeGreaterThan(0);
      complete('3: telemetria MQTT→AMQP→Influx→IA→WS recebida');
      expect((await page.request.get('/api/v1/docs')).status()).toBe(200);
      complete('4: documentação FastAPI HTTP 200');

      await page.getByRole('link', { name: 'Mensageria', exact: true }).click();
      await expect(
        page.getByRole('heading', { name: 'Mensagens recentes', exact: true }),
      ).toBeVisible();
      const queue = page.locator('[data-queue="q.telemetry.writer"]');
      try {
        docker('compose', 'stop', 'writer');
        await expect(queue).toHaveAttribute('data-consumers', '0', {
          timeout: 20000,
        });
        await expect
          .poll(async () => Number(await queue.getAttribute('data-ready')), {
            timeout: 20000,
          })
          .toBeGreaterThan(0);
      } finally {
        docker('compose', 'start', 'writer');
      }
      await expect(queue).toHaveAttribute('data-ready', '0', {
        timeout: 25000,
      });
      await expect(queue).toHaveAttribute('data-consumers', '1', {
        timeout: 20000,
      });
      complete('5: writer parado acumula; retomado drena; prévias visíveis');
      const history = await get('/devices/ac_01/metrics?hours=1');
      expect(
        history.chart.some(
          (point: { power_w: number | null }) => point.power_w !== null,
        ),
      ).toBe(true);
      report.history = { points: history.chart.length, energy: history.energy };
      const sourceEvent = frames.at(-1)!.conteudo.source_event_id;
      expect(sourceEvent).toMatch(/^[a-f0-9-]{36}$/i);
      expect(
        Number(
          docker(
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
            `SELECT count(*) FROM transport.inbox WHERE owner='writer' AND event_id='${sourceEvent}'::uuid AND state='completed';`,
          ),
        ),
      ).toBe(1);
      report.persisted_source_event = sourceEvent;
      report.postgres_devices = Number(
        docker(
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
          'SELECT count(*) FROM app.device_registry;',
        ),
      );
      complete('6: histórico Influx via API e cadastro PostgreSQL consultados');
      await page
        .getByRole('link', { name: 'Visão geral', exact: true })
        .click();
      await page
        .getByLabel('Equipamento', { exact: true })
        .selectOption('ac_01');
      const metrics = page.getByTestId('live-metrics');
      const source = await metrics.getAttribute('data-source-id');
      await expect
        .poll(() => metrics.getAttribute('data-source-id'), { timeout: 15000 })
        .not.toBe(source);
      complete('7: dashboard atualiza fonte por WS');
      for (const name of [
        'Desligar ventilador',
        'Ligar ventilador',
        'Liberar automático',
      ]) {
        const button = page.getByRole('button', { name, exact: true });
        await expect(button).toBeEnabled({ timeout: 15000 });
        const response = page.waitForResponse(
          (r) =>
            r.url().endsWith('/api/v1/devices/ac_01/commands') &&
            r.request().method() === 'POST',
        );
        manualChanged = true;
        await button.click();
        const accepted = await response;
        expect(accepted.status()).toBe(202);
        const command = (await accepted.json()) as Command;
        await expect(
          page.locator(`[data-command-id="${command.id}"]`),
        ).toHaveAttribute('data-command-status', 'confirmed', {
          timeout: 20000,
        });
        const expectedOn =
          name === 'Desligar ventilador'
            ? false
            : name === 'Ligar ventilador'
              ? true
              : null;
        await expect
          .poll(
            async () => {
              const current = (await get(
                '/devices/ac_01/control',
              )) as Observation;
              if (
                !current.fresh ||
                !current.observation ||
                Date.parse(current.observation.sampled_at) <
                  Date.parse(command.created_at)
              )
                return false;
              return expectedOn === null
                ? current.observation.mode === 'auto'
                : current.observation.telemetry.actuators.condenser_fan_on ===
                    expectedOn;
            },
            { timeout: 20000 },
          )
          .toBe(true);
        report['command_' + name] = {
          command: await get('/commands/' + command.id),
          physical_observation: await get('/devices/ac_01/control'),
        };
      }
      manualChanged = false;
      complete(
        '8: três comandos pelo dashboard confirmados pelo dispositivo; automático liberado',
      );
      await page
        .getByRole('link', { name: 'Interfaces locais', exact: true })
        .click();
      await expect(
        page.getByRole('link', { name: /Abrir RabbitMQ/ }),
      ).toHaveAttribute('href', 'http://127.0.0.1:15672');
      await page
        .getByRole('link', { name: 'Dados sintéticos', exact: true })
        .click();
      await page
        .getByRole('button', { name: 'Gerar dataset', exact: true })
        .click();
      await expect(page.locator('.job-detail')).toHaveAttribute(
        'data-job-status',
        'completed',
        { timeout: 60000 },
      );
      report.dataset_job = await page
        .locator('.job-detail')
        .getAttribute('data-job-id');
      generation = await get('/jobs/' + report.dataset_job);
      report.generation = generation;
      const generatedDataset = await get('/datasets/' + generation.dataset_id);
      expect(generatedDataset.rows).toBeGreaterThanOrEqual(1000000);
      report.dataset = generatedDataset;
      complete('9: dataset padrão 1.036.800 vetores gerado pela UI');
    } else {
      expect(previous?.generation?.status).toBe('completed');
      generation = previous.generation;
      report.generation = generation;
      report.dataset = previous.dataset;
      await login('admin', adminPassword);
      await page
        .getByLabel('Equipamento', { exact: true })
        .selectOption('ac_01');
      const release = page.getByRole('button', {
        name: 'Liberar automático',
        exact: true,
      });
      await expect(release).toBeEnabled();
      await release.click();
      await expect
        .poll(
          async () => (await get('/devices/ac_01/control')).observation?.mode,
          { timeout: 20000 },
        )
        .toBe('auto');
    }
    await page.getByRole('link', { name: 'Treinamento', exact: true }).click();
    await page
      .getByRole('combobox', { name: 'Dataset completo', exact: true })
      .selectOption(generation.dataset_id);
    await page
      .getByRole('button', { name: 'Treinar modelos', exact: true })
      .click();
    await expect(page.locator('.model-detail')).toHaveAttribute(
      'data-model-status',
      'completed',
      { timeout: 180000 },
    );
    await expect(
      page.getByRole('heading', { name: 'Previsto × real', exact: true }),
    ).toBeVisible();
    report.trained_version = await page
      .locator('.model-detail')
      .getAttribute('data-model-version');
    const candidate = (await get(
      '/models/' + report.trained_version,
    )) as ModelRecord;
    expect(candidate.dataset_id).toBe(generation.dataset_id);
    for (const target of ['health_score', 'rul_calendar_hours'] as const)
      for (const evaluated of ['test', 'test_baseline'] as const)
        for (const metric of ['mae', 'rmse', 'r2'] as const)
          expect(
            Number.isFinite(
              candidate.report?.targets[target][evaluated][metric],
            ),
          ).toBe(true);
    report.candidate = candidate;
    const selection = (await get('/models?limit=1')).selection as Selection;
    expect(selection.active_version).toBe(
      (report.original_selection as Selection).active_version,
    );
    const reasons =
      candidate.promotion_reasons ?? candidate.report?.promotion_reasons ?? [];
    report.promotion = {
      reasons,
      selection,
      promoted: false,
      note: 'Conclusão não implica ativação; candidato não promovido para preservar seleção original.',
    };
    if (reasons.length)
      await expect(
        page.getByRole('button', { name: 'Promover candidato', exact: true }),
      ).toBeDisabled();
    await expect
      .poll(
        async () =>
          (await get('/devices/ac_01/commands?limit=100')).items.some(
            (command: Command) =>
              command.producer === 'control' &&
              command.status === 'confirmed' &&
              command.created_at >= String(report.configuration_fixed_at),
          ),
        { timeout: 240000, intervals: [2000] },
      )
      .toBe(true);
    const automaticCommands = (
      await get('/devices/ac_01/commands?limit=100')
    ).items.filter(
      (command: Command) =>
        command.producer === 'control' &&
        command.status === 'confirmed' &&
        command.created_at >= String(report.configuration_fixed_at),
    );
    report.automatic_commands = automaticCommands;
    await expect
      .poll(
        () =>
          frames.some(
            (frame) =>
              frame.timestamp >= String(report.configuration_fixed_at) &&
              frame.conteudo.telemetry.actuators.compressor_on,
          ),
        { timeout: 20000 },
      )
      .toBe(true);
    report.automatic_observation = await get('/devices/ac_01/control');
    complete(
      '10: treino assíncrono e métricas reais; nenhuma promoção forçada',
    );

    // Keep the healthy scenario until any pre-existing alert clears naturally.
    await expect
      .poll(
        async () =>
          (await get('/alerts?device=ac_01&status=active')).items.length,
        { timeout: 180000, intervals: [2000] },
      )
      .toBe(0);
    report.healthy_hysteresis = docker(
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
      "SELECT row_to_json(s) FROM app.predictive_states s WHERE device_id='ac_01';",
    );
    const before = await get('/alerts?device=ac_01&status=active');
    const oldAlerts = new Set(
      before.items.map((item: { id: string }) => item.id),
    );
    injectedAt = new Date().toISOString();
    docker(
      ...scenario('mechanical_wear'),
      'up',
      '-d',
      '--no-deps',
      'simulator',
    );
    await page.getByRole('link', { name: 'Insights', exact: true }).click();
    await page
      .getByLabel('Equipamento dos insights', { exact: true })
      .selectOption('ac_01');
    await expect
      .poll(
        async () => {
          const alerts = await get('/alerts?device=ac_01&status=active');
          return alerts.items.some(
            (item: { id: string; raised_at: string }) =>
              !oldAlerts.has(item.id) && item.raised_at >= injectedAt,
          );
        },
        { timeout: 480000, intervals: [2000] },
      )
      .toBe(true);
    const valid = frames.filter(
      (frame) =>
        frame.timestamp >= injectedAt &&
        frame.conteudo.insight.status === 'valid',
    );
    expect(valid.length).toBeGreaterThanOrEqual(3);
    const first = valid[0]!,
      last = valid[valid.length - 1]!;
    expect(
      last.conteudo.telemetry.readings.vibration_rms_mm_s!,
    ).toBeGreaterThan(first.conteudo.telemetry.readings.vibration_rms_mm_s!);
    report.failure = {
      injected_at: injectedAt,
      valid_frames: valid.length,
      first,
      last,
      alerts: (await get('/alerts?device=ac_01&status=active')).items,
    };
    report.raised_hysteresis = docker(
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
      "SELECT row_to_json(s) FROM app.predictive_states s WHERE device_id='ac_01';",
    );
    await expect(page.getByTestId('insight-health')).not.toHaveText('—');
    await page.getByRole('link', { name: 'Cena 3D', exact: true }).click();
    await page
      .getByLabel('Equipamento na cena', { exact: true })
      .selectOption('ac_01');
    await expect(page.locator('.scene-card')).toHaveAttribute(
      'data-equipment-color',
      /#d38a29|#d45c52/,
      { timeout: 15000 },
    );
    await page.screenshot({
      path: resolve(directory, 'scene.png'),
      fullPage: true,
    });
    complete(
      '11: desgaste progressivo, nova transição por histerese e cor 3D via WS',
    );
    await page
      .getByRole('link', { name: 'Assistente local', exact: true })
      .click();
    await page
      .getByLabel('Equipamento da conversa', { exact: true })
      .selectOption('ac_01');
    await page
      .getByLabel('Pergunta sobre o equipamento', { exact: true })
      .fill(
        'O que significa RUL e que cuidado exige o alerta ativo do compressor?',
      );
    const assistantResponse = page.waitForResponse(
      (r) =>
        r.url().endsWith('/api/v1/assistant/chat') &&
        r.request().method() === 'POST',
    );
    const assistantStarted = Date.now();
    await page
      .getByRole('button', { name: 'Perguntar ao assistente', exact: true })
      .click();
    await expect(page.locator('.turn').last()).toHaveAttribute(
      'data-turn-outcome',
      'completed',
      { timeout: 95000 },
    );
    await expect(page.getByTestId('assistant-answer')).not.toBeEmpty();
    await page
      .getByText('Dados estruturados desta resposta', { exact: true })
      .click();
    await page
      .getByText('Referências técnicas do resumo', { exact: true })
      .click();
    await expect(page.locator('.turn details pre')).toContainText(
      'definitions',
    );
    report.assistant_text = await page
      .getByTestId('assistant-answer')
      .innerText();
    const chatResponse = await assistantResponse;
    expect(chatResponse.status()).toBe(200);
    // Chromium need not retain a consumed fetch/SSE body. Use the completed
    // UI turn plus the durable request record, without a second LLM request.
    const assistantRecord = JSON.parse(
      docker(
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
        `SELECT row_to_json(s) FROM (SELECT id,outcome,first_token_ms,duration_ms,tokens,reason_code FROM app.assistant_requests WHERE created_at >= '${new Date(assistantStarted).toISOString()}'::timestamptz ORDER BY created_at DESC LIMIT 1) s;`,
      ),
    );
    expect(assistantRecord.outcome).toBe('completed');
    expect(assistantRecord.first_token_ms).toBeGreaterThanOrEqual(0);
    await page.getByText('Detalhes da geração', { exact: true }).click();
    await expect(page.locator('.turn').last()).toContainText(
      'Primeiro fragmento:',
    );
    report.assistant_integration = {
      request: assistantRecord,
      browser_elapsed_ms: Date.now() - assistantStarted,
      generated_text_is_not_authoritative: true,
      semantic_fidelity: 'partial_previously_documented_not_requalified',
      structured_context: JSON.parse(
        await page.locator('.turn details pre').innerText(),
      ),
    };
    await page.screenshot({
      path: resolve(directory, 'assistant.png'),
      fullPage: true,
    });
    complete(
      '12: Ollama real respondeu; contexto estruturado separado; fidelidade semântica permanece parcial',
    );
    expect(errors).toBe(0);
    report.functional_passed = true;
  } catch (error) {
    report.functional_passed = false;
    report.failure_message =
      error instanceof Error ? error.message : 'Falha não identificada';
    throw error;
  } finally {
    const cleanup: Record<string, unknown> = {};
    try {
      docker('compose', 'start', 'writer');
      cleanup.writer_resumed = true;
    } catch {
      cleanup.writer_resumed = false;
    }
    if (simulatorChanged) {
      try {
        docker(
          'compose',
          'up',
          '-d',
          '--no-deps',
          '--force-recreate',
          'simulator',
        );
        cleanup.simulator_restored = true;
      } catch {
        cleanup.simulator_restored = false;
      }
    }
    if (savedRule && token) {
      try {
        const current = await get('/devices/ac_01/predictive-rule');
        if (
          JSON.stringify(current.configuration) !==
          JSON.stringify(savedRule.configuration)
        ) {
          const restored = await page.request.patch(
            '/api/v1/devices/ac_01/predictive-rule',
            {
              headers: headers(),
              data: {
                expected_revision: current.revision,
                configuration: savedRule.configuration,
              },
            },
          );
          expect(restored.status()).toBe(200);
        }
        const restoredRule = await get('/devices/ac_01/predictive-rule');
        expect(restoredRule.configuration).toEqual(savedRule.configuration);
        cleanup.rule_restored = true;
        report.final_predictive_rule = restoredRule;
      } catch {
        cleanup.rule_restored = false;
      }
    }
    if (manualChanged && token) {
      try {
        const released = await page.request.post(
          '/api/v1/devices/ac_01/commands',
          {
            headers: { ...headers(), 'Idempotency-Key': randomUUID() },
            data: { action: 'release_auto' },
          },
        );
        expect(released.status()).toBe(202);
        await expect
          .poll(
            async () => (await get('/devices/ac_01/control')).observation?.mode,
            { timeout: 30000 },
          )
          .toBe('auto');
        cleanup.automatic_restored = true;
      } catch {
        cleanup.automatic_restored = false;
      }
    }
    try {
      await expect
        .poll(
          () =>
            docker('compose', 'ps', '--format', '{{.Health}}')
              .split(/\r?\n/)
              .filter((value) => value === 'healthy').length,
          { timeout: 60000 },
        )
        .toBe(13);
      cleanup.services_healthy = true;
      report.final_selection = (await get('/models?limit=1')).selection;
      report.final_control = await get('/devices/ac_01/control');
    } catch {
      cleanup.services_healthy = false;
    }
    report.cleanup = cleanup;
    report.finished = new Date().toISOString();
    report.frames_received = frames.length;
    report.original_spool_preserved = true;
    report.page_errors = errors;
    writeFileSync(
      resolve(directory, 'frames.json'),
      JSON.stringify(frames, null, 2),
    );
    writeFileSync(
      resolve(directory, 'result.json'),
      JSON.stringify(report, null, 2),
    );
    console.log(
      JSON.stringify({
        evidence: directory,
        functional_passed: report.functional_passed ?? false,
        steps: steps.length,
        frames: frames.length,
        cleanup,
      }),
    );
    expect(Object.values(cleanup).every((value) => value === true)).toBe(true);
  }
});
