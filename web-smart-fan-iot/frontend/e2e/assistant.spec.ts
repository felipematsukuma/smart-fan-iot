import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { expect, test } from './fixtures';

test('Ollama local envia fragmentos reais, apresenta fontes e cancela antes de liberar recurso', async ({
  page,
}) => {
  test.setTimeout(120000);
  let errors = 0;
  page.on('pageerror', () => errors++);
  await page.goto('/entrar');
  await page.getByLabel('Usuário', { exact: true }).fill('operador');
  const password = readFileSync(
    new URL('../../../secrets/initial_operator_password', import.meta.url),
    'utf8',
  ).trim();
  try {
    await page.getByLabel('Senha', { exact: true }).fill(password);
  } catch {
    throw new Error('Falha ao preencher credencial local.');
  }
  await page.getByRole('button', { name: 'Entrar', exact: true }).click();
  await page
    .getByRole('link', { name: 'Assistente local', exact: true })
    .click();
  const question = page.getByLabel('Pergunta sobre o equipamento', {
    exact: true,
  });
  await expect(
    page.getByLabel('Equipamento da conversa', { exact: true }),
  ).toHaveValue('ac_01');
  await question.fill(
    'Resuma em duas frases o estado observado e a incerteza da estimativa.',
  );
  await page
    .getByRole('button', { name: 'Perguntar ao assistente', exact: true })
    .click();
  await expect(page.locator('.turn').first()).toHaveAttribute(
    'data-turn-outcome',
    /^(completed|failed|cancelled)$/,
    { timeout: 95000 },
  );
  await expect(page.locator('[data-turn-outcome="completed"]')).toBeVisible();
  await expect(page.getByTestId('assistant-answer')).not.toBeEmpty();
  await expect(
    page.getByRole('heading', {
      name: 'Assistente · llama3.2:1b-instruct-q4_K_M',
      exact: true,
    }),
  ).toBeVisible();
  await page.getByText('Dados usados nesta resposta', { exact: true }).click();
  await expect(page.locator('.turn details pre')).toContainText('rul_unit');
  await expect(page.locator('.turn details pre')).not.toContainText('readings');
  await expect(
    page.locator('.markdown script, .markdown img, .markdown iframe'),
  ).toHaveCount(0);
  await page.screenshot({
    path: 'test-results/assistant-review.png',
    fullPage: true,
  });
  await question.fill(
    'Explique em detalhes o significado da corrente, da vibração e das temperaturas.',
  );
  await page
    .getByRole('button', { name: 'Perguntar ao assistente', exact: true })
    .click();
  await expect(
    page.getByRole('status').filter({ hasText: 'Preparando o modelo local' }),
  ).toBeVisible({ timeout: 15000 });
  await page
    .getByRole('button', { name: 'Cancelar resposta', exact: true })
    .click();
  await expect(page.locator('[data-turn-outcome="cancelled"]')).toBeVisible();
  await expect
    .poll(
      () =>
        execFileSync(
          'docker',
          [
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
            "SELECT state FROM transport.resource_leases WHERE resource='heavy';",
          ],
          {
            cwd: new URL('../../..', import.meta.url),
            encoding: 'utf8',
            stdio: ['pipe', 'pipe', 'pipe'],
          },
        ).trim(),
      { timeout: 15000 },
    )
    .toBe('released');
  const loaded = execFileSync(
    'docker',
    ['compose', 'exec', '-T', 'ollama', 'ollama', 'ps'],
    {
      cwd: new URL('../../..', import.meta.url),
      encoding: 'utf8',
      stdio: ['pipe', 'pipe', 'pipe'],
    },
  );
  expect(loaded).not.toContain('llama3.2:1b-instruct-q4_K_M');
  expect(errors).toBe(0);
  await page.getByRole('button', { name: 'Sair', exact: true }).click();
});
