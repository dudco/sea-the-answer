import {test,expect} from '@playwright/test';

const ship={id:'ship-a',name:'해답호',imo:'7422881',version:1,dwt:1000,type:'Bulk carrier'};
const scope={action:'mrv_reference',ships:[ship],years:[],periods:[],document_ids:[],reference_ack:true,mappings:{}};
function answer(id,flow,extra={}) {
 return {id,question:'test',task:'workflow',language:'ko',generation:'workflow',status:'needs_input',notice:'추가 조건을 알려 주세요.',
  warnings:[],statements:[],evidence:[],toolRuns:[],reportSuggested:false,
  workflow:{version:'HAEDAP-QUESTION-WORKFLOW-1.0',scope,missing:[],options:{ships:[],documents:[]},routing:{method:'rules',model_attempted:false},results:[],comparisons:[],...flow},...extra};
}
async function setup(page,handler) {
 const calls=[],errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/api/**',route=>{
  const req=route.request(),path=new URL(req.url()).pathname;
  const send=data=>route.fulfill({contentType:'application/json',body:JSON.stringify(data)});
  if(path==='/api/health')return send({csrfToken:'test',user:{id:'viewer',name:'업무 검증자',role:'viewer',version:1},authenticated:true,publicAccess:false,llmConfigured:false});
  if(path==='/api/operations')return send({ships:[ship,{...ship,id:'ship-b',name:'별빛호',imo:'9074729'}],records:[]});
  if(path==='/api/documents')return send({documents:[{id:'doc-a',title:'선박 안전 문서',version:'1',active:true,kind:'manual'}]});
  if(path==='/api/ask'){const body=req.postDataJSON();calls.push(body);return send(handler(body,calls.length));}
  return send({skills:[],history:[],reports:[],evidence:[]});
 });
 await page.goto('/chat');await expect(page.locator('#question')).toBeVisible();return {calls,errors};
}
async function ask(page,text) {
 await page.locator('#question').fill(text);await page.getByRole('button',{name:'질문 보내기',exact:true}).click();
 await expect(page.locator('[data-question-workflow]')).toBeVisible();
}

test('clarification submits only current parent and shows blocked years without invented ratings',async({page})=>{
 const first='11111111-1111-4111-8111-111111111111',second='22222222-2222-4222-8222-222222222222';
 const state=await setup(page,(body,n)=>n===1?answer(first,{missing:['years']}):answer(second,{
  scope:{...scope,years:[2024,2025]},previous_query_id:first,
  results:[{kind:'mrv_reference',label:'해답호 · 2024',status:'estimated',result:{reference_only:true,reference_dwt_intensity:'1.500000',units:{reference_dwt_intensity:'gCO2/(DWT t * nm)'},blockers:[]}},
    {kind:'mrv_reference',label:'해답호 · 2025',status:'blocked',result:{reference_only:true,reference_dwt_intensity:null,blockers:['NO_ELIGIBLE_ANNUAL_RECORD']}}]
 },{status:'partial',notice:'참고값과 계산 불가 사유를 확인하세요.'}));
 await ask(page,'우리 배의 MRV 참고 탄소집약도를 계산해줘');
 await page.getByLabel('업무 보고연도').fill('2024,2025');await page.getByRole('button',{name:'조건 적용 후 조회'}).click();
 await expect(page.locator('[data-workflow-result]')).toHaveCount(2);
 expect(state.calls[1].workflowInput).toEqual({years:[2024,2025]});
 expect(state.calls[1].context.previousQueryId).toBe(first);
 await expect(page.locator('[data-question-workflow]')).toContainText('계산 불가');
 await expect(page.locator('[data-question-workflow]')).toContainText('공식 CII·등급은 산출하지 않습니다.');
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
 await page.getByLabel('업무 선택 문서').selectOption('doc-a');
 await page.getByRole('button',{name:'조건 적용 후 조회'}).click();
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
