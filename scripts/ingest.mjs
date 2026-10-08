import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { projectRoot as root, databasePath } from '../backend/paths.mjs';
import { openDatabase, importDocuments } from '../backend/db.mjs';

try {
  process.loadEnvFile(resolve(root, '.env'));
} catch (e) {
  if (e.code !== 'ENOENT') throw e;
}
const path = process.argv[2];
if (!path) {
  console.error('Usage: node scripts/ingest.mjs backend/knowledge/seed.json');
  process.exitCode = 1;
} else {
  const raw = await readFile(resolve(path), 'utf8');
  const db = openDatabase(databasePath());
  try {
    console.log(
      JSON.stringify(
        importDocuments(db, JSON.parse(raw.replace(/^\uFEFF/, ''))),
        null,
        2,
      ),
    );
  } finally {
    db.close();
  }
}
