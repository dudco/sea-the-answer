'use client';
import {UiText,UiControl} from './ui-language';
import React, {useState} from 'react';
import {useWorkspace} from '../workspace/provider';
import {SkillResult} from './skill-result';

const statuses={completed:'조회 완료',estimated:'참고값 계산 완료',blocked:'계산 불가',no_data:'기간 내 기록 없음',unavailable:'자료 확인 불가'};
const metrics={fuel_t:'연료 사용량',calculated_co2_t:'계산 CO₂',distance_nm:'항해거리',reference_dwt_intensity:'MRV 참고 탄소집약도'};

// part='answer': clarification and results (what the user asked); part='details': interpreted scope (behind the toggle).
export default function QuestionWorkflow({answer, part='all', results=true}) {
  return <Workflow key={answer.id} answer={answer} part={part} results={results} />;
}
function Workflow({answer, part, results}) {
  const {workspace}=useWorkspace(), flow=answer.workflow, scope=flow.scope;
  const [error,setError]=useState('');
  const [visibleChoices,setVisibleChoices]=useState(8);
  const missing=flow.missing || [];
  const field=flow.clarification===null ? null : flow.clarification?.field || missing[0];
  const current=workspace.state.answer?.id===answer.id;
  const documents=scope.document_ids.map(id=>{
    const doc=workspace.state.docs.find(d=>d.id===id) || workspace.state.turns.flatMap(t=>t.answer?.workflow?.options?.documents || []).find(d=>d.id===id);
    return doc ? [doc.title,doc.version && `v${doc.version}`].filter(Boolean).join(' · ') : id;
  });
  const choices=field==='ships' ? (flow.options?.ships || []).map(s=>({
    id:s.id,label:[s.name,s.imo && `IMO ${String(s.imo).replace(/^IMO\s*/i,'')}`,s.type,s.sample?'가상 예시':''].filter(Boolean).join(' · '),
    question:s.name,input:{ships:[s.id]},
  })) : field==='document_ids' ? (flow.options?.documents || []).map(d=>({
    id:d.id,label:[d.title,d.version && `v${d.version}`,d.reference].filter(Boolean).join(' · '),
    question:d.title,input:{document_ids:[d.id]},
  })) : field==='reference_ack' ? [
    {id:'accept',label:'참고값으로 확인',question:'참고값으로 계산해줘',input:{reference_ack:true}},
    {id:'decline',label:'진행하지 않기',question:'아니요',input:{reference_ack:false}},
  ] : [];
  async function choose(choice) {
    if(workspace.state.busy || workspace.state.answer?.id!==answer.id)return;
    setError('');
    try { await workspace.ask(choice.question,choice.input,answer.id); }
    catch(e){setError(e.message);}
  }
  const showScope=part!=='answer', showClarify=part!=='details';
  return <section className="mt" data-question-workflow={part}>
    {showScope && <>
    <h3><UiText>{"해석한 실행 범위"}</UiText></h3>
    <p><UiText>{scope.action==='selected_document' ? `선택 문서 ${scope.document_ids.length}개` : scope.ships?.map(s=>s.name+(s.imo ? ` · IMO ${String(s.imo).replace(/^IMO\s*/i,'')}` : '')).join(' / ') || '선박 미지정'}</UiText>
      {documents.length>0 && <> · {documents.join(' / ')}</>}
      {['mrv_reference','combined'].includes(scope.action) && scope.years?.length>0 && <><UiText>{"· MRV 연도"}</UiText>{scope.years.join(', ')}</>}
      {scope.periods?.map((p,i)=><React.Fragment key={i}> · {p.start}~{p.end}</React.Fragment>)}</p>
    <p className="small muted"><UiText>{flow.routing.method==='llm'?'AI 작업 선택·서버 범위 검증':'규칙 기반 조건 해석'}</UiText>
      {flow.routing.fallback && ' · 모델 제안을 사용할 수 없어 규칙/추가 확인으로 처리'}
      {flow.previous_query_id && ' · 이전 범위를 연결해 현재 자료로 재조회'}</p>
    </>}
    {showClarify && missing.length>0 && field && current && <div className="mt" data-workflow-clarification>
      <p className="small"><UiText>{'아래 질문창에 답하면 이어서 조회합니다.'}</UiText></p>
      {choices.length>0 && <>
        <UiControl as="div" role="group" aria-label="현재 질문의 후보" className="actions wrap mt">
          {choices.slice(0,visibleChoices).map(c=><button type="button" className="btn ghost sm" key={c.id}
            data-workflow-choice={c.id} disabled={workspace.state.busy} onClick={()=>choose(c)}
            style={{whiteSpace:'normal',textAlign:'left',overflowWrap:'anywhere'}}>
            <UiText>{c.label}</UiText>{choices.filter(v=>v.label===c.label).length>1 && <small> · {c.id}</small>}
          </button>)}
        </UiControl>
        {choices.length>visibleChoices && <button type="button" className="btn ghost sm mt" disabled={workspace.state.busy}
          onClick={()=>setVisibleChoices(v=>v+8)}><UiText>{'후보 더 보기'}</UiText></button>}
        {field!=='reference_ack' && <p className="small muted"><UiText>{'이름으로 답하거나 후보를 누르세요. 여러 대상은 이름을 함께 적어 주세요.'}</UiText></p>}
      </>}
      {error && <p role="alert">{error}</p>}
    </div>}
    {results && flow.results?.map((row,i)=><section className="card pad mt" key={i} data-workflow-result>
      {row.kind==='mrv_reference' && <h3>{row.label}</h3>}
      <p className="small"><UiText>{row.kind==='mrv_reference'?'실제 MRV 연간 자료·참고 계산':'앱 일별 운항 기록'}</UiText> · <UiText>{statuses[row.status] || row.status}</UiText></p>
      <SkillResult answer={{result:row.result,warnings:[]}} />
    </section>)}
    {results && flow.comparisons?.length>0 && <section className="card pad mt"><h3><UiText>{"입력 결과의 산술 비교"}</UiText></h3>
      {flow.comparisons.map((c,i)=><p key={i}>{c.base} → {c.target}<br /><UiText>{metrics[c.metric] || c.metric}</UiText><UiText>{": 차이"}</UiText>{c.difference ?? '비교 불가'} {c.unit}<UiText>{"· 변화율"}</UiText><UiText>{c.percent_change==null?'산출 불가':`${c.percent_change}%`}</UiText></p>)}
      <p className="small muted">{flow.comparisons[0].notice}</p>
    </section>}
  </section>;
}
