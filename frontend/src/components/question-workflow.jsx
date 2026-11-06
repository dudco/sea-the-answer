'use client';
import React, {useState} from 'react';
import {useWorkspace} from '../workspace/provider';
import {SkillResult} from './skill-result';

const statuses={completed:'조회 완료',estimated:'참고값 계산 완료',blocked:'계산 불가',no_data:'기간 내 기록 없음',unavailable:'자료 확인 불가'};
const metrics={fuel_t:'연료 사용량',calculated_co2_t:'계산 CO₂',distance_nm:'항해거리',reference_dwt_intensity:'MRV 참고 탄소집약도'};

export default function QuestionWorkflow({answer}) {
  return <Workflow key={answer.id} answer={answer} />;
}
function Workflow({answer}) {
  const {workspace}=useWorkspace(), flow=answer.workflow, scope=flow.scope;
  const [ship,setShip]=useState(''),[second,setSecond]=useState(''),[years,setYears]=useState('');
  const [start,setStart]=useState(''),[end,setEnd]=useState(''),[docs,setDocs]=useState([]),[ack,setAck]=useState(false),[error,setError]=useState('');
  const missing=flow.missing || [];
  async function submit(event) {
    event.preventDefault();event.stopPropagation();setError('');
    const reply={};
    if(missing.includes('ships'))reply.ships=[ship,second].filter(Boolean);
    if(missing.includes('years'))reply.years=years.split(/[,\s]+/).filter(Boolean).map(Number);
    if(missing.includes('periods'))reply.periods=[{start,end}];
    if(missing.includes('document_ids'))reply.document_ids=docs;
    if(missing.includes('reference_ack'))reply.reference_ack=ack;
    try { await workspace.ask('조건을 보완해서 다시 실행해줘',reply); }
    catch(e){setError(e.message);}
  }
  return <section className="mt" data-question-workflow>
    <h3>해석한 실행 범위</h3>
    <p>{scope.action==='selected_document' ? `선택 문서 ${scope.document_ids.length}개` : scope.ships?.map(s=>s.name).join(' / ') || '선박 미지정'}
      {['mrv_reference','combined'].includes(scope.action) && scope.years?.length>0 && <> · MRV 연도 {scope.years.join(', ')}</>}
      {scope.periods?.map((p,i)=><React.Fragment key={i}> · {p.start}~{p.end}</React.Fragment>)}</p>
    <p className="small muted">{flow.routing.method==='llm'?'AI 작업 선택·서버 범위 검증':'규칙 기반 조건 해석'}
      {flow.routing.fallback && ' · 모델 제안을 사용할 수 없어 규칙/추가 확인으로 처리'}
      {flow.previous_query_id && ' · 이전 범위를 연결해 현재 자료로 재조회'}</p>
    {missing.length>0 && <form className="card pad mt" onSubmit={submit} onInput={e=>e.stopPropagation()} onChange={e=>e.stopPropagation()}>
      <h3>추가로 필요한 조건</h3>
      {missing.includes('ships') && <div className="controls">
        <label className="field">조회 선박<select aria-label="업무 조회 선박" required value={ship} onChange={e=>setShip(e.target.value)}>
          <option value="">선박 선택</option>{flow.options.ships.map(s=><option key={s.id} value={s.id}>{s.name} {s.imo}</option>)}
        </select></label>
        <label className="field">비교 선박 (선택)<select aria-label="업무 비교 선박" value={second} onChange={e=>setSecond(e.target.value)}>
          <option value="">추가하지 않음</option>{flow.options.ships.filter(s=>s.id!==ship).map(s=><option key={s.id} value={s.id}>{s.name}</option>)}
        </select></label></div>}
      {missing.includes('years') && <label className="field">MRV 보고연도 (최대 3개)<input aria-label="업무 보고연도" required placeholder="2024, 2025" value={years} onChange={e=>setYears(e.target.value)} /></label>}
      {missing.includes('periods') && <div className="controls"><label className="field">시작일<input aria-label="업무 시작일" type="date" required value={start} onChange={e=>setStart(e.target.value)} /></label>
        <label className="field">종료일<input aria-label="업무 종료일" type="date" required value={end} onChange={e=>setEnd(e.target.value)} /></label></div>}
      {missing.includes('document_ids') && <label className="field">사용할 문서 (최대 5개)<select aria-label="업무 선택 문서" multiple required value={docs} onChange={e=>setDocs([...e.target.selectedOptions].map(v=>v.value))}>
        {flow.options.documents.map(d=><option key={d.id} value={d.id}>{d.title}</option>)}
      </select></label>}
      {missing.includes('reference_ack') && <label><input aria-label="MRV 참고값 동의" type="checkbox" required checked={ack} onChange={e=>setAck(e.target.checked)} /> MRV 기반 참고 탄소집약도 계산에 동의합니다. 공식 CII·등급이 아닙니다.</label>}
      <p className="small">자연어로 선박·연도·기간을 답해도 됩니다. 아래 입력은 현재 되묻기에만 적용합니다.</p>
      <button className="btn primary" disabled={workspace.state.busy} type="submit">조건 적용 후 조회</button>
      {error && <p role="alert">{error}</p>}
    </form>}
    {flow.results?.map((row,i)=><section className="card pad mt" key={i} data-workflow-result>
      {row.kind==='mrv_reference' && <h3>{row.label}</h3>}
      <p className="small">{row.kind==='mrv_reference'?'실제 MRV 연간 자료·참고 계산':'앱 일별 운항 기록'} · {statuses[row.status] || row.status}</p>
      <SkillResult answer={{result:row.result,warnings:[]}} />
    </section>)}
    {flow.comparisons?.length>0 && <section className="card pad mt"><h3>입력 결과의 산술 비교</h3>
      {flow.comparisons.map((c,i)=><p key={i}>{c.base} → {c.target}<br />{metrics[c.metric] || c.metric}: 차이 {c.difference ?? '비교 불가'} {c.unit} · 변화율 {c.percent_change==null?'산출 불가':`${c.percent_change}%`}</p>)}
      <p className="small muted">{flow.comparisons[0].notice}</p>
    </section>}
  </section>;
}
