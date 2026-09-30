import { icons } from './icons.js';
export const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
export const I = name => `<svg class="icon" aria-hidden="true" viewBox="0 0 24 24"><path d="${icons[name] || icons.file}"/></svg>`;
export const btn = (label, action, cls = '', icon = '', extra = '') => `<button type="button" class="btn ${cls}" data-action="${action}" ${extra}>${icon ? I(icon) : ''}${esc(label)}</button>`;
export const badge = (text, cls = '') => `<span class="badge ${cls}">${esc(text)}</span>`;
export const n = (v, d = 1) => Number(v).toLocaleString('ko-KR', { minimumFractionDigits: d, maximumFractionDigits: d });
export const dateText = date => date ? new Date(date).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '—';
export const options = (list, selected) => list.map(item => { const [v, label] = Array.isArray(item) ? item : [item, item]; return `<option value="${esc(v)}" ${v === selected ? 'selected' : ''}>${esc(label)}</option>`; }).join('');
export const head = (title, sub, actions = '') => `<div class="pagehead"><div><h1>${esc(title)}</h1><p>${esc(sub)}</p></div><div class="actions wrap">${actions}</div></div>`;
export const notice = (text, kind = '') => `<div class="notice ${kind}">${I(kind === 'warning' ? 'alert' : 'info')}<span>${text}</span></div>`;
export const empty = (title, sub, action = '') => `<div class="empty">${I('file')}<h3>${esc(title)}</h3><p>${esc(sub)}</p><div class="mt">${action}</div></div>`;
export function safeUrl(value) { try { const u = new URL(value); return u.protocol === 'https:' && !u.username && !u.password ? u.href : ''; } catch { return ''; } }
export function docKind(d) { return d.kind === 'sample' ? '가상 샘플' : d.kind === 'official-summary' ? '공식 안내 요약' : '선내 문서'; }
export const stat = (label, value, unit, sub, icon = 'chart') => `<div class="card stat"><div class="stat-top"><span>${esc(label)}</span>${I(icon)}</div><div class="stat-value mono">${esc(value)} <small>${esc(unit)}</small></div><div class="small muted">${esc(sub)}</div></div>`;
export function toast(text) {
  const node = document.createElement('div'); node.className = 'toast'; node.textContent = text;
  document.getElementById('toasts').append(node); setTimeout(() => node.remove(), 5000);
}
export function download(name, content, type = 'text/plain;charset=utf-8') {
  const url = URL.createObjectURL(new Blob([content], { type })), a = document.createElement('a');
  a.href = url; a.download = name.replace(/[\\/:*?"<>|]/g, '_'); document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
