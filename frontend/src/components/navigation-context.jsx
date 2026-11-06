import React from 'react';
import { checkLabels, metres, referenceTime } from '../lib/port-reference';

const states = {reference_available:'일치하는 참고 치수 있음',unavailable:'연결된 참고값 없음',
  period_unknown:'등록 유효기간 미확인',identity_conflict:'등록 식별자 충돌',insufficient_reference:'참고 치수 부족/충돌'};
const ages = {within_age_window:'2시간 이내',stale:'2시간 초과 · 오래된 수집본',time_in_future:'시각 확인 필요'};
const quality = {checked:'검수·승인',suspect_or_aggregated:'의심 또는 집계값',unchecked:'미검수',unknown:'품질 미확인'};

export function NavigationContext({ registered, environment }) {
  return <>
    {registered?.candidate_count > 0 && <section className="card pad mt" data-static-reference>
      <h3>과거 등록 제원 참고</h3>
      <p>{states[registered.status] || registered.status} · 요청 기간 끝 {referenceTime(registered.as_of)} 직전 기준</p>
      <p>길이 {metres(registered.length_m)} · 폭 {metres(registered.beam_m)} · 기록 후보 {registered.candidate_count}건</p>
      <p className="notice warning" style={{display:'block'}}>{registered.notice}</p>
      <details><summary>등록 후보·유효기간 확인</summary>
        {registered.candidates?.map((r,i)=><p key={i}>등록 IMO {r.registry_imo_number || '미확인'} · MMSI {r.mmsi}<br />
          길이 {metres(r.reference_length_m)} · 폭 {metres(r.reference_beam_m)} · 등록 흘수 {metres(r.registry_draught_m)}<br />
          등록 유효 시작 {referenceTime(r.valid_from)} / 종료 {referenceTime(r.valid_to)}<br />
          <small>{r.issues?.join(' · ')} · {r.source_ref?.locator}</small></p>)}
        {registered.candidate_count>20 && <p>후보 중 처음 20건만 표시합니다. 참고 치수는 전체 후보를 검사한 결과입니다.</p>}
      </details>
    </section>}
    {environment?.observations?.length>0 && <section className="card pad mt" data-environment-context>
      <h3>Gothenburg 지역 관측 수집본</h3>
      <p className="notice warning" style={{display:'block'}}>{environment.notice}</p>
      <ul>{environment.observations.map(r=><li key={r.source_ref.source_id}>
        <strong>{r.station_name}: {r.value} {r.unit}{r.vertical_datum ? ' / '+r.vertical_datum : ''}</strong><br />
        관측 {referenceTime(r.observed_at)} · {ages[r.age_status] || r.age_status}<br />
        품질 {r.quality} ({quality[r.quality_status] || r.quality_status}) · 수집본 {ages[r.capture_age_status] || r.capture_age_status}<br />
        <small>좌표 {r.latitude}, {r.longitude} · {r.unit==='m/s'?'10분 평균 · 시간당 제공':'분 단위 수위 · 기준면 RH2000'}<br />
          <a href={r.station_metadata.url} target="_blank" rel="noreferrer">관측소 정보</a>
          {r.datum_evidence && <> · <a href={r.datum_evidence.url} target="_blank" rel="noreferrer">수위 기준면·품질 설명</a></>}
        </small>
      </li>)}</ul>
      <p className="small">2시간은 앱의 노후화 표시 기준입니다. 가정 풍속·예선·선저 여유 입력값은 자동으로 채우지 않습니다.</p>
    </section>}
  </>;
}

export function HistoricalChecks({ checks }) {
  const rows = checks?.filter(c=>c.reference_value_m!=null);
  if (!rows?.length) return null;
  return <div className="notice mt" style={{display:'block'}} data-historical-checks>
    <strong>과거 등록 치수와의 별도 참고 비교</strong>
    {rows.map(c=><p className="small" key={c.kind}>{checkLabels[c.kind]} {metres(c.reference_value_m)} / 선석 {metres(c.berth_listed_m)} · {
      c.status==='reference_value_exceeded'?'과거 등록값이 공개 수치 초과':
      c.status==='within_historical_reference'?'과거 등록값이 공개 수치 이내':'선석 수치 미확인으로 비교 보류'}</p>)}
    <small>기존 AIS 비교 상태와 현재 입항 판정은 변경하지 않습니다.</small>
  </div>;
}
