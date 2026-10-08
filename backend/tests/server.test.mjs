import test from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve, sep, basename } from 'node:path';
import { once } from 'node:events';
import { createServer } from 'node:net';
import { request } from 'node:http';

test('HTTP integration: ingestion, search, tools, persistence, input and origin protection', { timeout: 30000 }, async () => {
  const temp = mkdtempSync(join(tmpdir(), 'haedap-http-'));
  const probe = createServer(); probe.listen(0, '127.0.0.1'); await once(probe, 'listening');
  const port = probe.address().port; await new Promise(r => probe.close(r));
  const root = new URL('../../', import.meta.url);
  const child = spawn(process.execPath, ['backend/server.mjs'], { cwd: root, windowsHide: true,
    env: { ...process.env, PORT: '5173', HAEDAP_API_ORIGIN: `http://127.0.0.1:${port}`, HAEDAP_DB_PATH: join(temp, 'db.sqlite'), OPENAI_API_KEY: '', OPENAI_MODEL: '' }, stdio: ['ignore', 'pipe', 'pipe'] });
  let logs = ''; child.stdout.on('data', d => { logs += d; }); child.stderr.on('data', d => { logs += d; });
  const base = `http://127.0.0.1:${port}`;
  try {
    let health;
    for (let n = 0; n < 100; n++) {
      try { health = await (await fetch(base + '/api/health')).json(); break; } catch { await new Promise(r => setTimeout(r, 50)); }
    }
    assert.ok(health?.ok, logs); assert.equal(health.documents, 4); assert.equal(health.llmConfigured, false);
    let cookie = '';
    const setup = await fetch(base+'/api/auth/login', {method:'POST',headers:{'Content-Type':'application/json','X-Haedap-Token':health.csrfToken},body:JSON.stringify({username:'admin',name:'관리자',password:'1234'})});
    assert.equal(setup.status,200); cookie=setup.headers.getSetCookie().find(c=>c.startsWith('haedap_session=')).split(';')[0];
    const post = (path, body, headers = {}) => fetch(base + path, { method: 'POST', headers: { 'Content-Type': 'application/json', Cookie: cookie, 'X-Haedap-Token': health.csrfToken, ...headers }, body: JSON.stringify(body) });
    const ask = await post('/api/ask', { question: '황 함유량 기준' }); assert.equal(ask.status, 200);
    const result = await ask.json(); assert.ok(result.statements[0].text.includes('0.50%'));
    const noResult = await (await post('/api/ask', { question: 'chocolate cake recipe' })).json(); assert.equal(noResult.status, 'insufficient_evidence');
    assert.equal((await post('/api/ask', { question: '' })).status, 400);
    assert.equal((await post('/api/ask', { question: 'CII' }, { Origin: 'https://evil.example' })).status, 403);
    assert.equal((await post('/api/ask', { question: 'CII' }, { 'X-Haedap-Token': '' })).status, 403);
    const badHostStatus = await new Promise((resolve, reject) => {
      const req = request(base + '/api/health', { headers: { Host: 'evil.example' } }, res => { res.resume(); resolve(res.statusCode); });
      req.on('error', reject); req.end();
    });
    assert.equal(badHostStatus, 403);
    // Through the Next.js rewrite: X-Forwarded-Host is the public address.
    const viaNext = await post('/api/ask', { question: '황 함유량 기준' }, { 'X-Forwarded-Host': '127.0.0.1:5173', Origin: 'http://127.0.0.1:5173' });
    assert.equal(viaNext.status, 200);
    assert.equal((await post('/api/ask', { question: 'CII' }, { 'X-Forwarded-Host': '127.0.0.1:5173', Origin: `http://127.0.0.1:${port}` })).status, 403);
    assert.equal((await post('/api/ask', { question: 'CII' }, { 'X-Forwarded-Host': 'evil.example:5173', Origin: 'http://evil.example:5173' })).status, 403);
    assert.equal((await post('/api/ask', { question: 'x'.repeat(1100000) })).status, 413);
    const malformed = await fetch(base + '/api/ask', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Haedap-Token': health.csrfToken }, body: '{bad' });
    assert.equal(malformed.status, 400);
    for (const path of ['/data/haedap.sqlite', '/.env', '/backend/db.mjs', '/knowledge/seed.json', '/server.mjs', '/.backup/', '/legacy-ui/app.js', '/backend-ui.js']) assert.equal((await fetch(base + path)).status, 404, path);
    const rootPage = await fetch(base + '/'); assert.equal(rootPage.status, 404, 'API server serves no screens');
    assert.ok((await rootPage.text()).includes('http://127.0.0.1:5173'), 'explains the Next.js address to open');
    const calc = await (await post('/api/tools/calculate_emissions', { fuel: 100, factor: 3, dwt: 1000, distance: 100 })).json();
    assert.equal(calc.result.emission, 300);
    assert.equal((await post('/api/tools/calculate_emissions', { fuel: '100' })).status, 400);
    assert.equal((await post('/api/tools/not-registered', {})).status, 404);
    const report = { title: 'HTTP 초안', type: '규정 검토', text: '검색 결과 검토', sources: [result.evidence[0].document_id], version: 0 };
    assert.equal((await post('/api/reports/current', report)).status, 200);
    assert.equal((await post('/api/reports/current', report)).status, 409);
    assert.equal((await (await fetch(base + '/api/reports/current', {headers:{Cookie:cookie}})).json()).report.title, report.title);
    assert.equal((await post('/api/reports/current', null)).status, 400);
  } finally {
    if (child.exitCode === null && child.signalCode === null) { const exited = once(child, 'exit'); child.kill(); await exited; }
    assert.ok(resolve(temp).startsWith(resolve(tmpdir()) + sep) && basename(temp).startsWith('haedap-http-'));
    rmSync(temp, { recursive: true, force: true });
  }
});
