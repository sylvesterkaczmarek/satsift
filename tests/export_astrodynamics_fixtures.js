'use strict';

const { loadBrowserApp } = require('../tools/load_browser_app');

const vm = require('vm');

const context = { Date, Math, Number, String, Array, console, window: {} };
vm.createContext(context);
context.api = loadBrowserApp(context, { start: false });

const fixtures = {};
for (const kind of ['quiet', 'leo', 'geo', 'radial', 'cross', 'finite', 'sparse']) {
  fixtures[kind] = context.api.exampleTles(kind);
}

process.stdout.write(JSON.stringify(fixtures, null, 2));
