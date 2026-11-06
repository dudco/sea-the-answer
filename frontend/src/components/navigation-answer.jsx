import React from 'react';
import { berthStates, checkLabels, checkStates, metres, referenceReason, referenceTime } from '../lib/port-reference';
import styles from './navigation-answer.module.css';
import { NavigationReadiness, OperationalChecks } from './navigation-readiness';
import { NavigationContext, HistoricalChecks } from './navigation-context';
import OfficialGuidance from './navigation-guidance';

function link(value) {
  try { const url = new URL(value); return ['http:', 'https:'].includes(url.protocol) ? url.href : undefined; }
  catch { return undefined; }
}
const sourceNames = {ais:'Fintraffic AIS',schema:'AIS 공식 명세',berths:'Gothenburg 항만청',helsinki_berths:'Helsinki 항만청 · 크루즈 선석',
  ais_no:'Kystverket · 노르웨이 공개 AIS',schema_no:'Kystdatahuset 공식 API 명세',aalborg_berths:'Aalborg 항만청 · 2026 Oil Terminals',
  norway_static:'Kystdatahuset · 과거 등록 제원',schema_no_static:'등록 제원 공식 명세',smhi_wind_vinga:'SMHI · Vinga 풍속',
  smhi_wind_gothenburg:'SMHI · Göteborg 풍속',smhi_water_gothenburg:'SMHI · Göteborg-Tångudden 수위'};
function shipQuery(ship, port='') {
  const imo = String(ship?.imo || '').replace(/^IMO\s*/i,'');
  return `${ship?.name || ''} ${imo ? 'IMO '+imo : ''} 선박이 ${port ? port+'에' : ''} 입항 가능한지 공개 자료로 비교해줘`;
}
export default function NavigationAnswer({ answer }) {
  const nav = answer.navigation, en = answer.language === 'en';
  if (!nav) return null;
  const results = Array.isArray(nav.results) ? nav.results : [];
  const sources = [...new Map(results.flatMap(r=>r.sources || []).map(s=>[s.id+':'+s.sha256,s])).values()];
  return <section className={styles.root} data-navigation-answer aria-label={en?'Port reference answer':'항구 참조 답변'}>
    {nav.ship && <p>{en?'Ship used: ':'조회 선박: '}<strong>{nav.ship.name}</strong>{nav.context?.imo_number && <> · IMO {nav.context.imo_number}</>}</p>}
    {nav.query && <p className="notice mt" data-navigation-conditions>
      <strong>{en?'Applied conditions: ':'적용 조건: '}</strong>{nav.query.description?.[en?'en':'ko']}
      <br />{en?'Compared / displayed berth groups: ':'비교 / 표시 선석 그룹: '}{nav.compared_berth_count} / {nav.matched_berth_count}
      {nav.excluded_unknown_count>0 && <><br />{en?'Excluded due to unknown numeric limits: ':'수치 제한 미확인으로 필터에서 제외: '}{nav.excluded_unknown_count}</>}
      {nav.previous_query_id && <><br />{en?'Previous target/conditions retained; current sources queried again.':'이전 대상·조건을 연결하고 현재 자료를 다시 조회했습니다.'}</>}
    </p>}
    {nav.ship_options?.length > 0 && <div className="actions wrap mt">
      {nav.ship_options.map(s=><button type="button" className="btn ghost sm" key={s.id} data-question={shipQuery(s)}>{s.name}{s.imo ? ' · '+s.imo : ''}</button>)}
    </div>}
    {results.length > 0 && <>
      <p className="notice warning mt">{en?'Partial reported-value comparison only. Berth approval, current verified draught and approach conditions remain unassessed.':'일부 신고값과 공개 수치의 비교입니다. 현재 실측 흘수·선석 승인·접근 항로 등은 추가 확인이 필요합니다.'}</p>
      <p className="small muted">{en?'Coverage is limited to the available sources; dates are independent of the operation period filter.':'확보된 항구 자료 범위만 조회했습니다. 상단 운항 기간 필터와 별개로 수집본 시점을 사용합니다.'}</p>
      <NavigationReadiness value={results[0]?.readiness} />
      <div className="tablewrap mt"><table className={styles.summary}><thead><tr>
        <th>{en?'Port':'항구'}</th><th>{en?'Displayed / compared':'표시 / 비교 선석'}</th><th>{en?'Some values within':'일부 수치 이내'}</th><th>{en?'Reference exceeded':'공개 수치 초과'}</th><th>{en?'Insufficient data':'자료 부족'}</th>
      </tr></thead><tbody>{nav.ports.map(p=><tr key={p.port_id}><th scope="row">{p.name}</th>
        <td data-label={en?'Displayed / compared':'표시 / 비교 선석'}>{p.berth_count} / {p.available_berth_count ?? p.berth_count}</td>
        <td data-label={en?'Some values within':'일부 수치 이내'}>{p.partial_reference_check}</td>
        <td data-label={en?'Reference exceeded':'공개 수치 초과'}>{p.published_reference_exceeded}</td>
        <td data-label={en?'Insufficient data':'자료 부족'}>{p.insufficient_data}</td></tr>)}</tbody></table></div>
      {results.map(result=><details className="card pad mt" key={result.port_id}>
        <summary>{result.port_name} · {en?'Berth details':'선석별 근거·부족 항목'} ({result.berths.length})</summary>
        <p className="small">{en?'Assessed':'비교 시각'}: {referenceTime(result.assessed_at)}<br />
          AIS {en?'metadata received':'기록 수신'}: {referenceTime(result.observation?.metadata_received_at)} · {en?'Not a draught measurement timestamp.':'흘수 측정 시각은 아닙니다.'}</p>
        {result.port_source_id==='helsinki_berths' && <p className="notice warning">{en?'Cruise berth source only; vessel/service suitability not assessed.':'크루즈 선석 자료입니다. 선종·서비스 적합성은 별도 확인해야 합니다.'}</p>}
        {result.ship_issues.length>0 && <p className="notice warning">{result.ship_issues.map(referenceReason).join(' · ')}</p>}
        {result.observation?.position_reported_at && <p className="small">위치 보고 시각: {referenceTime(result.observation.position_reported_at)} · 제원·흘수 신고/측정 시각과 구분합니다.</p>}
        <NavigationContext registered={result.static_reference} environment={result.environment} />
        <OfficialGuidance value={result.official_guidance} />
        <div className="tablewrap mt"><table className={styles.berths}><thead><tr><th>{en?'Berth':'선석'}</th><th>{en?'Result':'부분 비교'}</th><th>{en?'Details':'신고값 / 선석 공개값 · 확인 사유'}</th></tr></thead>
          <tbody>{result.berths.map(b=><tr key={b.berth_id}>
            <th scope="row">{en?'Berth ':'선석 '}{b.berth_id.split(':BERTH:')[1]}</th><td>{berthStates[b.status] || b.status}</td><td>
              {b.checks.map(c=><p key={c.kind}><strong>{checkLabels[c.kind] || c.kind}</strong>: {metres(c.vessel_reported_m)} / {metres(c.berth_listed_m)} · {checkStates[c.status] || c.status}
                {c.reasons.length>0 && <small> · {c.reasons.map(referenceReason).join(' · ')}</small>}</p>)}
              <OperationalChecks checks={b.operational_checks} />
              <HistoricalChecks checks={b.static_reference_checks} />
              <details><summary>{en?'Source conditions (not automatically evaluated)':'원문 조건 · 자동 충족 판정 안 함'}</summary>
                {b.conditions.map((value,i)=><pre key={i} style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{value}</pre>)}</details>
            </td></tr>)}</tbody></table></div>
      </details>)}
      {nav.latest_record_draught && <p className="notice mt">{en?'Separate operation record draught':'별도 운항 기록 흘수'}: {nav.latest_record_draught.date} · {metres(nav.latest_record_draught.draught_m)}
        {nav.latest_record_draught.sample ? ' (가상 예시 기록)' : ''}. {en?'Not used for comparison. Measurement time/current loading requires confirmation.':'이 비교에는 사용하지 않았습니다. 측정 시각·현재 적재 상태 확인이 필요합니다.'}</p>}
      <details className="mt"><summary>{en?'Sources and capture times':'출처·수집 시각'}</summary>{sources.map(s=><p key={s.id}>
        <a href={link(s.url)} target="_blank" rel="noreferrer">{sourceNames[s.id] || s.id}</a> · {referenceTime(s.retrieved_at)}<br />
        <small>{s.attribution}{s.license_url && <> · <a href={link(s.license_url)} target="_blank" rel="noreferrer">이용 조건</a></>}</small>
      </p>)}</details>
    </>}
    {nav.ship && nav.port_options?.length>0 && ['unsupported_port','unsupported_berth','needs_port'].includes(nav.status) && <div className="actions wrap mt">
      {nav.port_options.map(p=><button type="button" className="btn ghost sm" key={p.port_id} data-question={shipQuery(nav.ship,p.name)}>{p.name}{en?' reference':' 자료로 조회'}</button>)}
    </div>}
  </section>;
}
