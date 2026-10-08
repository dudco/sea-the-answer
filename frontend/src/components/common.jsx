import React from 'react';
import { icons } from '../lib/icons';
export const esc = (value) => String(value ?? ''); // React escapes text at render time.
export const I = (name) => (
  <svg className="icon" aria-hidden="true" viewBox="0 0 24 24">
    <path d={icons[name] || icons.file} />
  </svg>
);
export function Button({ children, action, className = '', icon = '', ...props }) {
  return (
    <button type="button" className={`btn ${className}`} data-action={action} {...props}>
      {icon && I(icon)}
      {children}
    </button>
  );
}
export const btn = (label, action, cls = '', icon = '', extra = {}) => (
  <Button action={action} className={cls} icon={icon} {...extra}>
    {label}
  </Button>
);
export const badge = (text, cls = '') => <span className={`badge ${cls}`}>{text}</span>;
export const n = (v, d = 1) =>
  Number(v).toLocaleString('ko-KR', {
    minimumFractionDigits: d,
    maximumFractionDigits: d,
  });
export const dateText = (date) =>
  date
    ? new Date(date).toLocaleString('ko-KR', {
        timeZone: 'Asia/Seoul',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      })
    : '—';
export const options = (list) =>
  list.map((item) => {
    const [v, label] = Array.isArray(item) ? item : [item, item];
    return (
      <option key={v} value={v}>
        {label}
      </option>
    );
  });
export function PageHeader({ title, description, children }) {
  return (
    <div className="pagehead">
      <div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      <div className="actions wrap">{children}</div>
    </div>
  );
}
export const head = (title, sub, actions = null) => (
  <PageHeader title={title} description={sub}>
    {actions}
  </PageHeader>
);
export function Notice({ children, kind = '' }) {
  return (
    <div className={`notice ${kind}`}>
      {I(kind === 'warning' ? 'alert' : 'info')}
      <span>{children}</span>
    </div>
  );
}
export const notice = (text, kind = '') => <Notice kind={kind}>{text}</Notice>;
export const empty = (title, sub, action = null) => (
  <div className="empty">
    {I('file')}
    <h3>{title}</h3>
    <p>{sub}</p>
    <div className="mt">{action}</div>
  </div>
);
export const stat = (label, value, unit, sub, icon = 'chart') => (
  <div className="card stat">
    <div className="stat-top">
      <span>{label}</span>
      {I(icon)}
    </div>
    <div className="stat-value mono">
      {value} <small>{unit}</small>
    </div>
    <div className="small muted">{sub}</div>
  </div>
);
export function safeUrl(value) {
  try {
    const u = new URL(value);
    return u.protocol === 'https:' && !u.username && !u.password ? u.href : '';
  } catch {
    return '';
  }
}
export const docKind = (d) =>
  d.kind === 'sample'
    ? '가상 샘플'
    : d.kind === 'official-summary'
      ? '공식 안내 요약'
      : '선내 문서';
export function download(name, content, type = 'text/plain;charset=utf-8') {
  const url = URL.createObjectURL(
      new Blob([content], {
        type,
      }),
    ),
    a = document.createElement('a');
  a.href = url;
  a.download = name.replace(/[\\/:*?"<>|]/g, '_');
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
