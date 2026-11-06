import React from 'react';
import { referenceTime } from '../lib/port-reference';

const names = {gothenburg_draught:'접근 수로 흘수·선저 여유',gothenburg_tugs:'호송 예선·사전 요청',
  gothenburg_weather:'선종·입출항별 기상 조건',gothenburg_control:'입항 신고·항만 운영 확인',
  helsinki_regulations:'항만 배정·현 수심·지원 지시',helsinki_cruise_navigation:'크루즈 항만 구역·도선 안내'};

export default function OfficialGuidance({ value }) {
  if (!value?.documents?.length) return null;
  return <section className="card pad mt" data-official-guidance>
    <h3>공식 지침에서 추가로 확인할 조건</h3>
    <p className="notice warning" style={{display:'block'}}>{value.notice}</p>
    <p className="small">검토한 일부 지침입니다. 아래 수치를 기존 선석 제한·가정 입력에 자동 적용하지 않습니다.</p>
    {value.documents.map(doc=><details className="mt" key={doc.id} data-guidance-document={doc.id}>
      <summary><strong>{names[doc.id] || doc.title}</strong> · {doc.facts.length}개 항목</summary>
      <p className="small"><a href={doc.url} target="_blank" rel="noreferrer">{doc.attribution} · {doc.title}</a><br />
        페이지 표시 개정일: {doc.displayed_updated_on || '미표시'}
        {doc.displayed_revision_age_status==='older_than_one_year' && ' · 1년 초과, 현행 적용 확인 필요'}<br />
        명시 적용일: {doc.effective_on || '미확인'} · 수집: {referenceTime(doc.retrieved_at)}
        {doc.capture_age_status==='stale' && ' · 수집 후 7일 초과'}
        {doc.capture_age_status==='time_in_future' && ' · 수집 시각 확인 필요'}</p>
      <ol>{doc.facts.map(fact=><li key={fact.id} data-guidance-fact={fact.id}>
        <strong>{fact.title}</strong><p>{fact.summary}</p>
        <p className="small">적용 범위·추가 확인: {fact.scope}</p>
        {fact.values.length>0 && <ul>{fact.values.map((v,i)=><li key={i}>{v.label}: <strong>{v.value} {v.unit}</strong></li>)}</ul>}
        <details className="small mt"><summary>근거 문구·위치</summary>
          <p style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{fact.evidence_text}</p>
          <small style={{overflowWrap:'anywhere'}}>{fact.locator}</small>
        </details>
      </li>)}</ol>
    </details>)}
  </section>;
}
