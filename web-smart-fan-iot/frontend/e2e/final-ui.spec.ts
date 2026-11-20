import { readFileSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import type { Page } from '@playwright/test';
import { test, expect } from './fixtures';
import { verifyContrast } from './ui-contrast';
test.use({ hasTouch: true });
const evidence = resolve('../../evidence/ui-final');
mkdirSync(evidence, { recursive: true });
async function login(page: Page) {
  await page.goto('/entrar');
  await page.getByLabel('Usuário', { exact: true }).fill('admin');
  await page
    .getByLabel('Senha', { exact: true })
    .fill(
      readFileSync(
        resolve('../../secrets/initial_admin_password'),
        'utf8',
      ).trim(),
    );
  await page.getByLabel('Senha', { exact: true }).press('Enter');
  await expect(
    page.getByRole('heading', { name: 'Visão geral', exact: true }),
  ).toBeVisible();
}
async function visit(page: Page, name: string) {
  if (page.viewportSize()!.width < 1024)
    await page.getByRole('button', { name: 'Abrir navegação' }).click();
  await page.getByRole('link', { name, exact: true }).click();
  await expect(page.getByRole('heading', { name, exact: true })).toBeVisible();
}
async function capture(page: Page, name: string) {
  await expect(page.locator('.task-page h1').first()).toBeVisible();
  await expect
    .poll(() =>
      page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
    )
    .toBe(true);
  await verifyContrast(page, resolve(evidence, name + '-contrast.json'));
  await page.evaluate(() => scrollTo(0, 0));
  await page.screenshot({
    path: resolve(evidence, name + '.png'),
    fullPage: true,
  });
}
interface FixtureWindow {
  assistantEmit: (event: string, data: Record<string, unknown>) => void;
  assistantRequests: number;
}
async function fakeAssistant(page: Page) {
  await page.addInitScript(() => {
    const original = window.fetch.bind(window);
    const fixture = window as unknown as {
      assistantEmit: (event: string, data: Record<string, unknown>) => void;
      assistantRequests: number;
    };
    fixture.assistantRequests = 0;
    window.fetch = async (input, options) => {
      const path = new URL(
        typeof input === 'string'
          ? input
          : input instanceof URL
            ? input.href
            : input.url,
        location.href,
      ).pathname;
      if (path !== '/api/v1/assistant/chat') return original(input, options);
      fixture.assistantRequests++;
      let closed = false;
      const stream = new ReadableStream<Uint8Array>({
        start(controller) {
          fixture.assistantEmit = (event, data) => {
            if (closed) return;
            controller.enqueue(
              new TextEncoder().encode(
                `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`,
              ),
            );
            if (event === 'done' || event === 'error') {
              closed = true;
              controller.close();
            }
          };
          options?.signal?.addEventListener('abort', () => {
            if (!closed) {
              closed = true;
              controller.error(new DOMException('Cancelado', 'AbortError'));
            }
          });
        },
        cancel() {
          closed = true;
        },
      });
      return new Response(stream, {
        headers: { 'Content-Type': 'text/event-stream' },
      });
    };
  });
}
async function emit(
  page: Page,
  event: string,
  data: Record<string, unknown> = {},
) {
  await page.evaluate(
    ({ event, data }) =>
      (window as unknown as FixtureWindow).assistantEmit(event, data),
    { event, data },
  );
}
async function startQuestion(page: Page, text = 'Pergunta de fixture') {
  await page
    .getByLabel('Pergunta sobre o equipamento', { exact: true })
    .fill(text);
  await page
    .getByRole('button', { name: 'Perguntar ao assistente', exact: true })
    .click();
  await expect
    .poll(() =>
      page.evaluate(
        () => (window as unknown as FixtureWindow).assistantRequests,
      ),
    )
    .toBeGreaterThan(0);
}
const summary = {
  device: 'ac_01',
  utc: '2026-11-15T20:00:00Z',
  sample_utc: '2026-11-15T19:59:59Z',
  live: 'fresh',
  alerts: [],
  rul_unit: 'calendar_hours',
  prediction: {
    status: 'valid',
    model: 'fixture-v1',
    saude_compressor_percentual: 0,
    vida_util_restante_estimada_horas: 0,
  },
  model_metrics: {
    version: 'fixture-v1',
    status: 'test_synthetic',
    targets: {
      health_score: { unit: 'pontos', mae: 0, rmse: 1, r2: -0.2 },
      rul_calendar_hours: { unit: 'h', mae: 2, rmse: 3, r2: 0.8 },
    },
  },
};
test('fixture: estados, dados estruturados e Markdown seguro com capturas', async ({
  page,
}) => {
  await fakeAssistant(page);
  await login(page);
  await visit(page, 'Assistente local');
  await page
    .getByLabel('Equipamento da conversa', { exact: true })
    .selectOption('ac_01');
  await expect(page.locator('.assistant-warning')).toHaveCount(1);
  await startQuestion(page);
  await emit(page, 'meta', { state: 'queued', model: 'fixture-local' });
  await expect(page.getByText('Aguardando', { exact: true })).toBeVisible();
  await emit(page, 'meta', {
    state: 'warming',
    model: 'fixture-local',
    summary,
  });
  await expect(
    page.getByText('Carregando modelo', { exact: true }),
  ).toBeVisible();
  await emit(page, 'delta', {
    text: '**Resposta simulada para validar a interface.**\n\nConfira os dados estruturados abaixo. ![remota](https://example.com/fixture.png)',
  });
  await expect(
    page.getByText('Recebendo resposta', { exact: true }),
  ).toBeVisible();
  await emit(page, 'done', { first_token_ms: 1234 });
  await expect(page.locator('[data-turn-outcome="completed"]')).toBeVisible();
  await expect(
    page.getByLabel('Pergunta sobre o equipamento', { exact: true }),
  ).toHaveValue('');
  await page
    .getByText('Dados estruturados desta resposta', { exact: true })
    .click();
  await expect(page.locator('.assistant-data')).toContainText('0 %');
  await expect(page.locator('.assistant-data')).toContainText(
    '0 h de calendário',
  );
  await expect(page.locator('.assistant-data')).toContainText('fixture-v1');
  await expect(
    page.locator('.markdown script,.markdown img,.markdown iframe'),
  ).toHaveCount(0);
  await capture(page, 'fixture-assistant-desktop');
  await page.setViewportSize({ width: 390, height: 844 });
  // visualViewport resize updates the workbench asynchronously. Read both
  // rectangles in one frame, and require the composer to fit after resizing.
  await expect
    .poll(() =>
      page.evaluate(() => {
        const conversation = document
          .querySelector('.conversation')!
          .getBoundingClientRect();
        const form = document
          .querySelector('.question-form')!
          .getBoundingClientRect();
        return {
          overlaps: conversation.bottom > form.top,
          composerWithinViewport: form.top >= 0 && form.bottom <= innerHeight,
        };
      }),
    )
    .toEqual({ overlaps: false, composerWithinViewport: true });
  await capture(page, 'fixture-assistant-mobile');
  await page
    .getByText('Dados estruturados desta resposta', { exact: true })
    .click();
  await page
    .getByLabel('Pergunta sobre o equipamento', { exact: true })
    .focus();
  await page.setViewportSize({ width: 390, height: 390 });
  await expect(
    page.getByRole('button', { name: 'Perguntar ao assistente', exact: true }),
  ).toBeInViewport();
});
test('fixture: rolagem respeita leitura anterior, cancelamento, erro e indisponibilidade', async ({
  page,
}) => {
  await fakeAssistant(page);
  await login(page);
  await visit(page, 'Assistente local');
  await page
    .getByLabel('Equipamento da conversa', { exact: true })
    .selectOption('ac_01');
  await startQuestion(page);
  await emit(page, 'meta', { state: 'warming', model: 'fixture-local' });
  await emit(page, 'delta', {
    text: 'Parágrafo de fixture para validar rolagem.\n\n'.repeat(80),
  });
  const conversation = page.locator('.conversation');
  await expect
    .poll(() =>
      conversation.evaluate(
        (el) => el.scrollHeight - el.scrollTop - el.clientHeight,
      ),
    )
    .toBeLessThan(34);
  await conversation.evaluate((el) => {
    el.scrollTop = 0;
    el.dispatchEvent(new Event('scroll'));
  });
  await expect(
    page.getByRole('button', { name: 'Ir para o fim da conversa' }),
  ).toBeVisible();
  await emit(page, 'delta', {
    text: 'Mais conteúdo de fixture.\n\n'.repeat(10),
  });
  await expect.poll(() => conversation.evaluate((el) => el.scrollTop)).toBe(0);
  await page.getByRole('button', { name: 'Ir para o fim da conversa' }).click();
  await emit(page, 'delta', { text: 'Fim do fragmento.' });
  await expect
    .poll(() =>
      conversation.evaluate(
        (el) => el.scrollHeight - el.scrollTop - el.clientHeight,
      ),
    )
    .toBeLessThan(34);
  await page
    .getByRole('button', { name: 'Cancelar resposta', exact: true })
    .click();
  await expect(page.locator('[data-turn-outcome="cancelled"]')).toBeVisible();
  await expect(
    page.getByText('Cancelamento solicitado', { exact: true }),
  ).toBeVisible();
  await startQuestion(page, 'Segunda pergunta de fixture');
  await emit(page, 'meta', {
    state: 'warming',
    summary: {
      utc: summary.utc,
      prediction: { status: 'inactive' },
      model_metrics: { status: 'unavailable' },
    },
  });
  await emit(page, 'error', {
    code: 'resource_busy',
    message: 'Recurso indisponível (fixture).',
  });
  await expect(page.getByRole('alert')).toContainText('fixture');
  await expect(page.locator('[data-turn-outcome="failed"]')).toBeVisible();
  await page
    .locator('.turn')
    .last()
    .getByText('Dados estruturados desta resposta', { exact: true })
    .click();
  await expect(
    page.locator('.turn').last().locator('.assistant-data'),
  ).toContainText('Indisponível');
});
test('cena com telemetria real, preferência reduzida e interrupção somente no navegador; passagem de rotas', async ({
  page,
}) => {
  test.setTimeout(60000);
  let drop = false;
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.route('**/api/v1/devices/*/commands', (r) => {
    expect(r.request().method()).toBe('GET');
    return r.continue();
  });
  await page.routeWebSocket('**/ws', (socket) => {
    const server = socket.connectToServer();
    server.onMessage((raw) => {
      if (drop && JSON.parse(raw.toString()).tipo === 'frame.ready') return;
      socket.send(raw);
    });
  });
  await page.goto('/entrar');
  await capture(page, 'entry-desktop');
  await page.setViewportSize({ width: 390, height: 844 });
  await capture(page, 'entry-mobile');
  await page.setViewportSize({ width: 1440, height: 1000 });
  await login(page);
  await visit(page, 'Cena 3D');
  await page
    .getByLabel('Equipamento na cena', { exact: true })
    .selectOption('ac_01');
  await expect(page.getByTestId('scene-status')).toHaveText('Dados recentes', {
    timeout: 15000,
  });
  const scene = page.locator('.scene-card');
  await expect
    .poll(async () => Number(await scene.getAttribute('data-geometries')))
    .toBeGreaterThan(0);
  const sensor = page.getByRole('button', {
    name: 'Selecionar Vibração',
    exact: true,
  });
  await sensor.focus();
  await page.keyboard.press('Enter');
  await expect(sensor).toHaveAttribute('aria-pressed', 'true');
  await expect(
    page.getByRole('img', {
      name: 'Histórico WS de Vibração (mm/s)',
      exact: true,
    }),
  ).toBeVisible();
  await expect(page.locator('.component-list button')).toHaveCount(8);
  await capture(page, 'scene-desktop');
  await page.setViewportSize({ width: 390, height: 844 });
  await capture(page, 'scene-mobile');
  const reset = page.getByRole('button', {
    name: 'Recentrar câmera',
    exact: true,
  });
  const box = await reset.boundingBox();
  const canvas = await page.locator('.scene-card canvas').boundingBox();
  expect(box!.y).toBeGreaterThanOrEqual(canvas!.y + canvas!.height);
  await reset.tap();
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await expect(page.getByTestId('scene-status')).toHaveText('Dados recentes');
  await page
    .getByRole('button', {
      name: 'Selecionar Acionamento do compressor',
      exact: true,
    })
    .click();
  await expect(
    page.locator('.component-detail').getByRole('button', {
      name: 'Ligar ventilador do condensador',
      exact: true,
    }),
  ).toHaveCount(0);
  await page
    .getByRole('button', {
      name: 'Selecionar Ventilador da condensadora',
      exact: true,
    })
    .click();
  await expect(
    page.locator('.component-detail').getByRole('button', {
      name: 'Ligar ventilador do condensador',
      exact: true,
    }),
  ).toBeVisible();
  await page.waitForTimeout(1100);
  const reducedAngle = await scene.getAttribute('data-fan-angle');
  await page.waitForTimeout(1100);
  expect(await scene.getAttribute('data-fan-angle')).toBe(reducedAngle);
  await expect(page.getByTestId('scene-status')).toHaveText('Dados recentes');
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  // Begin withholding telemetry only while the scene has a recent frame.
  await expect(scene).toHaveAttribute('data-scene-frozen', 'false');
  drop = true;
  await expect(scene).toHaveAttribute('data-scene-frozen', 'true', {
    timeout: 12000,
  });
  await expect(scene).toHaveAttribute('data-equipment-color', '#8b9aab');
  // UI freshness ticks every 500 ms; renderer statistics publish every second.
  // Gray also means unavailable prediction, so it cannot synchronize that tick.
  // Read the settled renderer angle, then strictly verify a further full tick.
  await page.waitForTimeout(1100);
  const angle = await scene.getAttribute('data-fan-angle');
  await page.waitForTimeout(1100);
  expect(await scene.getAttribute('data-fan-angle')).toBe(angle);
  await expect(page.getByTestId('scene-status')).toContainText('Sem dados');
  await capture(page, 'fixture-scene-stale');
  drop = false;
  await expect(scene).toHaveAttribute('data-scene-frozen', 'false', {
    timeout: 12000,
  });
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await visit(page, 'Assistente local');
  await page.setViewportSize({ width: 1440, height: 1000 });
  for (const name of [
    'Visão geral',
    'Dispositivos',
    'Insights',
    'Dados sintéticos',
    'Treinamento',
    'Mensageria',
    'Auditoria',
    'Usuários',
    'Interfaces locais',
    'Assistente local',
  ]) {
    await visit(page, name);
    await expect
      .poll(() =>
        page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      )
      .toBe(true);
  }
  expect(errors).toEqual([]);
});
test('fixture: entrada preserva erro de limite, usuário e envio por teclado', async ({
  page,
}) => {
  let sent = 0;
  await page.route('**/api/v1/auth/login', (r) => {
    sent++;
    return r.fulfill({
      status: 429,
      json: {
        title: 'Muitas tentativas. Aguarde para tentar novamente (fixture).',
      },
    });
  });
  await page.goto('/entrar');
  await expect(page.getByLabel('Usuário', { exact: true })).toHaveAttribute(
    'autocomplete',
    'username',
  );
  await expect(page.getByLabel('Senha', { exact: true })).toHaveAttribute(
    'autocomplete',
    'current-password',
  );
  await page.getByLabel('Usuário', { exact: true }).fill('conta_fixture');
  await page.getByLabel('Senha', { exact: true }).fill('fixture-password');
  await page.getByLabel('Senha', { exact: true }).press('Enter');
  await expect(page.getByRole('alert')).toContainText('Muitas tentativas');
  await expect(page.getByLabel('Usuário', { exact: true })).toHaveValue(
    'conta_fixture',
  );
  await expect(page.getByLabel('Senha', { exact: true })).toHaveValue('');
  expect(sent).toBe(1);
});
