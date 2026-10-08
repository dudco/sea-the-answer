import { ships, operations, date, allowedDocs, enrichEvidence, canReadDoc, storeReport } from './workspace.mjs';
import { answerQuestion } from './rag.mjs';
import { requireValue, number } from './validation.mjs';
export function summarize(db,context={}) {
 const vessel=ships(db).find(s=>s.id===context.ship);requireValue(vessel,'대상 선박을 선택해 주세요.');
 const from=date(context.from,'시작일'),to=date(context.to,'종료일');requireValue(from<=to,'기간을 확인해 주세요.');
 const rows=operations(db).filter(r=>r.ship===vessel.id&&r.date>=from&&r.date<=to);
 const fuel=rows.reduce((a,r)=>a+r.fuel,0),emission=rows.reduce((a,r)=>a+r.fuel*r.factor,0),distance=rows.reduce((a,r)=>a+r.distance,0);
 return {ship:vessel,from,to,rows,count:rows.length,fuel,emission,distance,speed:rows.length?rows.reduce((a,r)=>a+r.speed,0)/rows.length:null,intensity:distance>0?emission*1e6/(vessel.dwt*distance):null,sample:rows.some(r=>r.sample)||vessel.sample,cii:{status:'unavailable',value:null,rating:null,reason:'연간 데이터 완전성, 선종별 산식·용량 기준, 보정·제외 조건과 적용 연도 기준 검증이 필요합니다.'}};
}
function compareCriterion(db,user,input,summary) {
 const result={status:'unknown',label:'판단 불가',reason:'검토한 기준과 적용 조건이 지정되지 않았습니다. 담당자의 규정 확인이 필요합니다.'};
 const rule=input.criterion;if(!rule)return result;
 requireValue(rule.confirmed===true,'규정의 적용 조건을 확인해 주세요.');
 requireValue(allowedDocs(db,user).includes(rule.documentId),'현재 열람 가능한 적용 중 문서가 필요합니다.');
 const chunk=db.prepare('SELECT * FROM chunks WHERE id=? AND document_id=?').get(rule.chunkId,rule.documentId);
 requireValue(chunk && typeof rule.quote==='string' && rule.quote.length>=8&&chunk.text.includes(rule.quote),'선택한 규정의 원문 구절을 정확히 입력해 주세요.');
 requireValue(['fuel','emission','intensity','speed'].includes(rule.metric),'비교할 지표를 확인해 주세요.');
 requireValue(['lte','gte'].includes(rule.operator),'비교 조건을 확인해 주세요.');
 const limit=number(rule.limit,'기준값',0,1e12),actual=summary[rule.metric];
 if(!summary.count||actual===null)return {...result,reason:'해당 기간의 비교 가능한 운항 데이터가 없습니다.'};
 const passed=rule.operator==='lte'?actual<=limit:actual>=limit;
 return {status:passed?'met':'unmet',label:passed?'입력 기준 충족':'입력 기준 미충족',actual,limit,rule,reason:'사용자가 확인·입력한 단일 기준에 대한 수치 비교입니다. 전체 규정 준수나 공식 CII 등급 판정을 의미하지 않습니다.'};
}
export async function integratedAnswer(db,user,input,options={}) {
 const language=input.language&&input.language!=='auto'?input.language:/[가-힣]/.test(input.question)?'ko':'en';
 const answer=await answerQuestion(db,{...input,language},{...options,allowedIds:allowedDocs(db,user)});
 answer.evidence=enrichEvidence(db,answer.evidence);
 const type=input.task||'auto';
 const needsOps=['operations','integrated','report'].includes(type)||(type==='auto'&&/운항|추이|분석|비교|우리|선박|조회|계산|보고서|noon|mrv|trend|our ship|vessel|consumption|calculate|report|compare/i.test(input.question));
 answer.task=needsOps?'integrated':'documents';
 if(needsOps){
  if(!input.context?.ship){answer.operationNotice=language==='en'?'Choose a vessel and period for operations analysis.':'운항 분석을 위해 질문 위의 대상 선박·기간을 선택해 주세요.';}
  else {answer.operations=summarize(db,input.context);answer.compliance=compareCriterion(db,user,input,answer.operations);answer.status=answer.operations.count?'data_found':answer.status;}
 }
 answer.reportSuggested=type==='report'||/보고서|noon|mrv|report/i.test(input.question);
 db.prepare('UPDATE queries SET response=? WHERE id=?').run(JSON.stringify(answer),answer.id);
 db.prepare('INSERT INTO query_owner VALUES (?,?)').run(answer.id,user.id);
 return answer;
}
export function generateReport(db,user,p) {
 const summary=summarize(db,p),allRows=summary.rows;
 requireValue(['noon','mrv'].includes(p.template),'보고서 양식을 선택해 주세요.');requireValue(allRows.length,'선택 기간의 운항 기록이 없습니다.');
 if(p.template==='noon'){const last=allRows.at(-1);Object.assign(summary,summarize(db,{...p,from:last.date,to:last.date}));}
 const s=summary,last=s.rows.at(-1),label=p.template==='noon'?'Noon Report':'MRV 검토 보고서';
 const missing=v=>v===null||v===undefined||v===''?'[미입력 · 확인 필요]':v;
 const text=`# ${label}\n\n상태: 검토용 초안${s.sample?' · 가상 예시 데이터 포함':''}\n선박: ${s.ship.name}\nIMO: ${missing(s.ship.imo)}\n선종: ${s.ship.type}\nDWT: ${s.ship.dwt} t\n기간: ${s.from} ~ ${s.to}\n작성자: ${user.name}\n항차: ${missing(last.voyage)}\n항로: ${missing(s.ship.from)} → ${missing(s.ship.to)}\n기록 수: ${s.count}\n\n## 운항·연료 기록\n${s.rows.map(r=>`${r.date} | 연료 ${r.fuel} t (${r.fuelType}) | 배출계수 ${r.factor} | CO₂ ${r.fuel*r.factor} t | 거리 ${r.distance} nm | 속력 ${r.speed} kn`).join('\n')}\n\n## 집계\n연료 합계: ${s.fuel} t\nCO₂ 합계: ${s.emission} t\n거리 합계: ${s.distance} nm\n일별 속력 평균: ${s.speed} kn\n단순 탄소집약도: ${s.intensity??'산출 불가'} gCO₂/(DWT·nm)\n산식: CO₂ = Σ(각 기록의 연료 × 배출계수), 집약도 = CO₂ × 10⁶ / (DWT × 거리)\nCII: 산출 불가 — ${s.cii.reason}\n\n## 운항 상세\n위치: ${missing(last.position)}\n흘수: ${missing(last.draft)} m\n기상: ${missing(last.weather)}\n기관 운전시간: ${missing(last.engineHours)} h\n점검 사항: ${missing(last.note)}\n\n## 검토\n누락 항목, 연료별 배출계수, 기간의 완전성과 원본 기록을 담당자가 확인해야 합니다. 이 양식은 팀의 검토용 양식이며 공식 제출 서식 인증을 의미하지 않습니다.`;
 const body={template:p.template,ship:s.ship.id,from:s.from,to:s.to,recordIds:s.rows.map(r=>({id:r.id,version:r.version})),sample:s.sample};
 return storeReport(db,user,{title:`${s.ship.name} · ${label} · ${s.from}`,type:p.template==='noon'?'일일 운항':'배출량 검토',text,sources:[],version:0,body});
}
