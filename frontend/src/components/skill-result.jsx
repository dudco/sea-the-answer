import React from 'react';

const labels = {
  NO_ELIGIBLE_ANNUAL_RECORD: '선택 연도의 승인 MRV 보고가 없습니다.',
  MULTIPLE_ANNUAL_RECORDS_REQUIRE_REVIEW: '보고가 여러 건이라 검토가 필요합니다.',
  CAPACITY_REFERENCE_UNAVAILABLE: 'DWT 후보가 없습니다.',
  MISSING_OR_INVALID_REFERENCE_DWT: '유효한 DWT 후보가 없습니다.',
  CAPACITY_SOURCE_CONFLICT: '공개 출처의 DWT 값이 충돌합니다.',
  SOURCE_AND_REFERENCE_DWT_CONFLICT: '원본과 후보 DWT가 충돌합니다.',
  SHIP_TYPE_CAPACITY_BASIS_UNSUPPORTED: '이 선종은 현재 참고 계산 지원 범위 밖입니다.',
  MODEL_NOT_CONFIGURED: 'AI가 설정되지 않아 원문 발췌를 사용했습니다.',
  MODEL_FAILED_EXTRACTIVE_FALLBACK: 'AI 응답을 검증하지 못해 원문 발췌를 사용했습니다.',
  SYNTHETIC_OR_SAMPLE_OPERATIONS: '가상 예시 운항자료가 포함되어 있습니다.',
  PERIOD_HAS_UNREPORTED_DAYS: '선택 기간에 기록이 없는 날짜가 있습니다.',
};
export function SkillResult({ answer, draftSaved }) {
  const r = answer?.result || {};
  if (!Object.keys(r).length && !answer?.warnings?.length) return null;
  return <section className="skill-result" aria-label="업무 결과">
    {r.reference_only && <>
      <h3>MRV 기반 참고 탄소집약도</h3>
      <p className="skill-value">{r.reference_dwt_intensity ?? '계산 불가'} <small>{r.units?.reference_dwt_intensity}</small></p>
      <p>보고 CO₂ {r.source_reported_co2_t ?? '미제공'} t · 공개 DWT 후보 {r.candidate_dwt_t ?? '미제공'} t · 추정거리 {r.distance_nm_estimate ?? '미제공'} nm</p>
      <p>공식 CII·등급은 산출하지 않습니다. 보고 범위와 제원 기준연도가 검증되지 않은 참고값입니다.</p>
      {r.blockers?.length > 0 && <ul>{r.blockers.map(v=><li key={v}>{labels[v] || v}</li>)}</ul>}
    </>}
    {r.fuel_t !== undefined && <>
      <h3>{r.ship?.name} · {r.from} ~ {r.to}</h3>
      <dl className="skill-metrics">
        <div><dt>연료 합계</dt><dd>{r.fuel_t} t</dd></div>
        <div><dt>계산 CO₂</dt><dd>{r.calculated_co2_t} t CO₂</dd></div>
        <div><dt>거리 합계</dt><dd>{r.distance_nm} nm</dd></div>
        <div><dt>보고일 / 달력일</dt><dd>{r.reported_days} / {r.calendar_days}</dd></div>
      </dl>
      <p>{r.notice}</p>
      {r.sample && <p className="notice warning">가상 예시 데이터가 포함되어 있습니다.</p>}
    </>}
    {r.items && <>
      <h3>점검 항목 초안</h3><p>{r.notice}</p>
      <ol>{r.items.map((item,i)=><li key={`${item.chunkId}-${i}`}><label><input type="checkbox" aria-label={`점검 항목 ${i+1}`} /> {item.text}</label></li>)}</ol>
      <p className="small muted">체크 표시는 이 화면에서만 사용하며 점검 완료·승인을 서버에 기록하지 않습니다.</p>
    </>}
    {r.checks && <>
      <h3>질의·응답 평가</h3><p>{r.notice}</p>
      <div className="table-wrap"><table><thead><tr><th>점검</th><th>결과</th><th>설명</th></tr></thead><tbody>
        {r.checks.map(v=><tr key={v.check}><td>{v.check}</td><td>{{pass:'통과',fail:'실패',not_applicable:'해당 없음',manual_review_required:'사람 검토 필요'}[v.status] || v.status}</td><td>{v.detail}</td></tr>)}
      </tbody></table></div>
    </>}
    {r.draft && <><h3>검토용 보고서 초안</h3><textarea aria-label="보고서 초안 내용" readOnly rows={14} value={r.draft.text} /><p>{draftSaved === true ? '새 보고서 초안으로 저장했습니다. 제출되지 않았습니다.' : draftSaved === false ? '아직 저장·제출되지 않았습니다.' : '생성 당시의 미리보기입니다. 현재 저장·제출 상태는 보고서에서 확인하세요.'}</p></>}
    {answer.warnings?.filter(v=>labels[v]).map(v=><p key={v} className="small">{labels[v]}</p>)}
    {Object.keys(r).length > 0 && <details><summary>조회·계산 근거 상세</summary><pre className="skill-json">{JSON.stringify(r,null,2)}</pre></details>}
  </section>;
}
