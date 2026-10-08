import { createHash } from 'node:crypto';
import { object, string, requireValue } from './validation.mjs';

// Index words as well as Korean bigrams. Expand a small, explicit bilingual glossary;
// this is lexical retrieval, not a substitute for semantic embeddings.
const glossary = [
  ['sulphur', 'sulfur', 'sox', '황', '황함유량', '황 함유량'],
  ['eca', '배출규제해역', '배출 규제 해역'],
  ['cii', '탄소집약도', '탄소집약', 'carbon intensity'],
  ['corrective', '시정', '개선'], ['rating', '등급'],
  ['fuel', '연료'], ['changeover', '전환'], ['checklist', '점검표'],
  ['emission', 'emissions', '배출량'], ['report', '보고서'],
];
const stop = new Set('what how is are the a an of in for to do does and or with our ship ships please tell me about 규정 기준 알려줘 알려주세요 무엇 어떻게 어떤 필요한 필요 있나요 무엇인가요'.split(' '));
export function tokens(text) {
  const normalized = text.normalize('NFKC').toLowerCase();
  const words = (normalized.match(/[a-z0-9]+|[가-힣]+/g) || []).filter(w => !stop.has(w));
  const result = words.filter(w => w.length > 1);
  for (const word of words) if (/[가-힣]/.test(word) && word.length > 2) {
    for (let i = 0; i < word.length - 1; i++) if (!stop.has(word.slice(i, i + 2))) result.push(word.slice(i, i + 2));
  }
  for (const [i, group] of glossary.entries()) {
    if (group.some(w => /[가-힣]/.test(w) ? normalized.includes(w) : new RegExp(`\\b${w}\\b`).test(normalized))) result.push(`concept${i}`);
  }
  return [...new Set(result)].slice(0, 600);
}
export function validateDocument(raw) {
  object(raw);
  const id = string(raw.id, '문서 ID', 80);
  requireValue(/^[a-z0-9][a-z0-9-]*$/.test(id), '문서 ID는 영문 소문자·숫자·하이픈만 사용합니다.');
  requireValue(['official-summary', 'onboard', 'sample'].includes(raw.kind), '문서 종류가 올바르지 않습니다.');
  const url = raw.url || null;
  if (url) {
    let parsed; try { parsed = new URL(url); } catch { /* rejected below */ }
    requireValue(parsed?.protocol === 'https:' && !parsed.username && !parsed.password, '출처는 HTTPS URL이어야 합니다.');
  }
  requireValue(raw.kind !== 'official-summary' || !!url, '공식 안내 요약에는 원문 URL이 필요합니다.');
  const reviewedAt = string(raw.reviewedAt, '확인일', 10);
  requireValue(/^\d{4}-\d{2}-\d{2}$/.test(reviewedAt) && Number.isFinite(Date.parse(reviewedAt)) && new Date(reviewedAt).toISOString().slice(0, 10) === reviewedAt, '확인일은 유효한 YYYY-MM-DD 형식이어야 합니다.');
  requireValue(Array.isArray(raw.sections) && raw.sections.length > 0 && raw.sections.length <= 1500, '문서에는 1~1,500개 절이 필요합니다.');
  const sections = raw.sections.map(s => { object(s); return { heading: string(s.heading, '절 제목', 200), text: string(s.text, '본문', 20000), ...(s.page ? {page: Number(s.page)} : {}) }; });
  requireValue(sections.reduce((n, s) => n + s.text.length, 0) <= 2000000, '문서 본문은 2,000,000자 이하여야 합니다.');
  return { id, title: string(raw.title, '문서 제목', 200), kind: raw.kind, url,
    reference: string(raw.reference, '출처 조항', 200), version: string(raw.version, '버전', 100), reviewedAt,
    language: ['ko', 'en'].includes(raw.language) ? raw.language : 'ko', sections };
}
export function prepareDocument(raw) {
  const doc = validateDocument(raw);
  requireValue(doc.sections.every(s => !s.page || (Number.isInteger(s.page) && s.page > 0 && s.page <= 10000)), '페이지 번호는 1~10,000의 정수입니다.');
  const hash = createHash('sha256').update('haedap-chunk-v1\n').update(JSON.stringify(doc)).digest('hex');
  const revisionId = `${doc.id}-${hash.slice(0, 16)}`;
  const chunks = [];
  for (const section of doc.sections) {
    // Paragraph/sentence boundaries where possible, hard upper bound for long lines.
    const pieces = section.text.split(/(?<=[.!?])\s+|\n+/u).filter(Boolean);
    let text = '';
    const flush = () => { if (text.trim()) chunks.push({ heading: section.heading, text: text.trim(), page: section.page || null }); text = ''; };
    for (const piece of pieces) {
      if (text.length + piece.length > 900) flush();
      if (piece.length > 900) { for (let i = 0; i < piece.length; i += 900) { text = piece.slice(i, i + 900); flush(); } }
      else text += `${piece.trim()} `;
    }
    flush();
  }
  return { ...doc, revisionId, hash, chunks: chunks.map((c, i) => ({ ...c, id: `${revisionId}-${i + 1}`, position: i + 1,
    terms: tokens(`${doc.title} ${doc.reference} ${c.heading} ${c.text}`).join(' ') })) };
}
