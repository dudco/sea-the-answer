import test from 'node:test';
import assert from 'node:assert/strict';
import {
  mkdtempSync,
  mkdirSync,
  writeFileSync,
  rmSync,
  readFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { databasePath } from '../paths.mjs';

function fixture(t) {
  const root = mkdtempSync(join(tmpdir(), 'haedap-layout-'));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const put = (name) => {
    const path = join(root, name);
    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, 'preserved');
    return path;
  };
  return { root, put };
}

test('fresh workspace defaults to backend/data; relocated DB stays selected', (t) => {
  const { root, put } = fixture(t);
  assert.equal(
    databasePath({ root, configured: '' }),
    resolve(root, 'backend/data/haedap.sqlite'),
  );
  const moved = put('backend/data/haedap.sqlite');
  assert.equal(databasePath({ root, configured: '' }), moved);
});

test('legacy root data is reused without rewriting or removing it', (t) => {
  const { root, put } = fixture(t),
    previous = put('data/haedap.sqlite');
  assert.equal(databasePath({ root, configured: '' }), previous);
  assert.equal(readFileSync(previous, 'utf8'), 'preserved');
});

test('explicit DB paths preserve root-relative and absolute semantics', (t) => {
  const { root, put } = fixture(t),
    external = put('custom/db.sqlite');
  assert.equal(
    databasePath({ root, configured: 'custom/db.sqlite' }),
    external,
  );
  assert.equal(databasePath({ root, configured: external }), external);
  assert.equal(
    databasePath({ root, configured: 'data/haedap.sqlite' }),
    resolve(root, 'data/haedap.sqlite'),
  );
});

test('two default databases require an explicit choice and preserve both files', (t) => {
  const { root, put } = fixture(t);
  const previous = put('data/haedap.sqlite'),
    current = put('backend/data/haedap.sqlite');
  assert.throws(() => databasePath({ root, configured: '' }), /HAEDAP_DB_PATH/);
  assert.equal(
    databasePath({ root, configured: 'backend/data/haedap.sqlite' }),
    current,
  );
  for (const path of [previous, current])
    assert.equal(readFileSync(path, 'utf8'), 'preserved');
});
