import { expect, test, type Page } from '@playwright/test';

const token = process.env.PENFOLD_TOKEN ?? '';

async function openIde(page: Page): Promise<void> {
  await page.goto(`/?token=${encodeURIComponent(token)}`);
  await expect(page.locator('.token-gate')).toHaveCount(0);
  await expect(page.getByLabel('Seleccionar workflow')).toBeVisible();
  await expect(page.getByLabel('Librería de nodos')).toBeVisible();
}

test('carga la IDE con el token de la URL, ejecuta un workflow y lo recupera al recargar', async ({
  page,
}) => {
  test.skip(!token, 'PENFOLD_TOKEN no configurado');
  await openIde(page);

  await page.getByLabel('Seleccionar workflow').selectOption('simple');
  await expect(page.locator('.pf-node')).toHaveCount(4);
  await expect(page.locator('.react-flow__edge')).toHaveCount(3);

  await page.getByRole('button', { name: 'Ejecutar' }).click();
  const modal = page.getByRole('dialog');
  if (await modal.count()) {
    const input = modal.locator('input').first();
    if (await input.count()) await input.fill('E2E JWT');
    await modal.getByRole('button', { name: /ejecutar/i }).click();
  }

  await expect(page.locator('.run-status')).toHaveText('completed', { timeout: 20_000 });
  await expect(page.locator('.event-row').filter({ hasText: 'run_finished' })).toBeVisible();
  const simulated = page.locator('.pf-node .pf-node-sim');
  await expect(simulated.first()).toBeVisible();

  await page.reload();
  await expect(page.getByLabel('Seleccionar workflow')).toBeVisible();
  await page.getByLabel('Seleccionar workflow').selectOption('simple');
  await expect(page.locator('.pf-node')).toHaveCount(4);
  await expect(page.locator('.react-flow__edge')).toHaveCount(3);
});

test('crea un workflow desde la librería, configura el agente y lo guarda', async ({ page }) => {
  test.skip(!token, 'PENFOLD_TOKEN no configurado');
  await openIde(page);

  await page.getByRole('button', { name: 'Nuevo' }).click();
  await expect(page.locator('.pf-node')).toHaveCount(0);

  const canvas = page.locator('.react-flow__pane');
  await page.getByLabel('Añadir nodo Input').dblclick();
  await page.getByLabel('Añadir nodo Agent').dblclick();
  await page.getByLabel('Añadir nodo Output').dblclick();
  await expect(page.locator('.pf-node')).toHaveCount(3);

  // Conectar Input -> Agent arrastrando desde el handle de salida al de entrada.
  const sourceHandle = page.locator('.pf-node.node-input .react-flow__handle.source');
  const targetHandle = page.locator('.pf-node.node-agent .react-flow__handle.target');
  const from = await sourceHandle.boundingBox();
  const to = await targetHandle.boundingBox();
  if (from && to) {
    await page.locator('.react-flow__pane').click({ position: { x: 10, y: 10 } });
    await sourceHandle.hover();
    await page.mouse.down();
    await page.mouse.move(from.x + 40, from.y, { steps: 5 });
    await targetHandle.hover({ force: true });
    await page.waitForTimeout(200);
    await page.mouse.up();
    await expect(page.locator('.react-flow__edge')).toHaveCount(1);
  }

  // Arrastrar un nodo desde la librería al canvas (HTML5 drag & drop).
  await page.getByLabel('Añadir nodo Command').dragTo(canvas);
  await expect(page.locator('.pf-node')).toHaveCount(4);

  // Seleccionar el nodo agente y configurar su definición.
  await page.locator('.pf-node.node-agent').click();
  const agentSelect = page.locator('#agent-select');
  await expect(agentSelect).toBeVisible();
  await agentSelect.selectOption('product-analyst');

  // Guardar (la UI genera un ID estable) y verificar persistencia tras recargar.
  await page.getByRole('button', { name: /Guardar/i }).click();
  await expect(page.getByLabel('Seleccionar workflow')).not.toHaveValue('');
  const savedId = await page.getByLabel('Seleccionar workflow').inputValue();
  expect(savedId).toMatch(/^wf[_-]/);
  await page.reload();
  await expect(page.getByLabel('Seleccionar workflow')).toBeVisible();
  await page.getByLabel('Seleccionar workflow').selectOption(savedId);
  await expect(page.locator('.pf-node')).toHaveCount(4);
});
