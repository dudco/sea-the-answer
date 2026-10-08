import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve, sep, basename } from 'node:path';
import { openDatabase, importDocuments, retrieve, listDocuments, getReport, saveReport } from '../db.mjs';
import { prepareDocument } from '../knowledge.mjs';
import { calculateEmissions, voyageTime, runTool } from '../tools.mjs';
import { answerQuestion } from '../rag.mjs';

const seed = JSON.parse(readFileSync(new URL('../knowledge/seed.json', import.meta.url), 'utf8'));
function fixture(t) { const db = openDatabase(':memory:'); importDocuments(db, seed); t.after(() => db.close()); return db; }
const draft = { title: '검토 초안', type: '규정 검토', text: '담당자 검토 필요', sources: [], version: 0 };

test('document import is idempotent and preserves decimal facts', t => {
  const db = fixture(t);
  assert.ok(importDocuments(db, seed).every(r => r.status === 'unchanged'));
  assert.equal(db.prepare('SELECT count(*) n FROM chunks').get().n, 6);
  assert.ok(retrieve(db, '황 함유량')[0].text.includes('0.50%'));
  assert.ok(prepareDocument(seed[0]).chunks[0].text.includes('0.10%'));
});
test('Korean and English questions retrieve evidence, filters constrain the search itself', t => {
  const db = fixture(t);
  for (const q of ['황 함유량 기준', 'fuel sulphur ECA limit', '지중해 적용 시점', 'CII D 등급 시정조치', 'CII corrective action', '연료 전환 점검표']) {
    const hits = retrieve(db, q); assert.ok(hits.length, q); assert.ok(hits.every(h => h.document_id && h.id && h.hash));
  }
  assert.match(retrieve(db, 'CII D 등급 시정조치')[0].text, /3년 연속/);
  assert.match(retrieve(db, '지중해 적용 시점')[0].text, /2025년 5월 1일/);
  assert.ok(retrieve(db, '연료 전환', { kind: 'imo' }).every(h => h.kind === 'official-summary'));
  assert.ok(retrieve(db, 'CII 계산', { kind: 'manual' }).every(h => h.kind !== 'official-summary'));
  assert.deepEqual(retrieve(db, '초콜릿 케이크 레시피'), []);
  assert.deepEqual(retrieve(db, '" OR * - ()'), []);
});
test('revision replacement keeps old report citations and only searches the new revision', t => {
  const db = fixture(t), old = listDocuments(db).find(d => d.logical_id === 'imo-sulphur');
  saveReport(db, { ...draft, sources: [old.id] });
  const updated = structuredClone(seed[0]); updated.version = '2'; updated.sections = [{ heading: '새 규정', text: '황 함유량 개정 검토를 위한 교체 문서입니다.' }];
  importDocuments(db, [updated]);
  assert.equal(listDocuments(db).find(d => d.id === old.id).active, 0);
  assert.equal(getReport(db).sources[0], old.id);
  assert.ok(retrieve(db, '황 함유량').every(e => e.document_id !== old.id));
});
test('invalid ingestion is atomic and long paragraphs are bounded', t => {
  const db = fixture(t), invalid = structuredClone(seed[0]); invalid.id = 'bad'; invalid.url = 'javascript:alert(1)';
  const valid = { ...seed[0], id: 'new-doc' };
  assert.throws(() => importDocuments(db, [valid, invalid]));
  assert.equal(listDocuments(db).length, 4);
  assert.throws(() => importDocuments(db, [seed[0], seed[0]]));
  const doc = prepareDocument({ ...seed[0], sections: [{ heading: 'long', text: '항해'.repeat(2000) }] });
  assert.ok(doc.chunks.every(c => c.text.length <= 900));
});
test('SQLite persists reports, citations and tool history across reopen; concurrent edit conflicts', () => {
  const dir = mkdtempSync(join(tmpdir(), 'haedap-test-')), path = join(dir, 'test.sqlite');
  let db = openDatabase(path);
  try {
    importDocuments(db, seed);
    const report = saveReport(db, draft); assert.equal(report.version, 1);
    assert.throws(() => saveReport(db, draft), e => e.status === 409);
    assert.throws(() => saveReport(db, { ...draft, sources: ['fake'], version: 1 }));
    runTool(db, 'calculate_emissions', { fuel: 5400, factor: 3.114, dwt: 50000, distance: 60000 });
    db.close(); db = openDatabase(path);
    assert.equal(getReport(db).text, draft.text);
    assert.equal(db.prepare('SELECT count(*) n FROM tool_runs').get().n, 1);
    assert.equal(listDocuments(db).length, 4);
  } finally {
    db.close();
    assert.ok(resolve(dir).startsWith(resolve(tmpdir()) + sep) && basename(dir).startsWith('haedap-test-'));
    rmSync(dir, { recursive: true, force: true });
  }
});
test('emissions tool validates units and rejects coercion, overflow and zero denominators', () => {
  const args = { fuel: 5400, factor: 3.114, dwt: 50000, distance: 60000 };
  const r = calculateEmissions(args);
  assert.ok(Math.abs(r.emission - 16815.6) < 1e-8); assert.ok(Math.abs(r.intensity - 5.6052) < 1e-8);
  assert.equal(r.officialCiiRating, null);
  assert.equal(calculateEmissions({ ...args, fuel: 0 }).emission, 0);
  for (const change of [{ fuel: -1 }, { fuel: '5400' }, { factor: NaN }, { distance: 0 }, { dwt: 0 }, { factor: 11 }, { dwt: 5e-324, distance: 5e-324 }]) {
    assert.throws(() => calculateEmissions({ ...args, ...change }));
  }
});
test('UTC elapsed time stays correct across east/west date changes', () => {
  const args = { start: '2026-09-18T00:00:00Z', end: '2026-09-18T01:00:00Z', before: 720, after: -720 };
  assert.equal(voyageTime(args).elapsedHours, 1); assert.equal(voyageTime(args).clockHours, -23);
  assert.equal(voyageTime({ ...args, before: -720, after: 720 }).clockHours, 25);
  assert.throws(() => voyageTime({ ...args, start: '2026-02-30T00:00:00Z' }));
  assert.throws(() => voyageTime({ ...args, before: 1 }));
  assert.throws(() => voyageTime({ ...args, end: '2026-09-17T00:00:00Z' }));
});
test('retrieval answers and explicit calculations are logged; no evidence means no answer', async t => {
  const db = fixture(t);
  const r = await answerQuestion(db, { question: '배출량과 CII 규정', calculation: { fuel: 10, factor: 3, dwt: 100, distance: 10 } });
  assert.equal(r.toolRuns[0].emission, 30); assert.equal(r.generation, 'extractive');
  assert.ok(r.statements.every(s => r.evidence.some(e => e.id === s.chunkId && e.text === s.text)));
  const missing = await answerQuestion(db, { question: '초콜릿 케이크 레시피', mode: 'llm' }, { fetchImpl: () => assert.fail('No remote request allowed') });
  assert.equal(missing.status, 'insufficient_evidence'); assert.deepEqual(missing.statements, []);
  assert.equal(db.prepare('SELECT count(*) n FROM queries').get().n, 2);
  assert.throws(() => runTool(db, '__proto__', {}));
});
test('configured LLM uses Responses, validates citations, and degrades explicitly on failure', async t => {
  const db = fixture(t), env = { OPENAI_API_KEY: 'test-secret', OPENAI_MODEL: 'configured-model' };
  const source = retrieve(db, 'CII 등급 시정조치')[0];
  const content = { insufficient: false, statements: [{ text: '근거를 확인해 주세요.', chunkId: source.id, quote: source.text.slice(0, 20) }] };
  const mock = answer => async (url, init) => {
    assert.equal(url, 'https://api.openai.com/v1/responses');
    const body = JSON.parse(init.body); assert.equal(body.store, false); assert.equal(body.text.format.type, 'json_schema');
    assert.equal(body.model, env.OPENAI_MODEL);
    return { ok: true, json: async () => ({ status: 'completed', output: [{ type: 'message', content: [{ type: 'output_text', text: JSON.stringify(answer) }] }] }) };
  };
  const input = { question: 'CII 등급 시정조치', mode: 'llm' };
  assert.equal((await answerQuestion(db, input, { env, fetchImpl: mock(content) })).generation, 'llm');
  for (const bad of [{ ...content, statements: [{ ...content.statements[0], chunkId: 'invented' }] },
    { ...content, statements: [{ ...content.statements[0], quote: '문서에 존재하지 않는 문장' }] }]) {
    const r = await answerQuestion(db, input, { env, fetchImpl: mock(bad) });
    assert.equal(r.generation, 'extractive'); assert.ok(r.warnings.includes('MODEL_FAILED_EXTRACTIVE_FALLBACK'));
  }
  const failure = await answerQuestion(db, input, { env, fetchImpl: async () => { throw new Error('timeout'); } });
  assert.equal(failure.generation, 'extractive');
  const noKey = await answerQuestion(db, input, { env: {}, fetchImpl: () => assert.fail('No key') });
  assert.ok(noKey.warnings.includes('MODEL_NOT_CONFIGURED'));
  const abstain = await answerQuestion(db, input, { env, fetchImpl: mock({ insufficient: true, statements: [] }) });
  assert.equal(abstain.status, 'insufficient_evidence'); assert.equal(abstain.statements.length, 0);
});
