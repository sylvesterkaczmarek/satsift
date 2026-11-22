'use strict';

const { test, expect } = require('@playwright/test');
const fs = require('node:fs/promises');

const WORKBENCH = process.env.SATSIFT_TEST_ROUTE || '/satsift/';

async function openConsole(page, example = 'leo') {
  await page.goto(WORKBENCH);
  await expect(page.locator('#status')).toHaveText('Waiting for input');
  await page.locator('#demoSelect').selectOption(example);
  await page.locator('#tryDemo').click();
  await expect(page.locator('#run')).toHaveText('Analysis up to date');
  await expect(page.locator('#orbitChart .main-svg').first()).toBeVisible();
}

async function savedEvidence(page) {
  const pending = page.waitForEvent('download');
  await page.locator('#downloadBundle').click();
  return JSON.parse(await fs.readFile(await (await pending).path(), 'utf8'));
}

test('console context and selected event agree with the downloadable evidence', async ({ page }) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await openConsole(page);
  const evidence = await savedEvidence(page);
  await expect(page.locator('#consoleNorad')).toHaveText(evidence.object_id);
  await expect(page.locator('#consoleObject')).toContainText('DEMO');
  await expect(page.locator('#consoleSource')).toContainText(/synthetic/i);
  expect(Date.parse(await page.locator('#consoleEpoch').textContent())).toBe(Date.parse(evidence.rows.at(-1).epoch_utc));
  await expect(page.locator('#consoleState')).toContainText('Candidate events');
  await expect(page.locator('#eventInspectorTitle')).toContainText(evidence.events[0].event_id || evidence.events[0].id);
  await expect(page.locator('#eventInspectorBody')).toContainText('not probabilities');
  await expect(page.locator('#eventInspectorBody')).toContainText('Primary empirical band');
  await expect(page.locator('#flagTableBody [data-event-index="0"]')).toHaveAttribute('aria-pressed', 'true');

  const selected = await page.evaluate(() => document.getElementById('orbitChart').layout.shapes
    .filter(shape => shape.name.startsWith('Candidate ')).map(shape => ({ epoch: Date.parse(shape.x0), width: shape.line.width })));
  expect(selected[0].epoch).toBe(Date.parse(evidence.events[0].strongest_epoch_utc));
  expect(selected[0].width).toBeGreaterThan(1);
  await page.getByText('Pre-event source record', { exact: true }).click();
  await expect(page.locator('.inspector-records').first().locator('pre')).toContainText('1 90001');
  await page.locator('#flagTableBody [data-event-index="0"]').focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('#eventInspectorTitle')).toContainText('EVT-001');
  expect(errors).toEqual([]);
});

test('selected event focus, linked zoom and theme changes preserve the analysed run', async ({ page }) => {
  await openConsole(page);
  const original = await savedEvidence(page);
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await page.locator('#focusEventCharts').click();
  await expect.poll(() => page.evaluate(() => document.getElementById('orbitChart').layout.xaxis.autorange)).toBe(false);
  const beforeTheme = await page.evaluate(() => ({
    orbit: document.getElementById('orbitChart').layout.xaxis.range,
    rate: document.getElementById('rateChart').layout.xaxis.range
  }));
  expect(beforeTheme.orbit).toEqual(beforeTheme.rate);
  await page.locator('#themeToggle').click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  await expect.poll(() => page.evaluate(() => document.getElementById('orbitChart').layout.paper_bgcolor)).toBe('#ffffff');
  expect(await page.evaluate(() => document.getElementById('orbitChart').layout.xaxis.range)).toEqual(beforeTheme.orbit);
  expect((await savedEvidence(page)).run_id).toBe(original.run_id);

  const range = original.rows.slice(2, 6).map(row => row.epoch_utc);
  await page.evaluate(async values => {
    await window.Plotly.relayout('rateChart', { 'xaxis.range': [values[0], values.at(-1)], 'xaxis.autorange': false });
  }, range);
  await expect.poll(() => page.evaluate(() => document.getElementById('orbitChart').layout.xaxis.range
    .map(value => Date.parse(value)))).toEqual([Date.parse(range[0]), Date.parse(range.at(-1))]);
  await page.locator('#resetChartZoom').click();
  await expect.poll(() => page.evaluate(() => document.getElementById('rateChart').layout.xaxis.autorange)).toBe(true);
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  await expect(page.locator('#eventInspectorBody')).not.toContainText('EVT-001');
});

test('input edits, validation failure and reset remove stale inspector and object context', async ({ page }) => {
  await openConsole(page);
  const raw = await page.locator('#tles').inputValue();
  await page.locator('#manualInputDetails').evaluate(element => { element.open = true; });
  await page.locator('#tles').fill('{broken json');
  await expect(page.locator('#consoleNorad')).toHaveText('n/a');
  await expect(page.locator('#consoleSource')).toHaveText('No analysed source');
  await expect(page.locator('#eventInspectorTitle')).toHaveText('Event inspector');
  await expect(page.locator('#focusEventCharts')).toBeDisabled();
  await expect(page.locator('#orbitChart .main-svg')).toHaveCount(0);
  await page.locator('#run').click();
  await expect(page.locator('#consoleQuality')).toHaveText('Input invalid');
  await expect(page.locator('#eventInspectorBody')).toContainText('No validated analysis');
  await page.locator('#tles').fill(raw);
  await page.locator('#run').click();
  await expect(page.locator('#eventInspectorTitle')).toContainText('EVT-001');
  await page.locator('#reset').click();
  await expect(page.locator('#consoleObject')).toHaveText('No analysed object');
  await expect(page.locator('#eventInspectorTitle')).toHaveText('Event inspector');
  await expect(page.locator('#previousEvent')).toBeDisabled();
  await expect(page.locator('#nextEvent')).toBeDisabled();
  await expect(page.locator('#tles')).toHaveValue(raw);
});

test('gap annotations and calibration shading agree with eligible source intervals', async ({ page }) => {
  await openConsole(page, 'sparse');
  const sparse = await savedEvidence(page);
  expect(sparse.excluded_gap_count).toBeGreaterThan(0);
  const gaps = await page.evaluate(() => document.getElementById('orbitChart').layout.shapes
    .filter(shape => shape.name === 'Excluded data gap').map(shape => [Date.parse(shape.x0), Date.parse(shape.x1)]));
  expect(gaps.length).toBeGreaterThan(0);
  for (let index = 1; index < sparse.rows.length; index++) {
    if (sparse.rows[index].pair_eligible) continue;
    expect(gaps.some(([start, end]) => start <= Date.parse(sparse.rows[index - 1].epoch_utc)
      && end >= Date.parse(sparse.rows[index].epoch_utc))).toBe(true);
  }
  await expect(page.locator('#eventInspectorBody')).toContainText('abstained');
  await page.locator('#demoSelect').selectOption('leo');
  await page.locator('#tryDemo').click();
  await expect(page.locator('#eventInspectorTitle')).toContainText('EVT-001');
  await expect.poll(() => page.evaluate(() => document.getElementById('orbitChart').layout.shapes
    .filter(shape => shape.name === 'Excluded data gap').length)).toBe(0);
  const evidence = await savedEvidence(page);
  const selectedEpoch = Date.parse(evidence.events[0].strongest_epoch_utc);
  const previous = evidence.rows.filter(row => row.pair_eligible && Date.parse(row.epoch_utc) < selectedEpoch)
    .slice(-evidence.calibration_window);
  const calibration = await page.evaluate(() => document.getElementById('orbitChart').layout.shapes
    .filter(shape => shape.name === 'Selected event calibration').map(shape => [Date.parse(shape.x0), Date.parse(shape.x1)]));
  expect(previous).toHaveLength(evidence.calibration_window);
  expect(calibration.length).toBeGreaterThan(0);
  expect(calibration.at(-1)[1]).toBe(Date.parse(previous.at(-1).epoch_utc));
  expect(calibration.every(([, end]) => end < selectedEpoch)).toBe(true);
});

test('theme preference storage failure leaves the console usable', async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(window, 'localStorage', { configurable: true, get() { throw new Error('Storage unavailable'); } });
  });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await openConsole(page);
  await page.locator('#themeToggle').click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  await expect(page.locator('#eventInspectorTitle')).toContainText('EVT-001');
  expect(errors).toEqual([]);
});

test('keyboard event navigation updates the inspector and chart selection together', async ({ page }) => {
  await openConsole(page);
  const evidence = await savedEvidence(page);
  const shifted = evidence.normalized_input_omm.map(record => {
    const copy = { ...record, EPOCH: new Date(Date.parse(record.EPOCH) + 32 * 86400000).toISOString(), SMD_SOURCE_FORMAT: 'OMM JSON' };
    delete copy.SMD_TLE;
    return copy;
  });
  await page.locator('#manualInputDetails').evaluate(element => { element.open = true; });
  await page.locator('#tles').fill(JSON.stringify(evidence.normalized_input_omm.concat(shifted)));
  await page.locator('#run').click();
  await expect.poll(() => page.locator('#flagTableBody [data-event-index]').count()).toBeGreaterThan(1);
  await page.locator('#flagTableBody [data-event-index="0"]').focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('#eventInspectorTitle')).toContainText('EVT-001');
  await expect(page.locator('#previousEvent')).toBeDisabled();
  await page.locator('#nextEvent').focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('#eventInspectorTitle')).toContainText('EVT-002');
  await expect(page.locator('#flagTableBody [data-event-index="1"]')).toHaveAttribute('aria-pressed', 'true');
  const selectedNames = await page.evaluate(() => document.getElementById('orbitChart').layout.shapes
    .filter(shape => shape.type === 'line' && shape.line.width > 1).map(shape => shape.name));
  expect(selectedNames).toEqual(['Candidate EVT-002']);
});

test('dark and light charts, orbit context and the inspector remain accessible on mobile', async ({ page }) => {
  const AxeBuilder = require('@axe-core/playwright').default;
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await openConsole(page);
  await page.locator('#orbitDetails').evaluate(element => { element.open = true; });
  await expect.poll(() => page.evaluate(() => document.getElementById('orbitViewer').data?.length || 0)).toBeGreaterThan(1);
  const camera = await page.evaluate(() => document.getElementById('orbitViewer').layout.scene.camera);
  for (const theme of ['dark', 'light']) {
    if ((await page.locator('html').getAttribute('data-theme')) !== theme) await page.locator('#themeToggle').click();
    await page.setViewportSize({ width: 390, height: 844 });
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    const result = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
    expect(result.violations.map(item => ({ id: item.id, nodes: item.nodes.map(node => node.target) }))).toEqual([]);
  }
  expect(await page.evaluate(() => document.getElementById('orbitViewer').layout.scene.camera)).toEqual(camera);
  await expect.poll(() => page.evaluate(() => document.getElementById('orbitViewer').layout.paper_bgcolor)).toBe('#ffffff');
  expect(errors).toEqual([]);
});


test('pointer hover links UTC crosshairs and clears both charts without event recursion', async ({ page }) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await openConsole(page);
  await page.evaluate(() => {
    window.__consoleHoverCounts = { orbitChart: 0, rateChart: 0 };
    for (const id of Object.keys(window.__consoleHoverCounts)) {
      document.getElementById(id).on('plotly_hover', () => { window.__consoleHoverCounts[id]++; });
    }
  });
  const epochAt = async (id, index) => page.evaluate(({ id, index }) =>
    Date.parse(document.getElementById(id).data[0].x[index]), { id, index });
  const hoverEpochs = async id => page.evaluate(id =>
    (document.getElementById(id)._hoverdata || []).map(point =>
      Date.parse(document.getElementById(id).data[point.curveNumber].x[point.pointNumber])), id);
  const crosshairOffsets = async (id, epoch) => page.evaluate(({ id, epoch }) => {
    const chart = document.getElementById(id);
    const axis = chart._fullLayout.xaxis;
    const expectedX = axis._offset + axis.l2p(epoch);
    return [...chart.querySelectorAll('.spikeline')].filter(line => {
      const style = getComputedStyle(line);
      return style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity) > 0
        && Math.abs(Number(line.getAttribute('y2')) - Number(line.getAttribute('y1'))) > 0;
    }).map(line => Math.abs(Number(line.getAttribute('x1')) - expectedX));
  }, { id, epoch });
  const selectedEpoch = await epochAt('orbitChart', 5);
  await page.locator('#orbitChart .scatterlayer .trace').first().locator('.point').nth(5).hover({ force: true });
  await expect.poll(() => hoverEpochs('rateChart')).toContain(selectedEpoch);
  await expect.poll(async () => (await crosshairOffsets('orbitChart', selectedEpoch)).some(offset => offset < 2)).toBe(true);
  await expect.poll(async () => (await crosshairOffsets('rateChart', selectedEpoch)).some(offset => offset < 2)).toBe(true);

  await page.locator('#consoleObject').hover();
  await expect.poll(() => hoverEpochs('orbitChart')).toEqual([]);
  await expect.poll(() => hoverEpochs('rateChart')).toEqual([]);
  await expect(page.locator('#orbitChart .spikeline')).toHaveCount(0);
  await expect(page.locator('#rateChart .spikeline')).toHaveCount(0);

  // The first rate sample is null, so the fifth rendered point is record 5.
  await page.locator('#rateChart .scatterlayer .trace').first().locator('.point').nth(4).hover({ force: true });
  await expect.poll(() => hoverEpochs('orbitChart')).toContain(selectedEpoch);
  await expect.poll(async () => (await crosshairOffsets('orbitChart', selectedEpoch)).some(offset => offset < 2)).toBe(true);
  await expect.poll(async () => (await crosshairOffsets('rateChart', selectedEpoch)).some(offset => offset < 2)).toBe(true);
  await page.locator('#consoleObject').hover();
  await expect.poll(() => hoverEpochs('orbitChart')).toEqual([]);
  await expect.poll(() => hoverEpochs('rateChart')).toEqual([]);
  const counts = await page.evaluate(() => window.__consoleHoverCounts);
  expect(counts.orbitChart).toBeGreaterThan(0);
  expect(counts.rateChart).toBeGreaterThan(0);
  expect(counts.orbitChart + counts.rateChart).toBeLessThan(20);
  expect(errors).toEqual([]);
});
