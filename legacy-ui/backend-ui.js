'use strict';
const backend = { ready: false, token: '', health: null, result: null, error: '', version: 0, useModel: false, saving: false, reportExists: false, init: null };

async function apiRequest(path, body) {
  const response = await fetch(path, { method: body === undefined ? 'GET' : 'POST', cache: 'no-store',
    headers: body === undefined ? {} : { 'Content-Type': 'application/json', 'X-Haedap-Token': backend.token },
    body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(32000) });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error?.message || '서버 요청을 처리하지 못했습니다.');
  return data;
}
function registerEvidence(documents) {
  for (const d of documents) {
    if (!/^[a-z0-9-]+$/.test(d.id)) continue;
    DOCS[d.id] = { id: d.id, title: d.title, category: d.kind === 'official-summary' ? '공식 안내 요약' : d.kind === 'sample' ? '가상 샘플 문서' : '선내 문서',
      ref: d.reference, version: `${d.version} · 확인 ${d.reviewed_at}`, location: d.sections.map(s => s.heading).join(' / '),
      url: d.url, body: d.sections.map(s => s.text), note: d.kind === 'sample' ? '검색 시험용 가상 자료입니다.' : '저장한 문서 버전입니다. 최신 개정과 선박별 적용 여부는 별도로 확인하세요.', backend: true };
  }
}
function initializeBackend() {
  backend.init = (async () => {
    try {
      const [health, docs, saved] = await Promise.all([apiRequest('/api/health'), apiRequest('/api/documents'), apiRequest('/api/reports/current')]);
      backend.health = health; backend.token = health.csrfToken;
      registerEvidence(docs.documents);
      backend.reportExists = !!saved.report;
      // Never silently overwrite a browser draft. Loading the shared DB draft is explicit.
      backend.version = 0;
      const local = safeRead('haedap-report', null);
      if (local && typeof local.text === 'string' && Array.isArray(local.sources)) {
        state.report.sources = local.sources.filter(id => Object.hasOwn(DOCS, id));
      }
      backend.ready = true; backend.error = '';
      captureReport(); render();
    } catch { backend.error = '백엔드 연결에 실패했습니다. 서버를 실행한 뒤 새로고침해 주세요.'; render(); }
  })();
  return backend.init;
}
function backendNotice() {
  return `<div class="mode-notice"><span>${ico('info')} ${backend.ready ? `문서 검색 연결됨 · ${backend.health.documents}개 문서 · ${backend.useModel && !state.offline ? '근거 기반 AI 답변' : '근거 문단 보기'}` : backend.error || '문서 서버 연결 중…'}</span><button class="text-btn" data-action="demo-settings">실행 환경 설정</button></div>`;
}
async function backendSearch(query) {
  state.query = query.trim(); state.error = null; backend.error = ''; state.result = null;
  if (!state.query) { state.error = 'empty'; render(); return; }
  const request = ++state.requestId;
  state.loading = true; render();
  try {
    await backend.init;
    if (!backend.ready) throw new Error(backend.error || '백엔드에 연결할 수 없습니다.');
    const body = { question: state.query, filter: state.page === 'ask' ? 'all' : state.filter,
      language: state.language, mode: backend.useModel && !state.offline ? 'llm' : 'extractive' };
    if (/(배출량|emissions?)/i.test(state.query) && /(계산|함께|우리|calculate|together|our)/i.test(state.query)) body.calculation = { ...state.carbon };
    const data = await apiRequest('/api/ask', body);
    if (request !== state.requestId) return;
    if (data.evidence.some(e => !Object.hasOwn(DOCS, e.document_id))) {
      const docs = await apiRequest('/api/documents');
      if (request !== state.requestId) return;
      registerEvidence(docs.documents);
    }
    backend.result = data; state.result = 'backend';
  } catch (e) {
    if (request !== state.requestId) return;
    backend.error = e.message; state.error = 'backend';
  } finally { if (request === state.requestId) { state.loading = false; render(); } }
}
function backendErrorView() {
  return `<section class="panel error-state" role="alert"><h2>요청을 완료하지 못했습니다.</h2><p>${esc(backend.error)}</p>${btn('다시 시도','retry','primary')}</section>`;
}
function backendResultView() {
  const r = backend.result;
  if (!r) return '';
  const sources = [...new Set(r.evidence.map(e => e.document_id))].filter(id => Object.hasOwn(DOCS, id));
  const warning = r.warnings.length ? '<p class="inline-note">외부 모델 답변을 생성하지 못해 검색된 근거 문단을 표시합니다.</p>' : '';
  return `<section class="result-card"><div class="result-heading"><span class="answer-icon">${ico('book')}</span><div><div class="eyebrow">HAEDAP KNOWLEDGE</div><h2>${r.status === 'insufficient_evidence' ? '답변할 근거가 충분하지 않습니다.' : r.generation === 'llm' ? '검색 근거로 정리한 답변입니다.' : '질문과 관련된 근거 문단입니다.'}</h2></div>${chip(r.generation === 'llm' ? 'AI 초안' : '문서 검색','soft')}</div>
    <section class="result-block"><p class="small muted">${esc(r.notice)}</p>${warning}
    ${r.statements.map(s => { const e = r.evidence.find(e => e.id === s.chunkId); return `<p class="answer-summary">${esc(s.text)} <button class="citation" data-doc="${esc(e.document_id)}">[${sources.indexOf(e.document_id) + 1}]</button></p><details class="formula"><summary>근거 위치 · ${esc(e.heading)}</summary><p>${esc(s.quote)}</p><small>${esc(e.version)} · ${esc(e.kind === 'sample' ? '가상 자료' : '저장 문서')}</small></details>`; }).join('')}
    ${r.status === 'insufficient_evidence' ? '<p>등록된 문서에서 질문을 뒷받침할 내용을 찾지 못했습니다. 질문을 구체화하거나 관련 문서를 추가해 주세요.</p>' : ''}
    ${r.toolRuns.map(t => `<div class="ops-record"><strong>입력값으로 계산한 결과</strong><p>CO₂ ${t.emission.toLocaleString('ko-KR')} t · 단순 집약도 ${t.intensity.toFixed(2)} gCO₂/(DWT·nm)</p><small>공식 CII 등급 미산정 · ${esc(t.version)}</small></div>`).join('')}</section>
    ${sources.length ? sourceCards(sources) : ''}<div class="result-footer"><span>저장 문서의 확인일·적용 조건을 검토하세요.</span>${r.statements.length || r.toolRuns.length ? btn('보고서에 담기','add-backend-result','primary') : ''}</div></section>`;
}
function addBackendResult() {
  const r = backend.result;
  if (!r) return;
  const ids = [...new Set(r.statements.map(s => r.evidence.find(e => e.id === s.chunkId)?.document_id).filter(Boolean))];
  const body = [`## ${r.question}`, r.notice, ...r.statements.map(s => {
    const e = r.evidence.find(e => e.id === s.chunkId);
    return `${s.text}\n근거: ${e.title} / ${e.heading} / ${e.version} / ${e.id}`;
  }), ...r.toolRuns.map(t => `계산: CO₂ ${t.emission} t; 단순 집약도 ${t.intensity} gCO₂/(DWT·nm). 공식 CII 등급 미산정.\n계산 기록: ${t.id} / ${t.version}`)].join('\n\n');
  addReport(body, ids, r.toolRuns.length ? '종합 검토' : '규정 검토');
}
async function saveBackendReport() {
  if (backend.saving || !validateReport()) return;
  backend.saving = true;
  const snapshot = JSON.parse(JSON.stringify(state.report));
  try {
    await backend.init;
    if (!backend.ready) throw new Error('DB 서버에 연결할 수 없습니다. 파일 백업을 이용하세요.');
    const data = await apiRequest('/api/reports/current', { ...snapshot, version: backend.version });
    backend.version = data.report.version; backend.reportExists = true;
    writeLocal('haedap-report', snapshot);
    captureReport(); state.saved = JSON.stringify(state.report) === JSON.stringify(snapshot);
    render(); toast(state.saved ? 'DB에 초안을 저장했습니다.' : '저장 중 추가로 편집한 내용은 아직 저장되지 않았습니다.');
  } catch (e) { toast(e.message); }
  finally { backend.saving = false; }
}
async function loadBackendReport() {
  try {
    captureReport();
    const snapshot = JSON.stringify(state.report);
    const [{ report }, docs] = await Promise.all([apiRequest('/api/reports/current'), apiRequest('/api/documents')]);
    if (!report) { toast('DB에 저장된 초안이 없습니다.'); return; }
    captureReport();
    if (JSON.stringify(state.report) !== snapshot) { toast('불러오는 동안 편집 내용이 바뀌었습니다. 다시 불러와 주세요.'); return; }
    if (state.report.text.trim() && !window.confirm('현재 편집 내용을 DB에 저장된 초안으로 바꿀까요?')) return;
    registerEvidence(docs.documents);
    state.report = { title: report.title, type: report.type, text: report.text, sources: report.sources.filter(id => Object.hasOwn(DOCS, id)) };
    backend.version = report.version; state.saved = true;
    writeLocal('haedap-report', state.report); render(); toast('DB 초안을 불러왔습니다.');
  } catch (e) { toast(e.message); }
}
async function calculateBackendCarbon() {
  if (!captureCarbon()) return;
  const input = { ...state.carbon };
  const sequence = backend.calcSequence = (backend.calcSequence || 0) + 1;
  try {
    await backend.init;
    const { result } = await apiRequest('/api/tools/calculate_emissions', input);
    if (sequence !== backend.calcSequence || JSON.stringify(input) !== JSON.stringify(state.carbon)) return;
    state.calc = result;
    if (state.page === 'carbon') { render(); toast('서버 계산 결과와 실행 기록을 저장했습니다.'); }
  } catch (e) { if (sequence === backend.calcSequence) { state.carbonError = e.message; if (state.page === 'carbon') render(); } }
}
document.addEventListener('change', e => { if (e.target.id === 'backend-model') backend.useModel = e.target.checked; });
document.addEventListener('input', e => {
  if (['fuel', 'factor', 'dwt', 'distance'].includes(e.target.id)) backend.calcSequence = (backend.calcSequence || 0) + 1;
});
