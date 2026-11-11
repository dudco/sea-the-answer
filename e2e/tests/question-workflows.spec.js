import {test,expect} from '@playwright/test';

const ship={id:'ship-a',name:'해답호',imo:'7422881',version:1,dwt:1000,type:'Bulk carrier'};
const scope={action:'mrv_reference',ships:[ship],years:[],periods:[],document_ids:[],reference_ack:true,mappings:{}};
function answer(id,flow,extra={}) {
 return {id,question:'test',task:'workflow',language:'ko',generation:'workflow',status:'needs_input',notice:'추가 조건을 알려 주세요.',
  warnings:[],statements:[],evidence:[],toolRuns:[],reportSuggested:false,
  workflow:{version:'HAEDAP-QUESTION-WORKFLOW-1.0',scope,missing:[],options:{ships:[],documents:[]},routing:{method:'rules',model_attempted:false},results:[],comparisons:[],...flow},...extra};
}
async function setup(page,handler,llmConfigured=false) {
 const calls=[],errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/api/**',route=>{
  const req=route.request(),path=new URL(req.url()).pathname;
  const send=data=>route.fulfill({contentType:'application/json',body:JSON.stringify(data)});
  if(path==='/api/health')return send({csrfToken:'test',user:{id:'viewer',name:'업무 검증자',role:'viewer',version:1},authenticated:true,publicAccess:false,llmConfigured});
  if(path==='/api/operations')return send({ships:[ship,{...ship,id:'ship-b',name:'별빛호',imo:'9074729'}],records:[]});
  if(path==='/api/documents')return send({documents:[{id:'doc-a',title:'선박 안전 문서',version:'1',active:true,kind:'manual'}]});
  if(path==='/api/ask'){const body=req.postDataJSON();calls.push(body);return send(handler(body,calls.length));}
  return send({skills:[],history:[],reports:[],evidence:[]});
 });
 await page.goto('/chat');await expect(page.locator('#question')).toBeVisible();return {calls,errors};
}
async function ask(page,text) {
 await page.locator('#question').fill(text);const count=await page.locator('.chat-turn').count();
 await page.getByRole('button',{name:'질문 보내기',exact:true}).click();
 await expect(page.locator('.chat-turn')).toHaveCount(count+1);
 await expect(page.locator('.chat-turn').nth(count).locator('[data-question-workflow]')).toBeVisible();
}

test('clarification submits only current parent and shows blocked years without invented ratings',async({page})=>{
 const first='11111111-1111-4111-8111-111111111111',second='22222222-2222-4222-8222-222222222222';
 const state=await setup(page,(body,n)=>n===1?answer(first,{missing:['years']}):answer(n===2?second:'66666666-6666-4666-8666-666666666666',{
  scope:{...scope,years:[2024,2025]},previous_query_id:first,
  results:[{kind:'mrv_reference',label:'해답호 · 2024',status:'estimated',result:{reference_only:true,reference_dwt_intensity:'1.500000',units:{reference_dwt_intensity:'gCO2/(DWT t * nm)'},blockers:[]}},
    {kind:'mrv_reference',label:'해답호 · 2025',status:'blocked',result:{reference_only:true,reference_dwt_intensity:null,blockers:['NO_ELIGIBLE_ANNUAL_RECORD']}}]
 },{status:'partial',notice:'참고값과 계산 불가 사유를 확인하세요.'}));
 await ask(page,'우리 배의 MRV 참고 탄소집약도를 계산해줘');
 await ask(page,'2024년과 2025년');
 await expect(page.locator('[data-workflow-result]')).toHaveCount(2);
 expect(state.calls[1].workflowInput).toBeUndefined();
 expect(state.calls[1].context.previousQueryId).toBe(first);
 await expect(page.locator(`[data-answer-id="${second}"] [data-question-workflow]`)).toContainText('계산 불가');
 await expect(page.locator(`[data-answer-id="${second}"] [data-question-workflow]`)).toContainText('공식 CII·등급은 산출하지 않습니다.');
 await ask(page,'그럼 2023년은?');expect(state.calls[2].context.previousQueryId).toBe(second);
 expect(state.errors).toEqual([]);
});

test('selected-document clarification works even when operation ship is selected',async({page})=>{
 const id='33333333-3333-4333-8333-333333333333';
 const docScope={...scope,action:'selected_document',ships:[],document_ids:[]};
 const state=await setup(page,(body,n)=>n===1?answer(id,{scope:docScope,missing:['document_ids'],options:{ships:[],documents:[{id:'doc-a',title:'선박 안전 문서'}]}}):
  answer('44444444-4444-4444-8444-444444444444',{scope:{...docScope,document_ids:['doc-a']},previous_query_id:id},
    {status:'completed',statements:[{text:'선택한 문서의 확인 문구',chunkId:'c',quote:'선택한 문서의 근거입니다.'}],evidence:[{id:'c',document_id:'doc-a',title:'선박 안전 문서',version:'1',text:'선택한 문서의 근거입니다.'}]}));
 await ask(page,'선택한 문서만 사용해서 요약해줘');
 await page.locator('[data-workflow-choice="doc-a"]').click();
 await expect(page.locator('main')).toContainText('선택한 문서의 확인 문구');
 expect(state.calls[1].workflowInput.document_ids).toEqual(['doc-a']);expect(state.calls[1].context.previousQueryId).toBe(id);
 expect(state.errors).toEqual([]);
});

test('new question reset drops workflow continuation',async({page})=>{
 const state=await setup(page,()=>answer('55555555-5555-4555-8555-555555555555',{missing:['years']}));
 await ask(page,'우리 배의 MRV 참고 탄소집약도를 계산해줘');
 await page.getByRole('button',{name:'새 질문',exact:true}).click();
 await ask(page,'우리 배의 2025년 연료 사용량을 알려줘');
 expect(state.calls[1].context.previousQueryId).toBeUndefined();expect(state.errors).toEqual([]);
});

test('questions carry no answer mode and show the tools the server ran with related documents',async({page})=>{
 const routing={method:'model_tools',toolCalls:[{name:'search_documents',status:'completed'},{name:'calculate_mrv_reference',status:'needs_input'}]};
 const state=await setup(page,()=>answer('aaaaaaa1-aaaa-4aaa-8aaa-aaaaaaaaaaaa',{missing:['years']},
   {routing,relatedEvidence:[{id:'c',document_id:'doc-a',title:'선박 안전 문서',version:'1',text:'관련 근거입니다.'}]}),true);
 await expect(page.getByLabel('답변 방식',{exact:true})).toHaveCount(0);
 await ask(page,'MRV 참고 탄소집약도 계산해줘');expect(state.calls[0].mode).toBeUndefined();
 const turn=page.locator('[data-answer-id="aaaaaaa1-aaaa-4aaa-8aaa-aaaaaaaaaaaa"]');
 // Answer first: tools and related documents stay behind the details toggle until opened.
 await expect(turn.getByTestId('tool-calls')).toBeHidden();
 await turn.getByTestId('answer-details').locator('summary').click();
 await expect(turn.getByTestId('tool-calls')).toBeVisible();
 await expect(turn.getByTestId('tool-calls')).toContainText('search_documents');
 await expect(turn.getByTestId('tool-calls')).toContainText('calculate_mrv_reference');
 await expect(turn.getByTestId('answer-details')).toContainText('관련 문서');
 expect(state.errors).toEqual([]);
});

test('question box alone fills missing ship and period without opening tool forms',async({page},testInfo)=>{
 const first='77777777-7777-4777-8777-777777777777',second='88888888-8888-4888-8888-888888888888';
 const operationScope={...scope,action:'operations_summary',ships:[],years:[],periods:[],reference_ack:false};
 const state=await setup(page,(body,n)=>n===1?answer(first,{
  scope:operationScope,missing:['ships','periods'],options:{ships:[ship],documents:[]},
  clarification:{field:'ships',question:'어느 선박의 자료를 확인할까요?'}
 },{notice:'어느 선박의 자료를 확인할까요?'}):n===2?answer(second,{
  scope:{...operationScope,ships:[ship]},missing:['periods'],previous_query_id:first,
  clarification:{field:'periods',question:'어느 기간의 운항 실적을 확인할까요?'}
 },{notice:'어느 기간의 운항 실적을 확인할까요?'}):answer('99999999-9999-4999-8999-999999999999',{
  scope:{...operationScope,ships:[ship],periods:[{start:'2025-01-01',end:'2025-01-31'}]},previous_query_id:second,
  results:[{kind:'operations_summary',status:'completed',result:{ship,from:'2025-01-01',to:'2025-01-31',
   count:1,reported_days:1,calendar_days:31,missing_days:30,fuel_t:'2.000000',calculated_co2_t:'6.228000',distance_nm:'100.000000',sample:true}}]
 },{status:'completed',notice:'조회 완료'}));
 await ask(page,'우리 배 연료 사용량을 알려줘');
 expect(state.calls[0].context.ship).toBe('');expect(state.calls[0].context.from).toBeUndefined();
 await expect(page.locator('[data-question-workflow] select')).toHaveCount(0);
 await ask(page,'해답호');
 expect(state.calls[1].context.previousQueryId).toBe(first);
 await expect(page.locator('[data-question-workflow] input')).toHaveCount(0);
 await ask(page,'2025년 1월');
 expect(state.calls[2].context.previousQueryId).toBe(second);
 expect(state.calls.every(c=>c.workflowInput===undefined)).toBe(true);
 await expect(page.locator('[data-workflow-result]')).toContainText('2.000000');
 await expect(page.locator('.chat-turn')).toHaveCount(3);
 await page.setViewportSize({width:390,height:844});
 await expect.poll(()=>page.locator('.sidebar').evaluate(e=>e.getBoundingClientRect().right)).toBeLessThanOrEqual(1);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
 await page.screenshot({path:testInfo.outputPath('conversation-mobile.png'),fullPage:true});
 expect(state.errors).toEqual([]);
});

test('only current document candidates are shown and duplicate titles retain distinct versions',async({page},testInfo)=>{
 const first='bbbbbbb1-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
 const docScope={...scope,action:'selected_document',ships:[],document_ids:[]};
 const state=await setup(page,(body,n)=>n===1?answer(first,{
  scope:docScope,missing:['document_ids'],clarification:{field:'document_ids',question:'어느 문서인가요?'},
  options:{ships:[],documents:[{id:'doc-a',title:'기관 점검 문서',version:'1',reference:'초판'},
    {id:'doc-b',title:'기관 점검 문서',version:'2',reference:'개정판'}]}
 }):answer('bbbbbbb2-bbbb-4bbb-8bbb-bbbbbbbbbbbb',{
  scope:{...docScope,document_ids:['doc-b']},results:[]
 },{status:'insufficient_evidence',notice:'선택 문서에 근거가 없습니다.'}));
 await expect(page.locator('.query-context')).toHaveCount(0);
 await ask(page,'선택한 문서에서 연료 전환 절차를 알려줘');
 await expect(page.locator('[data-workflow-clarification] input,[data-workflow-clarification] select')).toHaveCount(0);
 await expect(page.locator('[data-workflow-choice]')).toHaveCount(2);
 await expect(page.locator('[data-workflow-choice="doc-b"]')).toContainText('v2');
 await page.setViewportSize({width:390,height:844});
 await expect.poll(()=>page.locator('.sidebar').evaluate(e=>e.getBoundingClientRect().right)).toBeLessThanOrEqual(1);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
 await page.screenshot({path:testInfo.outputPath('document-candidates-mobile.png'),fullPage:true});
 await page.locator('[data-workflow-choice="doc-b"]').click();
 await expect.poll(()=>state.calls.length).toBe(2);
 expect(state.calls[1].workflowInput).toEqual({document_ids:['doc-b']});
 expect(state.calls[1].context.previousQueryId).toBe(first);
 await expect(page.locator('[data-workflow-choice]')).toHaveCount(0);
 expect(state.errors).toEqual([]);
});

test('reference value confirmation is explicit and decline never requests calculation',async({page})=>{
 const first='ccccccc1-cccc-4ccc-8ccc-cccccccccccc';
 const state=await setup(page,(body,n)=>n===1?answer(first,{
  scope:{...scope,years:[2024],reference_ack:false},missing:['reference_ack'],
  clarification:{field:'reference_ack',question:'참고값으로 확인할까요?'}
 }):answer('ccccccc2-cccc-4ccc-8ccc-cccccccccccc',{
  scope:{...scope,years:[2024],reference_ack:false},missing:['reference_ack'],clarification:null
 },{notice:'계산을 진행하지 않았습니다.'}));
 await ask(page,'우리 배의 공식 CII를 계산해줘');
 expect(state.calls.length).toBe(1);
 await expect(page.getByRole('checkbox')).toHaveCount(0);
 await page.getByRole('button',{name:'진행하지 않기',exact:true}).click();
 await expect.poll(()=>state.calls.length).toBe(2);
 expect(state.calls[1].workflowInput).toEqual({reference_ack:false});
 expect(state.calls[1].context.previousQueryId).toBe(first);
 await expect(page.locator('[data-workflow-result]')).toHaveCount(0);
 await expect(page.locator('[data-workflow-choice]')).toHaveCount(0);
 expect(state.errors).toEqual([]);
});

test('new questions remove obsolete ship candidates instead of permitting a stale choice',async({page})=>{
 const state=await setup(page,()=>answer('ddddddd1-dddd-4ddd-8ddd-dddddddddddd',{
  scope:{...scope,ships:[]},missing:['ships','years'],options:{ships:[ship],documents:[]},
  clarification:{field:'ships',question:'어느 선박인가요?'}
 }));
 await ask(page,'MRV 참고값 계산해줘');
 await expect(page.locator('[data-workflow-choice="ship-a"]')).toBeVisible();
 await page.getByRole('button',{name:'새 질문',exact:true}).click();
 await expect(page.locator('[data-workflow-choice]')).toHaveCount(0);
 expect(state.calls.length).toBe(1);
 expect(state.errors).toEqual([]);
});

test('more choices keeps later revisions with the same title reachable',async({page})=>{
 const first='eeeeeee1-eeee-4eee-8eee-eeeeeeeeeeee';
 const docScope={...scope,action:'selected_document',ships:[],document_ids:[]};
 const state=await setup(page,(body,n)=>n===1?answer(first,{
  scope:docScope,missing:['document_ids'],options:{ships:[],documents:Array.from({length:9},(_,i)=>({
   id:`revision-${i+1}`,title:'기관 매뉴얼',version:String(i+1)
  }))}
 }):answer('eeeeeee2-eeee-4eee-8eee-eeeeeeeeeeee',{
  scope:{...docScope,document_ids:['revision-9']}
 },{status:'insufficient_evidence'}));
 await ask(page,'선택한 문서에서 점검 항목 알려줘');
 await expect(page.locator('[data-workflow-choice]')).toHaveCount(8);
 await page.getByRole('button',{name:'후보 더 보기',exact:true}).click();
 await page.locator('[data-workflow-choice="revision-9"]').click();
 await expect.poll(()=>state.calls.length).toBe(2);
 expect(state.calls[1].workflowInput).toEqual({document_ids:['revision-9']});
 expect(state.errors).toEqual([]);
});

test('AI fallback explains timeout and citation rejection as different failures',async({page})=>{
 const state=await setup(page,(body,n)=>({id:'failure-'+n,question:body.question,task:'documents',language:'ko',
  generation:'extractive',status:'insufficient_evidence',notice:'원문 근거를 확인하세요.',
  warnings:['MODEL_FAILED_EXTRACTIVE_FALLBACK'],statements:[],evidence:[],toolRuns:[],reportSuggested:false,
  generationFailure:{code:n===1?'MODEL_TIMEOUT':'MODEL_CITATION_MISMATCH',retryable:n===1}
 }),true);
 await page.locator('#question').fill('조종불능선에 대해 설명해줘');
 await page.getByRole('button',{name:'질문 보내기',exact:true}).click();
 await expect(page.locator('.answer').last()).toContainText('모델 응답 대기 시간이 초과됐습니다');
 await page.locator('#question').fill('다른 설명도 알려줘');
 await page.getByRole('button',{name:'질문 보내기',exact:true}).click();
 await expect(page.locator('.answer').last()).toContainText('인용을 원문에서 확인하지 못해');
 expect(state.errors).toEqual([]);
});
