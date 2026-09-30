import { DatabaseSync } from 'node:sqlite';
import { mkdirSync } from 'node:fs';
import { dirname } from 'node:path';
import { randomUUID } from 'node:crypto';
import { prepareDocument, tokens } from './knowledge.mjs';
import { object, string, requireValue } from './validation.mjs';
import runtime from '../scripts/check-runtime.cjs';

let runtimeChecked = false;

export function openDatabase(path) {
  if (!runtimeChecked) { runtime.checkRuntime(); runtimeChecked = true; }
  if (path !== ':memory:') mkdirSync(dirname(path), { recursive: true });
  const db = new DatabaseSync(path);
  db.exec(`PRAGMA foreign_keys=ON; PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000;
    CREATE TABLE IF NOT EXISTS documents (
      id TEXT PRIMARY KEY, logical_id TEXT NOT NULL, hash TEXT NOT NULL, title TEXT NOT NULL,
      kind TEXT NOT NULL, url TEXT, reference TEXT NOT NULL, version TEXT NOT NULL,
      reviewed_at TEXT NOT NULL, language TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, imported_at TEXT NOT NULL
    );
    CREATE UNIQUE INDEX IF NOT EXISTS one_active_revision ON documents(logical_id) WHERE active=1;
    CREATE TABLE IF NOT EXISTS chunks (
      id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id), position INTEGER NOT NULL,
      heading TEXT NOT NULL, text TEXT NOT NULL
    );
    CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(chunk_id UNINDEXED, terms);
    CREATE TABLE IF NOT EXISTS reports (
      id TEXT PRIMARY KEY, title TEXT NOT NULL, type TEXT NOT NULL, text TEXT NOT NULL,
      sources TEXT NOT NULL, version INTEGER NOT NULL, updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS tool_runs (
      id TEXT PRIMARY KEY, tool TEXT NOT NULL, version TEXT NOT NULL, input TEXT NOT NULL,
      output TEXT NOT NULL, created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS queries (
      id TEXT PRIMARY KEY, question TEXT NOT NULL, response TEXT NOT NULL, created_at TEXT NOT NULL
    );
    PRAGMA user_version=1;`);
  return db;
}
export function importDocuments(db, input) {
  requireValue(Array.isArray(input) && input.length > 0 && input.length <= 100, '1~100개 문서의 JSON 배열이 필요합니다.');
  const docs = input.map(prepareDocument);
  requireValue(new Set(docs.map(d => d.id)).size === docs.length, '한 번에 같은 문서 ID를 중복 등록할 수 없습니다.');
  const result = [];
  const ownTransaction = !db.isTransaction;
  if (ownTransaction) db.exec('BEGIN IMMEDIATE');
  try {
    for (const d of docs) {
      const old = db.prepare('SELECT id, hash FROM documents WHERE logical_id=? AND active=1').get(d.id);
      if (old?.hash === d.hash) { result.push({ id: old.id, status: 'unchanged' }); continue; }
      db.prepare('UPDATE documents SET active=0 WHERE logical_id=?').run(d.id);
      const existing = db.prepare('SELECT id FROM documents WHERE id=?').get(d.revisionId);
      if (existing) db.prepare('UPDATE documents SET active=1 WHERE id=?').run(d.revisionId);
      else {
        db.prepare('INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?,?,1,?)').run(d.revisionId, d.id, d.hash, d.title, d.kind, d.url, d.reference, d.version, d.reviewedAt, d.language, new Date().toISOString());
        for (const c of d.chunks) {
          db.prepare('INSERT INTO chunks VALUES (?,?,?,?,?)').run(c.id, d.revisionId, c.position, c.heading, c.text);
          db.prepare('INSERT INTO chunks_fts(chunk_id,terms) VALUES (?,?)').run(c.id, c.terms);
        }
      }
      result.push({ id: d.revisionId, status: old ? 'updated' : 'created', chunks: d.chunks.length });
    }
    if (ownTransaction) db.exec('COMMIT');
  } catch (error) { if (ownTransaction) db.exec('ROLLBACK'); throw error; }
  return result;
}
export function listDocuments(db) {
  return db.prepare('SELECT * FROM documents ORDER BY active DESC, title, imported_at DESC').all().map(d => ({ ...d,
    sections: db.prepare('SELECT id, heading, text, position FROM chunks WHERE document_id=? ORDER BY position').all(d.id) }));
}
export function retrieve(db, question, { kind = 'all', limit = 5, allowedIds } = {}) {
  string(question, '질문', 2000);
  requireValue(['all', 'imo', 'manual'].includes(kind), '문서 필터가 올바르지 않습니다.');
  if (Array.isArray(allowedIds) && !allowedIds.length) return [];
  const accessSql = Array.isArray(allowedIds) ? `AND d.id IN (${allowedIds.map(() => '?').join(',')})` : '';
  const terms = tokens(question).slice(0, 80);
  if (!terms.length) return [];
  // No raw user SQL/FTS syntax: only normalized alphanumeric terms are quoted.
  const match = terms.map(t => `"${t}"`).join(' OR ');
  const rows = db.prepare(`SELECT c.*, d.title, d.kind, d.url, d.reference, d.version, d.reviewed_at, d.hash,
      bm25(chunks_fts) AS rank FROM chunks_fts
      JOIN chunks c ON c.id=chunks_fts.chunk_id JOIN documents d ON d.id=c.document_id
      WHERE chunks_fts MATCH ? AND d.active=1 ${accessSql} AND (?='all' OR (?='imo' AND d.kind='official-summary') OR (?='manual' AND d.kind!='official-summary'))
      ORDER BY rank LIMIT 30`).all(match, ...(allowedIds || []), kind, kind, kind);
  return rows.map(r => {
    const bodyTerms = new Set(tokens(`${r.heading} ${r.text}`));
    const matched = terms.filter(t => bodyTerms.has(t));
    const concept = matched.some(t => t.startsWith('concept'));
    const substantial = matched.filter(t => !t.startsWith('concept') && t.length >= 3);
    return { ...r, matched, supported: concept || substantial.length >= 1 || matched.length >= 2 };
  }).filter(r => r.supported).slice(0, limit).map(({ supported, ...r }) => r);
}
export function saveReport(db, input) {
  object(input);
  const id = string(input.id || 'current', '보고서 ID', 80);
  requireValue(/^[a-zA-Z0-9-]+$/.test(id), '보고서 ID가 올바르지 않습니다.');
  const title = string(input.title, '제목', 120), text = string(input.text, '내용', 200000);
  requireValue(['규정 검토', '일일 운항', '배출량 검토', '종합 검토'].includes(input.type), '보고서 유형이 올바르지 않습니다.');
  requireValue(Array.isArray(input.sources) && input.sources.length <= 100 && input.sources.every(s => typeof s === 'string'), '근거 ID 배열이 필요합니다.');
  requireValue(Number.isInteger(input.version) && input.version >= 0, '보고서 버전이 필요합니다.');
  const sources = [...new Set(input.sources)];
  // Legacy UI document IDs are explicitly accepted as sample evidence.
  for (const s of sources) requireValue(['sulfur','cii','checklist','noon','carbon'].includes(s) || !!db.prepare('SELECT id FROM documents WHERE id=?').get(s), '존재하지 않는 근거입니다.');
  const ownTransaction = !db.isTransaction;
  if (ownTransaction) db.exec('BEGIN IMMEDIATE');
  try {
    const old = db.prepare('SELECT version FROM reports WHERE id=?').get(id);
    requireValue((old?.version || 0) === input.version, '다른 창에서 초안이 변경되었습니다. DB 초안을 다시 불러온 뒤 저장하세요.', 'VERSION_CONFLICT', 409);
    const version = input.version + 1, updatedAt = new Date().toISOString();
    db.prepare(`INSERT INTO reports VALUES (?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
      title=excluded.title,type=excluded.type,text=excluded.text,sources=excluded.sources,version=excluded.version,updated_at=excluded.updated_at`)
      .run(id, title, input.type, text, JSON.stringify(sources), version, updatedAt);
    if (ownTransaction) db.exec('COMMIT');
    return { id, title, type: input.type, text, sources, version, updatedAt };
  } catch (error) { if (ownTransaction) db.exec('ROLLBACK'); throw error; }
}
export function getReport(db, id = 'current') {
  const row = db.prepare('SELECT * FROM reports WHERE id=?').get(id);
  return row ? { ...row, sources: JSON.parse(row.sources), updatedAt: row.updated_at } : null;
}
export function logTool(db, name, input, output) {
  const id = randomUUID();
  db.prepare('INSERT INTO tool_runs VALUES (?,?,?,?,?,?)').run(id, name, output.version, JSON.stringify(input), JSON.stringify(output), new Date().toISOString());
  return { id, name, ...output };
}
export function logQuery(db, question, response) {
  const id = randomUUID();
  db.prepare('INSERT INTO queries VALUES (?,?,?,?)').run(id, question, JSON.stringify(response), new Date().toISOString());
  return { id, ...response };
}
