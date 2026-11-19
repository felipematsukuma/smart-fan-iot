import { readFileSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { randomUUID } from 'node:crypto';
import { test, expect } from './fixtures';
import { isServerControl } from '../src/lib/ws-control';

test.use({ hasTouch: true });
const evidence = resolve('../../evidence/ui-pilot');
mkdirSync(evidence, { recursive: true });
async function login(page: import('@playwright/test').Page) {
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
  await page.getByRole('button', { name: 'Entrar', exact: true }).click();
  await page.getByLabel('Equipamento', { exact: true }).selectOption('ac_01');
}

test('leituras reais: teclado, grupos, três temperaturas e toque no celular', async ({
  page,
}) => {
  test.setTimeout(60000);
  await login(page);
  const picker = page.locator('.pv-reading-picker');
  const summary = picker.locator('summary');
  await expect(picker).not.toHaveAttribute('open', '');
  await summary.focus();
  await page.keyboard.press('Enter');
  await expect(picker).toHaveAttribute('open', '');
  const power = page.getByRole('checkbox', {
    name: 'Potência (W)',
    exact: true,
  });
  await expect(power).toBeChecked();
  await expect(power).toBeDisabled();
  const inside = page.getByRole('checkbox', {
    name: 'Temperatura interna (°C)',
    exact: true,
  });
  await inside.focus();
  await page.keyboard.press('Space');
  await expect(power).not.toBeChecked();
  await expect(inside).toBeDisabled();
  await page
    .getByRole('checkbox', { name: 'Temperatura externa (°C)', exact: true })
    .check();
  await page
    .getByRole('checkbox', { name: 'Temperatura da carcaça (°C)', exact: true })
    .check();
  await expect(page.locator('.power-chart')).toHaveAttribute(
    'data-series-count',
    '3',
  );
  await expect(page.locator('.power-chart')).toHaveAttribute('data-unit', '°C');
  await expect(
    page.getByRole('heading', { name: 'Temperaturas em tempo real' }),
  ).toBeVisible();
  await expect(page.locator('.pv-series-legend li')).toHaveCount(3);
  const outsideLine = page.locator('[data-series="outdoor_temp_c"] line');
  await expect(outsideLine).toHaveAttribute('stroke-dasharray', '8 4');
  const current = page.getByRole('checkbox', {
    name: 'Corrente (A)',
    exact: true,
  });
  await current.check();
  await expect(page.locator('.power-chart')).toHaveAttribute(
    'data-series-count',
    '1',
  );
  await expect(page.locator('.power-chart')).toHaveAttribute('data-unit', 'A');
  await page
    .getByRole('checkbox', { name: 'Vibração (mm/s)', exact: true })
    .check();
  await expect(page.locator('.power-chart')).toHaveAttribute(
    'data-unit',
    'mm/s',
  );
  await inside.check();
  await page
    .getByRole('checkbox', { name: 'Temperatura externa (°C)', exact: true })
    .check();
  await page
    .getByRole('checkbox', { name: 'Temperatura da carcaça (°C)', exact: true })
    .check();
  await expect
    .poll(
      () => page.locator('.pv-live-chart .pv-section-heading').innerText(),
      { timeout: 25000 },
    )
    .toMatch(/(?:[8-9]|[1-9][0-9]) amostras/);
  await summary.click();
  await expect(picker).not.toHaveAttribute('open', '');
  await expect(page.locator('.pv-series-legend li')).toHaveCount(3);
  await page.evaluate(() => scrollTo(0, 0));
  await page.screenshot({
    path: resolve(evidence, 'desktop-three.png'),
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator('.pv-zoom select')).toHaveValue('15');
  const totals = await page.locator('.energy-summary').innerText();
  await page.locator('.pv-zoom select').selectOption('0');
  expect(await page.locator('.energy-summary').innerText()).toBe(totals);
  await page.locator('.pv-zoom select').selectOption('15');
  const outside = page.getByRole('checkbox', {
    name: 'Temperatura externa (°C)',
    exact: true,
  });
  await summary.tap();
  await outside.tap();
  await expect(page.locator('.power-chart')).toHaveAttribute(
    'data-series-count',
    '2',
  );
  await outside.tap();
  await expect(outsideLine).toHaveAttribute('stroke', '#1d4ed8');
  await expect(outsideLine).toHaveAttribute('stroke-dasharray', '8 4');
  await expect(page.locator('.power-chart')).toHaveAttribute(
    'data-series-count',
    '3',
  );
  await summary.tap();
  await expect
    .poll(() =>
      page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
    )
    .toBe(true);
  await page.evaluate(() => scrollTo(0, 0));
  await page.getByRole('heading', { name: 'Temperaturas em tempo real' }).tap();
  await page.evaluate(() => scrollTo(0, 0));
  await page.screenshot({
    path: resolve(evidence, 'mobile-three.png'),
    fullPage: true,
  });
  await page.locator('.power-chart canvas').tap();
  await expect(page.getByRole('tooltip')).toContainText(
    'Temperatura externa (°C)',
  );
  const consulted = await page.getByRole('tooltip').innerText();
  expect(consulted).toMatch(/Consulta às \d{2}:\d{2}:\d{2}/);
  expect(consulted).toMatch(/Temperatura interna \(°C\): \d+,\d(?:\n|$)/);
  const sample = await page
    .locator('.pv-live-chart')
    .getAttribute('data-frame-id');
  await expect(page.locator('.pv-live-chart')).not.toHaveAttribute(
    'data-frame-id',
    sample!,
  );
  expect(await page.getByRole('tooltip').innerText()).toBe(consulted);
  await page
    .locator('.pv-live-chart')
    .screenshot({ path: resolve(evidence, 'mobile-three-tooltip.png') });
  await page.keyboard.press('Escape');
  await expect(page.getByRole('tooltip')).toHaveCount(0);
  await page.locator('.power-chart canvas').tap();
  await expect(page.getByRole('tooltip')).toBeVisible();
  await page.getByRole('heading', { name: 'Temperaturas em tempo real' }).tap();
  await expect(page.getByRole('tooltip')).toHaveCount(0);
});

test('fixture: temperaturas ausentes, zero e estado desatualizado preservam seleção', async ({
  page,
}) => {
  const controls = JSON.parse(
    readFileSync('src/lib/ws.fixtures.json', 'utf8'),
  ) as { name: string; value: unknown }[];
  const fixture = structuredClone(
    controls.find((item) => item.name === 'snapshot')!.value,
  );
  if (!isServerControl(fixture) || fixture.type !== 'snapshot')
    throw new Error('Invalid fixture');
  const frame = fixture.events.find((event) => event.tipo === 'frame.ready');
  if (!frame || frame.tipo !== 'frame.ready') throw new Error('Missing frame');
  frame.conteudo.telemetry.readings.indoor_temp_c = null;
  frame.conteudo.telemetry.readings.outdoor_temp_c = 0;
  frame.conteudo.telemetry.readings.compressor_case_temp_c = null;
  frame.conteudo.telemetry.quality.missing_fields = [
    'indoor_temp_c',
    'compressor_case_temp_c',
  ];
  let streaming = true;
  await page.routeWebSocket('**/ws', (socket) => {
    let interval: ReturnType<typeof setInterval>;
    const stamp = () => {
      const at = new Date().toISOString();
      frame.timestamp = at;
      frame.metadata.observed_at = at;
      frame.metadata.sequence++;
      frame.id = randomUUID();
      fixture.server_time = at;
      fixture.devices[0]!.last_sample_at = at;
    };
    socket.onMessage((raw) => {
      if (JSON.parse(raw.toString()).type !== 'authenticate') return;
      stamp();
      fixture.events = [frame];
      socket.send(
        JSON.stringify({
          type: 'authenticated',
          server_time: fixture.server_time,
          heartbeat_seconds: 15,
          stale_after_seconds: 6,
        }),
      );
      socket.send(JSON.stringify(fixture));
      interval = setInterval(() => {
        if (streaming) {
          stamp();
          socket.send(JSON.stringify(frame));
        }
      }, 1000);
    });
    socket.onClose(() => clearInterval(interval));
  });
  await login(page);
  await page.locator('.pv-reading-picker summary').click();
  for (const name of [
    'Temperatura interna (°C)',
    'Temperatura externa (°C)',
    'Temperatura da carcaça (°C)',
  ])
    await page.getByRole('checkbox', { name, exact: true }).check();
  await expect(page.getByTestId('pilot-temperature')).toHaveText('—');
  await expect(page.locator('.power-chart')).toHaveAttribute(
    'data-series-count',
    '3',
  );
  await page.locator('.power-chart canvas').tap();
  await expect(page.getByRole('tooltip')).toContainText(
    'Temperatura externa (°C): 0,0',
  );
  await expect(page.getByRole('tooltip')).not.toContainText(
    'Temperatura interna',
  );
  streaming = false;
  await expect(page.locator('.pv-freshness')).toContainText(
    'Dados desatualizados',
    { timeout: 10000 },
  );
  await expect(page.locator('.power-chart')).toHaveAttribute(
    'data-series-count',
    '3',
  );
  await expect(
    page.getByText('Conexão ao vivo: Conectada', { exact: true }),
  ).toBeVisible();
  await expect(page.locator('.pv-series-legend li')).toHaveCount(3);
});
