import React from 'react';
import {UiControl, UiText} from './ui-language';

const states={available:'자료 있음',empty:'등록 건수 0',unavailable:'연결 확인 불가',unsupported_scope:'조건 확인 필요'};
function sourceUrl(value) {
  try { const url=new URL(value); return ['https:','http:'].includes(url.protocol) ? url.href : undefined; }
  catch { return undefined; }
}
export default function DatasetStatus({value}) {
  if (!value) return null;
  const scope=value.scope || {};
  return <UiControl as="section" className="mt" data-dataset-status aria-label="자료 등록 현황">
    <h3><UiText>자료 등록 현황</UiText></h3>
    <p className="small muted"><UiText>확인 시각</UiText>: {value.assessed_at}</p>
    {scope.ship && <p>{scope.ship.name} · {scope.ship.imo}</p>}
    {scope.years?.length>0 && <p><UiText>보고 연도</UiText>: {scope.years.join(', ')}</p>}
    <div className="tablewrap"><table><thead><tr>
      {['자료','상태','등록 건수','고유 선박','집계/후보 적격 건수','기간'].map(label=><th key={label}><UiText>{label}</UiText></th>)}
    </tr></thead><tbody>{value.datasets.map(item=><tr key={item.dataset}>
      <th scope="row">{item.label}</th><td><UiText>{states[item.status] || item.status}</UiText></td>
      <td>{item.row_count ?? '—'}</td><td>{item.vessel_count ?? '—'}</td>
      <td>{item.eligible_count ?? '—'}</td><td>{item.first_period ? `${item.first_period} ~ ${item.last_period}` : '—'}</td>
    </tr>)}</tbody></table></div>
    {value.datasets.map(item=><div className="mt" key={item.dataset}>
      <strong>{item.label}</strong><p><UiText>{item.notice}</UiText></p>
      {item.sample_count!=null && <p><UiText>가상 예시 건수</UiText>: {item.sample_count}</p>}
      {item.sources?.length>0 && <ul>{item.sources.map((source,i)=><li key={i}>
        {sourceUrl(source.source_url) ? <a href={sourceUrl(source.source_url)} target="_blank" rel="noreferrer">{source.dataset_id}</a> : source.dataset_id}
      </li>)}</ul>}
    </div>)}
  </UiControl>;
}
