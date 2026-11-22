(function () {
  'use strict';

  // A cached earlier document may load only this compatibility entrypoint.
  // New documents preload the same immutable module assets with ordered defer.
  if (globalThis.SMDApplicationBoot) return;
  const bootState = { status: 'loading' };
  globalThis.SMDApplicationBoot = bootState;

  // BEGIN MODULE ASSETS
  const MODULE_ASSETS = Object.freeze([
  {
    "name": "common",
    "url": "/satellite-maneuver-detector/app/common-bc423f074a86.js",
    "integrity": "sha256-vEI/B0qG4V6Uu4TybLzdwSXKj8y1IqxGTkhxTDYn+5w="
  },
  {
    "name": "orbital-input",
    "url": "/satellite-maneuver-detector/app/orbital-input-e1b787fca1e2.js",
    "integrity": "sha256-4beH/KHil20I0a8aBwkrIknvj1vn0wHMABUzvUpXfj0="
  },
  {
    "name": "benchmark",
    "url": "/satellite-maneuver-detector/app/benchmark-91d4848f8ca3.js",
    "integrity": "sha256-kdSEj4yjucZ20x1rnOklD6cGVP5mnpHe3U6jKN3WOhU="
  },
  {
    "name": "packages",
    "url": "/satellite-maneuver-detector/app/packages-1ca01aa7ed42.js",
    "integrity": "sha256-HKAap+1CX7Einb16WS6hjDq25oaM11FR5yAvrS+L0WU="
  },
  {
    "name": "detection",
    "url": "/satellite-maneuver-detector/app/detection-133da300883d.js",
    "integrity": "sha256-Ez2jAIg9dFkhj/iGC/CUokXNEdpX+j6k+cfPey5R+zg="
  },
  {
    "name": "interface",
    "url": "/satellite-maneuver-detector/app/interface-3a88f4921deb.js",
    "integrity": "sha256-Ooj0kh3rNIFAFoTTdRnW5mW+mq3aDHQxFUaio11Z/vQ="
  }
]);
// END MODULE ASSETS

  function moduleReady(name) {
    return globalThis.SMDModules && typeof globalThis.SMDModules[name] === 'function';
  }

  function startApplication() {
    if (!MODULE_ASSETS.every(asset => moduleReady(asset.name))) {
      throw new Error('The application module set is incomplete.');
    }
    const registry = Object.freeze(globalThis.SMDModules);
    const common = registry.common();
    const orbitalInput = registry['orbital-input'](common);
    const benchmark = registry.benchmark(common, orbitalInput);
    const packages = registry.packages(common, orbitalInput, benchmark);
    const workbench = registry.interface(common, orbitalInput, benchmark, packages, registry.detection);
    workbench.start();
    bootState.status = 'ready';
  }

  function reportLoadFailure(error) {
    bootState.status = 'failed';
    const status = document.getElementById('status');
    if (status) {
      status.textContent = 'The application could not load completely. Reload this page and try again.';
      status.className = 'badge err';
      status.setAttribute('role', 'alert');
    }
    const button = document.getElementById('run');
    if (button) button.disabled = true;
    if (globalThis.console && typeof console.error === 'function') console.error('Workbench startup failed.', error);
  }

  function loadModule(asset) {
    return new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = asset.url;
      script.integrity = asset.integrity;
      script.crossOrigin = 'anonymous';
      script.async = false;
      script.onload = () => moduleReady(asset.name) ? resolve() : reject(new Error('A required module did not register.'));
      script.onerror = () => reject(new Error('A required application asset could not be loaded.'));
      document.head.appendChild(script);
    });
  }

  if (MODULE_ASSETS.every(asset => moduleReady(asset.name))) {
    try { startApplication(); } catch (error) { reportLoadFailure(error); }
  } else {
    MODULE_ASSETS.reduce((pending, asset) => pending.then(() => moduleReady(asset.name) ? undefined : loadModule(asset)), Promise.resolve())
      .then(startApplication, reportLoadFailure).catch(reportLoadFailure);
  }
})();
