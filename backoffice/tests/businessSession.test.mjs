import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { spawnSync } from 'node:child_process';

test('business credentials stay tab scoped and reject stale/cross-account context installation', async () => {
  const root = resolve(import.meta.dirname, '..');
  const directory = mkdtempSync(resolve(tmpdir(), 'apex-business-context-'));
  const storage = () => { const values = new Map(); return {
    getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value), removeItem: key => values.delete(key),
  }; };
  globalThis.localStorage = storage(); globalThis.sessionStorage = storage();
  globalThis.window = new EventTarget();
  localStorage.setItem('pos_offline_queue', 'retain');
  localStorage.setItem('backoffice_token', 'old-reusable-token');
  try {
    writeFileSync(resolve(directory, 'package.json'), '{"type":"module"}');
    const compiled = spawnSync(resolve(root, 'node_modules/.bin/tsc'), ['--ignoreConfig', '--target', 'ES2023', '--module', 'ESNext', '--skipLibCheck', '--outDir', directory, resolve(root, 'src/api/businessSession.ts')], { cwd: root, encoding: 'utf8' });
    assert.equal(compiled.status, 0, compiled.stdout + compiled.stderr);
    const session = await import(pathToFileURL(resolve(directory, 'businessSession.js')));
    assert.equal(localStorage.getItem('backoffice_token'), null);
    const context = user => ({token: 'short-access-' + user, company_id: 'same-tenant', user: {id: user}});
    assert.equal(session.installBusinessContext(context('owner-a')), true);
    assert.equal(localStorage.getItem('backoffice_token'), null);
    assert.equal(sessionStorage.getItem('backoffice_token'), 'short-access-owner-a');
    const stale = session.contextGeneration();
    session.clearBusinessContext();
    assert.equal(session.installBusinessContext(context('owner-a'), stale), false);
    assert.equal(session.installBusinessContext(context('owner-b')), true);
    assert.equal(session.installBusinessContext(context('owner-a')), false);
    assert.equal(sessionStorage.getItem('backoffice_token'), null);
    assert.equal(localStorage.getItem('pos_offline_queue'), 'retain');
  } finally { rmSync(directory, { recursive: true, force: true }); }
});
