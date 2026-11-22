'use strict';

const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;
const fs = require('node:fs/promises');

const WORKBENCH = '/satsift';

async function openWorkbench(page) {
  await page.goto(WORKBENCH + '/');
  await expect(page.locator('#status')).toHaveText('Waiting for input');
}

async function runExample(page, name = 'leo') {
  await page.locator('#demoSelect').selectOption(name);
  await page.locator('#tryDemo').click();
  await expect(page.locator('#executiveSummary')).toBeVisible();
  await expect(page.locator('#run')).toHaveText('Analysis up to date');
}

async function downloadPackage(page) {
  const downloaded = page.waitForEvent('download');
  await page.locator('#downloadBundle').click();
  const download = await downloaded;
  expect(download.suggestedFilename()).toMatch(/^satellite-maneuver-reproducibility-.+\.json$/);
  return JSON.parse(await fs.readFile(await download.path(), 'utf8'));
}

async function expectNoOverflow(page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
}

async function checkAccessibility(page) {
  const result = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
  expect(result.violations.map(item => ({ id: item.id, impact: item.impact, nodes: item.nodes.map(node => node.target) }))).toEqual([]);
}

test('first visit presents a clear start and the hero runs a local example without navigation', async ({ page }) => {
  const errors = [];
  const externalRequests = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => {
    if (!new URL(request.url()).hostname.match(/^(127\.0\.0\.1|localhost)$/)) externalRequests.push(request.url());
  });
  await openWorkbench(page);
  await expect(page.locator('#analysisEmptyState')).toBeVisible();
  await expect(page.locator('#chartCard')).toBeHidden();
  await expect(page.locator('#exportCard')).toBeHidden();
  await checkAccessibility(page);
  await page.locator('#heroDemoButton').click();
  await expect(page.locator('#summaryEventCount')).toHaveText('1');
  await expect(page.locator('#resultBox')).toContainText('candidate');
  await expect(page.locator('#analysisEmptyState')).toBeHidden();
  await expect(page.locator('#orbitChart .main-svg').first()).toBeVisible();
  await expect(page.locator('#candidateEventsCard')).toBeVisible();
  expect(await page.evaluate(() => performance.getEntriesByType('navigation').length)).toBe(1);
  expect(externalRequests).toEqual([]);
  expect(errors).toEqual([]);
});

for (const scenario of [
  { name: 'quiet', outcome: /No (?:clear )?candidate/i, eventCount: '0' },
  { name: 'sparse', outcome: /Abstain|insufficient/i, eventCount: 'suppressed' }
]) {
  test(`${scenario.name} history distinguishes no event from insufficient evidence`, async ({ page }) => {
    await openWorkbench(page);
    await runExample(page, scenario.name);
    await expect(page.locator('#resultBox')).toContainText(scenario.outcome);
    await expect(page.locator('#summaryEventCount')).toHaveText(scenario.eventCount);
    await expect(page.locator('#candidateEventsCard')).toBeHidden();
    const result = await downloadPackage(page);
    expect(result.events).toHaveLength(0);
    expect(result.interpretable).toBe(scenario.name === 'quiet');
  });
}

test('invalid input displays its explanation and removes the previous result until repaired', async ({ page }) => {
  await openWorkbench(page);
  await runExample(page);
  await page.locator('#executiveSummary .summary-details > summary').click();
  await expect(page.locator('#executiveSummary .summary-grid')).toBeVisible();
  const original = await page.locator('#tles').inputValue();
  await page.locator('#manualInputDetails > summary').click();
  await page.locator('#tles').fill('{broken json');
  await page.locator('#run').click();
  await expect(page.locator('#executiveSummary')).toBeVisible();
  await expect(page.locator('#resultBox')).toContainText('Analysis unavailable');
  await expect(page.locator('#resultBox .result-body')).not.toHaveText('');
  await expect(page.locator('#executiveSummary .summary-grid')).toBeHidden();
  await expect(page.locator('#stickyResultBar')).toBeHidden();
  await expect(page.locator('#chartCard')).toBeHidden();
  await expect(page.locator('#exportCard')).toBeHidden();
  await page.locator('#tles').fill(original);
  await page.locator('#run').click();
  await expect(page.locator('#summaryEventCount')).toHaveText('1');
  await expect(page.locator('#executiveSummary .summary-grid')).toBeVisible();
});

test('a saved evidence package restores its settings and reproduces the candidate', async ({ page }) => {
  await openWorkbench(page);
  await runExample(page);
  const original = await downloadPackage(page);
  expect(original.normalized_input_omm).toHaveLength(original.valid_snapshots);
  expect(original.events).toHaveLength(1);
  expect(original.calibration_window).toBe(6);
  expect(original.evidence_note).toContain(original.run_id);
  await page.locator('#sensitivity').selectOption('conservative');
  await page.locator('.controls-card > details > summary').click();
  await page.locator('#dath').fill('12');
  await page.locator('#stale').fill('75');
  await page.locator('#manualInputDetails > summary').click();
  await page.locator('#fileInput').setInputFiles({
    name: 'saved-analysis.json', mimeType: 'application/json',
    buffer: Buffer.from(JSON.stringify(original))
  });
  await expect(page.locator('#fileImportHint')).toContainText(/restor|accepted/i);
  await expect(page.locator('#win')).toHaveValue('6');
  await expect(page.locator('#alpha')).toHaveValue('0.1');
  await expect(page.locator('#dath')).toHaveValue('0.05');
  await expect(page.locator('#stale')).toHaveValue('30');
  await expect(page.locator('#summaryEventCount')).toHaveText('1');
  const imported = await downloadPackage(page);
  expect(imported.valid_snapshots).toBe(original.valid_snapshots);
  expect(imported.events.map(event => [event.start_utc, event.end_utc, event.direction])).toEqual(
    original.events.map(event => [event.start_utc, event.end_utc, event.direction])
  );
  await page.locator('#exportCard .export-options > summary').click();
  const csvDownload = page.waitForEvent('download');
  await page.locator('#downloadCsv').click();
  const csv = await fs.readFile(await (await csvDownload).path(), 'utf8');
  expect(csv).toContain('epoch_utc');
  expect(csv.trim().split('\n')).toHaveLength(original.valid_snapshots + 1);
});

test('an incompatible or malformed saved package preserves the existing input and settings', async ({ page }) => {
  await openWorkbench(page);
  await runExample(page);
  const valid = await downloadPackage(page);
  await page.locator('#sensitivity').selectOption('conservative');
  const originalText = await page.locator('#tles').inputValue();
  await page.locator('#manualInputDetails > summary').click();
  for (const invalid of [
    { ...valid, method_version: 'unsupported-method' },
    { ...valid, analysis_options: { ...valid.analysis_options, requestedWindow: -3 } }
  ]) {
    await page.locator('#fileInput').setInputFiles({
      name: 'invalid-analysis.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(invalid))
    });
    await expect(page.locator('#fileImportHint')).toContainText(/invalid|unsupported|method|window/i);
    await expect(page.locator('#tles')).toHaveValue(originalText);
    await expect(page.locator('#win')).toHaveValue('8');
    await expect(page.locator('#sensitivity')).toHaveValue('conservative');
  }
});

test('a saved package cannot silently replace settings when append mode is selected', async ({ page }) => {
  await openWorkbench(page);
  await runExample(page);
  const saved = await downloadPackage(page);
  const originalText = await page.locator('#tles').inputValue();
  await page.locator('#manualInputDetails > summary').click();
  await page.locator('#importMode').selectOption('append');
  await page.locator('#fileInput').setInputFiles({
    name: 'saved-analysis.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(saved))
  });
  await expect(page.locator('#fileImportHint')).toContainText(/replace/i);
  await expect(page.locator('#tles')).toHaveValue(originalText);
  await expect(page.locator('#summaryEventCount')).toHaveText('1');
});

test('changing settings invalidates old exports and reset keeps the input available', async ({ page }) => {
  await openWorkbench(page);
  await runExample(page);
  const raw = await page.locator('#tles').inputValue();
  await page.locator('#sensitivity').selectOption('conservative');
  await expect(page.locator('#executiveSummary')).toBeHidden();
  await expect(page.locator('#downloadBundle')).toBeDisabled();
  await expect(page.locator('#run')).toBeEnabled();
  await page.locator('#run').click();
  await expect(page.locator('#executiveSummary')).toBeVisible();
  expect((await downloadPackage(page)).calibration_window).toBe(8);
  await page.locator('#reset').click();
  await expect(page.locator('#tles')).toHaveValue(raw);
  await expect(page.locator('#analysisEmptyState')).toBeVisible();
  await expect(page.locator('#stickyResultBar')).toBeHidden();
});

test('local history service explains its limitation and preserves the loaded history', async ({ page }) => {
  await openWorkbench(page);
  await runExample(page, 'quiet');
  const raw = await page.locator('#tles').inputValue();
  await page.locator('#heroHistoryButton').click();
  await page.locator('#loadHistory').click();
  await expect(page.locator('#historyFetchHint')).toContainText(/local preview|unavailable/i);
  await expect(page.locator('#tles')).toHaveValue(raw);
  await expect(page.locator('#loadHistory')).toBeEnabled();
});

test('a delayed history response cannot overwrite text entered while it was loading', async ({ page }) => {
  await openWorkbench(page);
  await runExample(page);
  const result = await downloadPackage(page);
  let pending;
  const captured = new Promise(resolve => { pending = resolve; });
  await page.route('**/history?**', async route => { pending(route); });
  await page.locator('#heroHistoryButton').click();
  await page.locator('#publicNorad').fill(result.object_id);
  await page.locator('#loadHistory').click();
  const route = await captured;
  await page.locator('#manualInputDetails > summary').click();
  const newerInput = 'My newer input must remain available';
  await page.locator('#tles').fill(newerInput);
  await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ records: result.normalized_input_omm }) });
  await expect(page.locator('#loadHistory')).toBeEnabled();
  await expect(page.locator('#tles')).toHaveValue(newerInput);
  await expect(page.locator('#executiveSummary')).toBeHidden();
});

test('a chart dependency failure still permits tabular review and evidence download', async ({ page }) => {
  await page.route('**/plotly-3.3.1.min.js*', route => route.abort());
  await openWorkbench(page);
  await runExample(page);
  await expect(page.locator('#orbitChart')).toContainText(/unavailable|failed/i);
  await page.locator('#chartDataDetails > summary').click();
  await expect(page.locator('#chartDataBody tr')).toHaveCount(16);
  expect((await downloadPackage(page)).events).toHaveLength(1);
});

test('mobile setup, result and data tables remain usable and accessible', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openWorkbench(page);
  await expectNoOverflow(page);
  await runExample(page);
  await expect(page.locator('#orbitChart .main-svg').first()).toBeVisible();
  await expectNoOverflow(page);
  await page.locator('#flagTableWrap').focus();
  await page.keyboard.press('ArrowRight');
  await expect.poll(() => page.locator('#flagTableWrap').evaluate(element => element.scrollLeft)).toBeGreaterThan(0);
  await page.locator('#chartDataDetails > summary').click();
  await expectNoOverflow(page);
  await page.locator('#technicalDetails > summary').click();
  await expectNoOverflow(page);
  await checkAccessibility(page);
  await page.locator('#manualInputDetails > summary').click();
  await expectNoOverflow(page);
  await expect(page.locator('#chooseFile')).toBeVisible();
});

test('keyboard users can skip to the result region', async ({ page }) => {
  await openWorkbench(page);
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Skip to analysis result' })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.locator('#analysisOutput')).toBeFocused();
});

test('a browser without JavaScript receives an explanation and documentation link', async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();
  await page.goto('http://127.0.0.1:8765' + WORKBENCH);
  await expect(page.locator('.no-script')).toContainText('JavaScript is needed');
  await expect(page.locator('.no-script a')).toHaveAttribute('href', WORKBENCH + '/docs');
  await context.close();
});

for (const timezoneId of ['UTC', 'Europe/Berlin']) {
  test(`charts, candidate markers and linked hover use UTC in ${timezoneId}`, async ({ browser }) => {
  const context = await browser.newContext({ timezoneId });
  const page = await context.newPage();
  await page.goto('http://127.0.0.1:8765' + WORKBENCH);
  await runExample(page);
  await expect(page.locator('#orbitChart .main-svg').first()).toBeVisible();
  const result = await downloadPackage(page);
  const plotted = await page.evaluate(() => {
    const orbit = document.getElementById('orbitChart');
    const rate = document.getElementById('rateChart');
    const candidateTrace = rate.data.findIndex(trace => trace.name === 'Candidate epoch');
    return {
      orbitEpoch: orbit.calcdata[0][0].x,
      rateEpoch: rate.calcdata[0][1].x,
      candidateEpoch: rate.calcdata[candidateTrace][0].x,
      markerEpoch: Date.parse(orbit.layout.shapes[0].x0)
    };
  });
  expect(plotted.orbitEpoch).toBe(Date.parse(result.rows[0].epoch_utc));
  expect(plotted.rateEpoch).toBe(Date.parse(result.rows[1].epoch_utc));
  expect(plotted.candidateEpoch).toBe(Date.parse(result.events[0].strongest_epoch_utc));
  expect(plotted.markerEpoch).toBe(plotted.candidateEpoch);
  await expect(page.locator('#orbitChart .xtitle')).toHaveText('Epoch UTC');
  await expect(page.locator('#orbitChart .ytitle')).toHaveText('Semi-major axis [km]');
  await expect(page.locator('#rateChart .ytitle')).toHaveText('Δa/Δt [km/day]');
  await page.locator('#orbitChart .scatterlayer .trace .point').nth(5).hover({ force: true });
  await expect.poll(() => page.evaluate(() => (document.getElementById('rateChart')._hoverdata || []).map(point => point.pointNumber))).toContain(5);
  await context.close();
});

}


test('historical acquisition evidence survives download and reopening until manual editing', async ({ page }) => {
  await openWorkbench(page);
  await runExample(page);
  const demonstration = await downloadPackage(page);
  const records = demonstration.normalized_input_omm;
  const dates = records.map(row => new Date(row.EPOCH).toISOString().slice(0, 10)).sort();
  const range = { start: dates[0], end: dates[dates.length - 1] };
  const acquired = new Date(Date.parse(range.end + 'T00:00:00Z') + 86400000).toISOString().replace('.000Z', 'Z');
  const canonical = value => Array.isArray(value) ? value.map(canonical) : value && typeof value === 'object'
    ? Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])])) : value;
  const digest = value => require('node:crypto').createHash('sha256').update(JSON.stringify(canonical(value))).digest('hex');
  const metadata = {
    schema_version: 1, provider: 'Space-Track', source_class: 'GP_HISTORY', policy: 'retained-history-v1',
    norad: demonstration.object_id, requested_range: range,
    records_sha256: digest(records), cache_snapshot_sha256: digest({ records, range, acquired }),
    cache_updated_at: acquired, retrieval_status: 'recorded',
    acquisitions: [{
      kind: 'upstream-fetch', source_class: 'GP_HISTORY', ...range,
      retrieved_at: acquired, records_sha256: digest(records)
    }]
  };
  let requests = 0;
  await page.route('**/history?**', async route => {
    requests++;
    await route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({
        ok: true, cached: true, records, retrieved_at: acquired,
        served_at: new Date(Date.parse(acquired) + requests * 86400000).toISOString(), data_provenance: metadata
      })
    });
  });
  await page.locator('#heroHistoryButton').click();
  await page.locator('#publicNorad').fill(demonstration.object_id);
  await page.locator('#historyStart').fill(range.start);
  await page.locator('#historyEnd').fill(range.end);
  await page.locator('#loadHistory').click();
  await expect(page.locator('#historyFetchHint')).toContainText(acquired);
  await expect(page.locator('#run')).toHaveText('Analysis up to date');
  const first = await downloadPackage(page);
  expect(first.data_provenance.sources).toHaveLength(1);
  expect(first.data_provenance.sources[0].metadata).toEqual(metadata);
  expect(first.evidence_note).toContain(acquired);
  expect(JSON.stringify(first.data_provenance)).not.toContain('served_at');

  await page.locator('#loadHistory').click();
  await expect(page.locator('#loadHistory')).toBeEnabled();
  const second = await downloadPackage(page);
  expect(requests).toBe(2);
  expect(second.data_provenance).toEqual(first.data_provenance);
  expect(second.run_id).toBe(first.run_id);

  await page.locator('#manualInputDetails > summary').click();
  await page.locator('#fileInput').setInputFiles({
    name: 'acquired-history.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(first))
  });
  await expect(page.locator('#fileImportHint')).toContainText(/restor|accepted/i);
  expect((await downloadPackage(page)).data_provenance).toEqual(first.data_provenance);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.locator('#technicalDetails > summary').click();
  await page.getByText('Run and reproducibility details', { exact: true }).click();
  await expect(page.locator('#audit')).toContainText(acquired);
  await expectNoOverflow(page);

  const original = await page.locator('#tles').inputValue();
  await page.locator('#tles').fill(original + '\n');
  await page.locator('#run').click();
  const edited = await downloadPackage(page);
  expect(edited.data_provenance).toBeNull();
  expect(edited.run_id).toBe(first.run_id);
});


test('cached documents recover through the compatibility entry and immutable modules', async ({ page }) => {
  const errors = [];
  const modules = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => {
    const pathname = new URL(request.url()).pathname;
    if (pathname.startsWith(WORKBENCH + '/app/')) modules.push(pathname);
  });
  await page.route('**/satsift/', async route => {
    const response = await route.fetch();
    const current = await response.text();
    const script = /<script\b[^>]*src="\/satsift\/app\/[^\"]+"[^>]*><\/script>/g;
    const tags = current.match(script) || [];
    expect(tags).toHaveLength(7);
    const body = current.replace(script, '').replace('</body>',
      '<script defer src="/satsift/app-3.4.js?v=c8eb05db9c48"></script>\n</body>');
    await route.fulfill({ response, body });
  });
  await openWorkbench(page);
  await runExample(page, 'leo');
  const saved = await downloadPackage(page);
  expect(saved.workbench_version).toBe('3.5.0');
  expect(saved.normalized_input_omm).toHaveLength(16);
  expect(modules).toHaveLength(6);
  expect(new Set(modules).size).toBe(6);
  expect(modules.every(value => /\/app\/[a-z-]+-[0-9a-f]{12}\.js$/.test(value))).toBe(true);
  expect(await page.evaluate(() => globalThis.SMDApplicationBoot.status)).toBe('ready');
  expect(errors).toEqual([]);
});

test('a missing application module reports startup failure and disables analysis', async ({ page }) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/app/detection-*.js', route => route.abort('failed'));
  await page.goto(WORKBENCH);
  await expect(page.locator('#status')).toHaveText('The application could not load completely. Reload this page and try again.');
  await expect(page.locator('#status')).toHaveAttribute('role', 'alert');
  await expect(page.locator('#run')).toBeDisabled();
  expect(await page.evaluate(() => globalThis.SMDApplicationBoot.status)).toBe('failed');
  expect(errors).toEqual([]);
});
