import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { expect, test } from '@playwright/test';

const root = fileURLToPath(new URL('../../../', import.meta.url));
function publish(after?: string) {
  const result = execFileSync(
    'docker',
    [
      'compose',
      'run',
      '--rm',
      '--no-deps',
      '--pull',
      'never',
      '-v',
      `${root}/infra/tests:/tests:ro`,
      '-v',
      `${root}/secrets/rabbit_inference:/run/secrets/rabbit_inference:ro`,
      'bootstrap',
      'python',
      '/tests/realtime_fixture.py',
      ...(after ? ['--after-sample', after] : []),
    ],
    { cwd: root, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] },
  );
  return JSON.parse(result) as {
    id: string;
    sampled_at: string;
    power_w: number | null;
  };
}

test('AMQP atualiza painel; silêncio expira e reconexão preserva histórico', async ({
  page,
}) => {
  test.setTimeout(90000);
  execFileSync('docker', ['compose', 'stop', 'inference'], {
    cwd: root,
    stdio: 'pipe',
  });
  try {
    await page.goto('/entrar');
    await page.getByLabel('Usuário', { exact: true }).fill('visualizador');
    const input = page.getByLabel('Senha', { exact: true });
    await expect(input).toBeVisible();
    const password = readFileSync(
      new URL('../../../secrets/initial_viewer_password', import.meta.url),
      'utf8',
    ).trim();
    try {
      await input.fill(password);
    } catch {
      throw new Error('Falha ao preencher credencial local.');
    }
    await page.getByRole('button', { name: 'Entrar', exact: true }).click();
    await expect(
      page.getByRole('status').filter({ hasText: 'Conectado' }),
    ).toBeVisible();
    await expect(
      page.getByRole('heading', { name: 'Histórico e consumo' }),
    ).toBeVisible();
    await expect(
      page.locator('.historical-panel tbody tr').first(),
    ).toBeVisible({
      timeout: 25000,
    });
    const first = publish();
    await expect(page.locator(`[data-frame-id="${first.id}"]`)).toBeVisible();
    await expect(
      page.getByRole('status').filter({ hasText: 'Dados recentes' }),
    ).toBeVisible();
    await expect(
      page.getByRole('status').filter({ hasText: 'Sem dados em tempo real' }),
    ).toBeVisible({ timeout: 10000 });
    try {
      execFileSync('docker', ['compose', 'stop', 'api'], {
        cwd: root,
        stdio: 'pipe',
      });
    } finally {
      execFileSync('docker', ['compose', 'start', 'api'], {
        cwd: root,
        stdio: 'pipe',
      });
    }
    await expect(
      page.getByRole('status').filter({ hasText: 'Conectado' }),
    ).toBeVisible({ timeout: 20000 });
    await expect(
      page.locator('.historical-panel tbody tr').first(),
    ).toBeVisible();
    const next = publish(first.sampled_at);
    await expect(page.locator(`[data-frame-id="${next.id}"]`)).toBeVisible();
    await page.getByRole('button', { name: 'Sair', exact: true }).click();
  } finally {
    execFileSync('docker', ['compose', 'start', 'inference'], {
      cwd: root,
      stdio: 'pipe',
    });
  }
});
