import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import runtime from '../scripts/check-runtime.cjs';

test('runtime preflight exercises actual in-memory FTS5 search and BM25', () => {
  assert.equal(runtime.checkRuntime().fts5, true);
  const result = spawnSync(process.execPath, [fileURLToPath(new URL('../scripts/check-runtime.cjs', import.meta.url))], { encoding: 'utf8' });
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /SQLite \+ FTS5 ready/);
});

test('runtime preflight rejects SQLite without FTS5, explains upgrade, and closes the probe', () => {
  let closed = false, openedPath;
  class WithoutFts {
    constructor(path) { openedPath = path; }
    exec() { throw new Error('no such module: fts5'); }
    close() { closed = true; }
  }
  assert.throws(() => runtime.checkRuntime(() => ({ DatabaseSync: WithoutFts })), error =>
    error.code === 'HAEDAP_RUNTIME_UNSUPPORTED' && /Node.js 24 LTS/.test(error.message) && /no such module: fts5/.test(error.message));
  assert.equal(openedPath, ':memory:');
  assert.equal(closed, true);
});
