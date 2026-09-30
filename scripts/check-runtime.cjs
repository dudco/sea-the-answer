'use strict';

// Test the actual features used by this app, without touching the project DB.
function checkRuntime(loadSqlite = () => require('node:sqlite')) {
  let db;
  try {
    if (typeof process.loadEnvFile !== 'function') throw new Error('process.loadEnvFile is unavailable');
    const { DatabaseSync } = loadSqlite();
    db = new DatabaseSync(':memory:');
    db.exec("CREATE VIRTUAL TABLE runtime_fts_probe USING fts5(terms); INSERT INTO runtime_fts_probe(terms) VALUES ('haedap');");
    const row = db.prepare("SELECT bm25(runtime_fts_probe) AS score FROM runtime_fts_probe WHERE runtime_fts_probe MATCH ?").get('haedap');
    if (!row || !Number.isFinite(row.score)) throw new Error('FTS5 search or BM25 ranking is unavailable');
    if (typeof db.isTransaction !== 'boolean') throw new Error('SQLite transaction state support is unavailable');
    return { version: process.version, sqlite: true, fts5: true };
  } catch (cause) {
    const error = new Error(`This runtime (${process.version}) cannot run Haedap: SQLite with FTS5/BM25 is required. Install official Node.js 24 LTS, close old terminals, and run start.cmd again. Detail: ${cause.message}`);
    error.code = 'HAEDAP_RUNTIME_UNSUPPORTED';
    throw error;
  } finally {
    if (db) db.close();
  }
}

module.exports = { checkRuntime };
if (require.main === module) {
  try { const result = checkRuntime(); console.log(`Runtime ${result.version}: SQLite + FTS5 ready`); }
  catch (error) { console.error(error.message); process.exitCode = 1; }
}
