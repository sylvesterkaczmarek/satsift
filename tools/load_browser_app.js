'use strict';

// Node-only verification support. Browser execution never evaluates assembled source.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const PREFIX = '/satellite-maneuver-detector/app/';
const MODULE_SOURCES = Object.freeze(['app/common.js', 'app/orbital-input.js', 'app/benchmark.js',
  'app/packages.js', 'app/detection.js', 'app/interface.js']);

function sourceFiles(root = process.cwd()) {
  const manifestPath = path.join(root, 'browser-assets.json');
  if (!fs.existsSync(manifestPath)) {
    const source = fs.readFileSync(path.join(root, 'app-3.4.js'), 'utf8');
    assert(source.includes('  function analyzeRaw('), 'A modular application requires its asset manifest.');
    return ['app-3.4.js'];
  }
  const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
  assert.equal(manifest.schema, 'smd-browser-assets-v1');
  assert.deepEqual(manifest.module_sources, MODULE_SOURCES, 'Unknown or reordered browser source modules require explicit review.');
  assert.equal(manifest.entry_source, 'app-3.4.js');
  const files = [...manifest.module_sources, manifest.entry_source];
  assert.equal(new Set(files).size, files.length, 'Browser source files must be unique.');
  for (const file of manifest.module_sources) {
    assert.match(file, /^app\/[a-z][a-z-]*\.js$/, 'Browser module sources must be explicit relative JavaScript paths.');
  }
  return files;
}

function browserAssets(root = process.cwd()) {
  return sourceFiles(root).map(source => {
    const bytes = fs.readFileSync(path.join(root, source));
    const digest = crypto.createHash('sha256').update(bytes).digest();
    const sha256 = digest.toString('hex');
    const name = source === 'app-3.4.js' ? 'bootstrap' : path.basename(source, '.js');
    return {
      source, name, sha256,
      target: `app/${name}-${sha256.slice(0, 12)}.js`,
      url: `${PREFIX}${name}-${sha256.slice(0, 12)}.js`,
      integrity: `sha256-${digest.toString('base64')}`,
    };
  });
}

function readBrowserSource(root = process.cwd()) {
  // Inspection only: the VM loader below executes each real module separately.
  return sourceFiles(root).map(source => fs.readFileSync(path.join(root, source), 'utf8')).join('\n');
}

function legacyApiNames(source) {
  return [...source.matchAll(/^  (?:async )?function ([A-Za-z_$][\w$]*)\(/gm)].map(match => match[1])
    .concat([...source.matchAll(/^  const ([A-Z][A-Z_0-9]*) = /gm)].map(match => match[1]));
}

function loadBrowserApp(context, { root = process.cwd(), start = true, hooks = '', configureModules = null, configureLegacySource = null } = {}) {
  const files = sourceFiles(root);
  if (files.length === 1) {
    // Kept for read-only comparison with an explicitly selected historical snapshot.
    const originalSource = fs.readFileSync(path.join(root, files[0]), 'utf8');
    const source = configureLegacySource ? configureLegacySource(originalSource) : originalSource;
    const cutoff = source.indexOf("  byId('run').addEventListener");
    const closing = source.lastIndexOf('\n})();');
    assert(cutoff > 0 && closing > cutoff, 'Historical application boundaries are required.');
    const exposed = `\n${hooks}\nglobalThis.__SMD_TEST_APPLICATION__ = {${legacyApiNames(source).join(',')}};\n`;
    const code = start
      ? source.slice(0, closing) + exposed + source.slice(closing)
      : source.slice(0, cutoff) + exposed + '\n})();';
    vm.runInContext(code, context, { filename: files[0] });
    return context.__SMD_TEST_APPLICATION__;
  }

  const assets = browserAssets(root);
  const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
  const urls = [...html.matchAll(/<script\b[^>]*\bsrc="([^"]+)"[^>]*>/g)]
    .map(match => match[1]).filter(url => url.startsWith(PREFIX));
  assert.deepEqual(urls, assets.map(asset => asset.url), 'The VM must execute the complete production module order.');
  for (const asset of assets) {
    let source = fs.readFileSync(path.join(root, asset.source), 'utf8');
    if (asset.name === 'interface' && hooks) {
      const marker = '// Interface API.';
      assert.equal(source.split(marker).length, 2, 'Interface hook boundary must be unique.');
      // Bind pure exports only inside the injected verification closure. UI functions
      // and mutable state still resolve to the real interface's surrounding scope.
      const localFunctions = new Set([...source.matchAll(/^  (?:async )?function ([A-Za-z_$][\w$]*)\(/gm)].map(match => match[1]));
      const pureNames = [...new Set(assets.filter(item => !['interface', 'bootstrap'].includes(item.name))
        .flatMap(item => legacyApiNames(fs.readFileSync(path.join(root, item.source), 'utf8'))))]
        .filter(name => !localFunctions.has(name));
      const instrument = `(() => { const { ${pureNames.join(',')} } = { ...common, ...orbitalInput, ...benchmark, ...packages, ...detection };\n${hooks}\n})();`;
      source = source.replace(marker, `${instrument}\n  ${marker}`);
    }
    if (asset.name === 'bootstrap') {
      if (configureModules) configureModules(context.SMDModules);
      const marker = 'workbench.start();';
      assert.equal(source.split(marker).length, 2, 'The production start call must be unique.');
      source = source.replace(marker,
        `globalThis.__SMD_TEST_APPLICATION__ = workbench;${start ? marker : ''}`);
    }
    vm.runInContext(source, context, { filename: asset.source });
  }
  assert(context.__SMD_TEST_APPLICATION__, 'The production entry must construct the workbench synchronously when its modules are present.');
  return context.__SMD_TEST_APPLICATION__;
}

module.exports = { sourceFiles, browserAssets, readBrowserSource, loadBrowserApp };
