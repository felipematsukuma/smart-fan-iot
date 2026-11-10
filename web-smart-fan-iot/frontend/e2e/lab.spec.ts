import { readFileSync } from 'node:fs';
import { expect, test } from './fixtures';

test('laboratório gera milhão reproduzível e cancela parcial sem rótulos no WS', async ({
  page,
}) => {
  test.setTimeout(120000);
  let leaked = false;
  let jobEvents = 0;
  let errors = 0;
  page.on('pageerror', () => errors++);
  page.on('websocket', (socket) =>
    socket.on('framereceived', ({ payload }) => {
      const raw = typeof payload === 'string' ? payload : payload.toString();
      if (
        raw.includes('truth_health_score') ||
        raw.includes('truth_rul_calendar_hours') ||
        raw.includes('latent_damage')
      )
        leaked = true;
      if (
        raw.includes('"tipo":"job.progress"') ||
        raw.includes('"tipo": "job.progress"')
      )
        jobEvents++;
    }),
  );
  await page.goto('/entrar');
  await page.getByLabel('Usuário', { exact: true }).fill('admin');
  const password = readFileSync(
    new URL('../../../secrets/initial_admin_password', import.meta.url),
    'utf8',
  ).trim();
  try {
    await page.getByLabel('Senha', { exact: true }).fill(password);
  } catch {
    throw new Error('Falha ao preencher credencial local.');
  }
  await page.getByRole('button', { name: 'Entrar', exact: true }).click();
  await page.getByRole('link', { name: 'Laboratório', exact: true }).click();
  await expect(page.getByTestId('dataset-estimate')).toContainText(
    '1.036.800 vetores completos',
  );
  const job = page.locator('.job-detail');
  const generate = page.getByRole('button', {
    name: 'Gerar dataset',
    exact: true,
  });
  try {
    await generate.click();
    await expect(job).toHaveAttribute('data-job-status', 'completed', {
      timeout: 30000,
    });
    const first = await job.getAttribute('data-job-id');
    const hash = job.locator('code');
    await expect(hash).toHaveText(/^[a-f0-9]{64}$/, { timeout: 10000 });
    const original = await hash.textContent();
    await expect(
      page.getByRole('heading', {
        name: 'Amostra do laboratório com rótulos',
        exact: true,
      }),
    ).toBeVisible();
    await expect(generate).toBeEnabled();
    await generate.click();
    await expect.poll(() => job.getAttribute('data-job-id')).not.toBe(first);
    await expect(job).toHaveAttribute('data-job-status', 'completed', {
      timeout: 30000,
    });
    await expect(hash).toHaveText(original!, { timeout: 10000 });
    const second = await job.getAttribute('data-job-id');
    await page
      .getByLabel('Equipamentos sintéticos', { exact: true })
      .fill('100');
    await page.getByLabel('Vetores por bloco', { exact: true }).fill('100');
    await generate.click();
    await expect.poll(() => job.getAttribute('data-job-id')).not.toBe(second);
    await page
      .getByRole('button', { name: 'Cancelar geração', exact: true })
      .click();
    await expect(job).toHaveAttribute('data-job-status', 'cancelled', {
      timeout: 15000,
    });
    await expect(
      job.getByText('Parcial não treinável;', { exact: false }),
    ).toBeVisible();
    expect(leaked).toBe(false);
    expect(jobEvents).toBeGreaterThan(0);
    expect(errors).toBe(0);
  } finally {
    const cancel = page.getByRole('button', {
      name: 'Cancelar geração',
      exact: true,
    });
    if ((await cancel.count()) && (await cancel.isEnabled()))
      await cancel.click();
  }
  await page.getByRole('button', { name: 'Sair', exact: true }).click();
});
