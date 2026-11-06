const reasons = {
  AIS_OBSERVATION_UNAVAILABLE: '이 자료에 해당 선박의 AIS 신고값이 없음',
  AIS_STATIC_TIME_UNVERIFIED: '위치 보고 시각만 있어 제원·흘수 신고 시각은 미확인',
  AIS_UNITS_UNVERIFIED: '공식 명세에서 치수 단위가 확정되지 않아 수치 비교 보류',
  AIS_IDENTITY_AMBIGUOUS: 'IMO·MMSI 식별자가 중복되거나 불명확함',
  AIS_RECORD_STALE: 'AIS 기록이 24시간 기준을 지남',
  AIS_CAPTURE_STALE: 'AIS 수집 자료가 24시간 기준을 지남',
  AIS_RECORD_TIME_UNKNOWN: 'AIS 기록 시각을 확인할 수 없음',
  AIS_LENGTH_UNAVAILABLE: '신고 전장 없음', AIS_BEAM_UNAVAILABLE: '신고 선폭 없음',
  AIS_DRAUGHT_UNAVAILABLE: '정확한 신고 흘수 없음',
  AIS_DRAUGHT_LOWER_BOUND: 'AIS 흘수가 하한값으로 신고돼 정확한 값 비교를 보류함',
  PORT_CAPTURE_STALE: '항구 자료 수집 후 30일이 지남',
  CATALOG_STALE: '참조 자료 생성 후 30일이 지남',
  DUPLICATE_BERTH_VARIANTS_REQUIRE_REVIEW: '같은 선석 번호의 조건이 여러 개여서 검토 필요',
};
export function referenceReason(value) {
  if (reasons[value]) return reasons[value];
  if (value?.startsWith('BERTH_')) return '선석 한계값이 없거나 별도 조건 검토가 필요함';
  if (value?.endsWith('_TIME_IN_FUTURE')) return '자료 시각이 서버 시각보다 미래임';
  if (value?.endsWith('_TIME_UNKNOWN')) return '자료 시각을 확인할 수 없음';
  return value || '확인 필요';
}
export function metres(value) {
  return value === null || value === undefined || value === '' ? '자료 없음' : `${value} m`;
}
export function referenceTime(value) {
  if (!value || !Number.isFinite(Date.parse(value))) return '시각 미확인';
  return new Date(value).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul', hour12: false }) + ' (한국 시각)';
}
export const checkLabels = { length: '전장', beam: '선폭', draught: '흘수' };
export const checkStates = { within_listed_reference: '공개 수치 이내', above_listed_reference: '공개 수치 초과', unavailable: '비교 보류' };
export const berthStates = { partial_reference_check: '일부 수치 비교', published_reference_exceeded: '공개 수치 초과 항목 있음', insufficient_data: '비교 자료 부족' };
