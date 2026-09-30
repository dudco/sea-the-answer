// DOM + actual HTTP/SQLite integration. This does not test browser layout.
// Optional dev dependency: npm install, then npm run test:ui.
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFile, mkdtemp, rm } from 'node:fs/promises';
import { resolve, dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { tmpdir } from 'node:os';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { createServer } from 'node:net';
import vm from 'node:vm';

const require=createRequire(import.meta.url);
const {parseHTML}=require(process.env.HAEDAP_DOM_LIBRARY || 'linkedom');
const root=fileURLToPath(new URL('../',import.meta.url));
const temp=await mkdtemp(join(tmpdir(),'haedap-ui-'));
const probe=createServer();probe.listen(0,'127.0.0.1');await once(probe,'listening');
const port=probe.address().port;await new Promise(r=>probe.close(r));
const base=`http://127.0.0.1:${port}`;
const server=spawn(process.execPath,['server.mjs'],{cwd:root,env:{...process.env,PORT:String(port),HAEDAP_DB_PATH:join(temp,'test.sqlite'),OPENAI_API_KEY:'',OPENAI_MODEL:''},stdio:['ignore','pipe','pipe']});
let logs='';server.stderr.on('data',d=>logs+=d);server.stdout.on('data',d=>logs+=d);
const pause=ms=>new Promise(r=>setTimeout(r,ms));
async function until(fn,label){for(let i=0;i<150;i++){if(await fn())return;await pause(20);}throw Error(label+' timed out. '+logs);}
const checks=[];
const check=name=>{checks.push(name);console.log('PASS '+name);};
let browser;
try {
  await until(async()=>{try{return(await fetch(base+'/api/health')).ok;}catch{return false;}},'server');
  const storage=new Map(),timerIds=new Set(); const cookies=new Map();
  async function boot(hash='#chat'){
    const {window,document}=parseHTML(await readFile(join(root,'index.html'),'utf8'));
    const location={hash},history={pushState:(_a,_b,h)=>{location.hash=h;}};
    window.scrollTo=()=>{};
    window.HTMLElement.prototype.scrollIntoView=()=>{};
    window.HTMLElement.prototype.reportValidity=function(){return true;};
    // A native browser dispatches close asynchronously; emulate that lifecycle.
    const dialog=document.querySelector('#dialog');
    dialog.showModal=function(){this.open=true;};
    dialog.close=function(){this.open=false;queueMicrotask(()=>this.dispatchEvent(new window.Event('close')));};
    const timers=(fn,ms)=>{const id=setTimeout(fn,ms);id.unref?.();timerIds.add(id);return id;};
    let holdNext=null;
    const context=vm.createContext({window,document,console,location,history,URL,Blob,AbortSignal,structuredClone,crypto:globalThis.crypto,btoa,
      requestAnimationFrame:fn=>fn(),setTimeout:timers,clearTimeout,
      localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},
      fetch:async(path,opts)=>{const result=await fetch(new URL(path,base),{...opts,headers:{...opts?.headers,Cookie:[...cookies].map(([k,v])=>k+'='+v).join('; ')}});for(const header of result.headers.getSetCookie()){const [k,v]=header.split(';')[0].split('=');if(v)cookies.set(k,v);else cookies.delete(k);}if(holdNext&&path===holdNext.path){const current=holdNext;holdNext=null;await current.promise;}return result;}});
    const modules=new Map(),modulePromises=new Map();
    async function load(path){path=resolve(path);if(modulePromises.has(path))return modulePromises.get(path);
      const promise=readFile(path,'utf8').then(source=>{const mod=new vm.SourceTextModule(source,{context,identifier:path});modules.set(path,mod);return mod;});
      modulePromises.set(path,promise);return promise;}
    const main=await load(join(root,'app.js'));await main.link((specifier,parent)=>load(resolve(dirname(parent.identifier),specifier)));await main.evaluate();
    const state=modules.get(join(root,'ui/state.js')).namespace.state;
    const click=selector=>{const el=document.querySelector(selector);assert.ok(el,'Missing '+selector);assert.ok(!el.disabled,'Disabled '+selector);el.dispatchEvent(new window.Event('click',{bubbles:true}));};
    const input=(selector,value)=>{const el=document.querySelector(selector);assert.ok(el,'Missing '+selector);el.value=value;el.dispatchEvent(new window.Event('input',{bubbles:true}));};
    const submit=selector=>document.querySelector(selector).dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true}));
    const change=(selector,value)=>{const el=document.querySelector(selector);Object.defineProperty(el,'value',{value,writable:true,configurable:true});el.dispatchEvent(new window.Event('change',{bubbles:true}));};
    function hold(path){let release;const promise=new Promise(r=>release=r);holdNext={path,promise};return release;}
    await until(()=>{if(!state.connecting&&!state.health)throw Error('Connection failed: '+state.connectionError);return !state.connecting&&state.health;},'initial connection');
    return {document,state,click,input,submit,change,hold,modules};
  }
  browser=await boot();let {state,document,click,input,submit,change}=browser;
  assert.equal(document.querySelector('#authForm'),null);assert.equal(state.health.setupRequired,false);assert.equal(state.user.role,'guest');assert.equal(state.ready,true);const guestId=state.user.id;assert.equal(document.querySelector('[data-nav=admin]'),null);assert.equal(document.querySelector('.brand small').textContent,'SEA THE ANSWER');check('First visit opens the public workspace without login and shows SEA THE ANSWER');
  input('#question','연료 황 함유량 기준');submit('#askForm');await until(()=>state.answer&&!state.busy,'guest search');assert.match(state.answer.statements[0].text,/0.50%/);check('Anonymous visitor can ask and receive document evidence');
  click('[data-action="openLogin"]');assert.ok(document.querySelector('#authForm'));click('[data-action="cancelLogin"]');assert.ok(document.querySelector('#question'));assert.ok(state.answer);check('Administrator login can be cancelled without losing guest work');
  click('[data-action="openLogin"]');input('#auth-username','admin');input('#auth-password','wrong');submit('#authForm');await until(()=>state.authError,'wrong password');assert.ok(document.querySelector('#authError').textContent);assert.equal(state.user.role,'guest');
  input('#auth-username','admin');input('#auth-password','1234');submit('#authForm');
  await until(()=>state.ready&&state.user.role==='admin'&&!state.connecting,'admin login');assert.equal(state.docs.length,4);assert.equal(state.answer,null);check('Wrong password is rejected; admin / 1234 opens administrator controls and clears guest response');
  input('#question','연료 황 함유량 기준');submit('#askForm');await until(()=>state.answer&&!state.busy,'search');assert.match(state.answer.statements[0].text,/0.50%/);
  click('.citation');assert.ok(document.querySelector('#dialog').textContent.includes('0.50%'));click('#dialog [data-action="document"]');assert.equal(state.page,'document');assert.ok(document.querySelector('.paper').textContent.includes('0.50%'));click('[data-action="backDocument"]');check('Search → evidence → source text → back to original answer');
  click('[data-action="history"]');await until(()=>document.querySelector('.history-item'),'history');click('#dialog [data-action="historyAnswer"]');assert.ok(state.answer.statements.length);check('Question history reopens stored answer and evidence');
  click('[data-nav="docs"]');click('[data-action="newDocument"]');
  input('#f-title','UI 페이지 검증');input('#f-reference','시험 제1조');input('#f-text','--- PAGE 4 ---\n오로라라는 실험용 문서는 입력 기준 50톤 이하를 설명합니다.');input('#f-issuer','검증기관');input('#f-version','v1');
  document.querySelector('[name=checked]').checked=true;submit('#documentForm');await until(()=>state.docs.some(d=>d.title==='UI 페이지 검증'),'document create');const created=state.docs.find(d=>d.title==='UI 페이지 검증');assert.equal(created.sections[0].page,4);check('Document registration persists metadata, page number and indexed text');
  click(`[data-action="document"][data-id="${created.id}"]`);assert.ok(document.querySelector('[data-action=editDocument]'));assert.ok(document.querySelector('[data-action=deleteDocument]'));click('[data-action=editDocument]');assert.equal(document.querySelector('#documentForm button[type=submit]').textContent,'저장');input('#f-version','v2');input('#f-issuer','변경기관');document.querySelector('[name=checked]').checked=true;submit('#documentForm');await until(()=>state.docs.some(d=>d.logical_id===created.logical_id&&d.version==='v2'&&d.active),'document revision');const revised=state.docs.find(d=>d.logical_id===created.logical_id&&d.active);assert.equal(revised.meta.issuer,'변경기관');click('[data-nav=docs]');click(`[data-action="document"][data-id="${revised.id}"]`);click('[data-action=deleteDocument]');assert.equal(document.querySelector('[data-action=confirm]').textContent,'삭제');click('[data-action=closeModal]');assert.ok(state.docs.some(d=>d.id===revised.id));click('[data-action=deleteDocument]');click('[data-action=confirm]');await until(()=>!state.docs.some(d=>d.logical_id===created.logical_id),'document delete');const {changes:directChanges}=await browser.modules.get(join(root,'ui/api.js')).namespace.api.request('/api/changes');assert.ok(directChanges.filter(c=>c.kind.startsWith('document.')).every(c=>c.status==='approved'));check('Administrator document revision and confirmed deletion apply immediately without approval waiting');
  click('[data-nav="operations"]');click('[data-action="newShip"]');input('#f-name','UI 검증선');input('#f-type','벌크선');input('#f-dwt','1000');submit('#shipForm');await until(()=>state.ships.length===1,'ship create');
  click('[data-action="newRecord"]');input('#f-date','2026-09-28');input('#f-fuel','10');input('#f-factor','3');input('#f-distance','100');input('#f-speed','10');input('#f-fuelType','시험용');input('#f-position','시험 항만');input('#f-voyage','TEST-1');input('#f-draft','7');input('#f-weather','맑음');input('#f-engineHours','24');submit('#recordForm');await until(()=>state.operationRecords.length===1,'record create');assert.equal(state.operationRecords[0].fuel,10);assert.ok(document.querySelector('main').textContent.includes('30.0'));for(const action of ['newShip','importOperations','newRecord','editShip','editRecord','deleteRecord'])assert.ok(document.querySelector('[data-action='+action+']'),action);check('Administrator vessel/record controls are visible and forms write actual DB records');
  click('[data-tab="analysis"]');change('[data-field=metric]','emission');assert.ok(document.querySelector('svg.chart').getAttribute('aria-label').includes('CO₂'));click('[data-tab="calculation"]');click('[data-action="useSampleInputs"]');submit('#calcForm');await until(()=>state.calc,'calculation');assert.equal(state.calc.emission,30);input('#distance','0');assert.equal(state.calc,null);submit('#calcForm');await until(()=>state.calcError,'invalid calculation');check('Selectable emissions chart and invalid calculation do not display stale values');
  click('[data-nav="chat"]');input('#question','선택 선박의 운항 추이와 규정을 확인해줘');submit('#askForm');await until(()=>state.answer?.operations,'integrated');assert.equal(state.answer.operations.emission,30);assert.ok(document.querySelector('.integrated-result'));assert.ok(document.querySelector('.integrated-result').textContent.includes('판단 불가'));check('Integrated answer renders DB metrics, trend, provenance and cannot-determine state');
  click('[data-action="answerReport"]');input('#report-title','UI 통합 보고서');click('[data-action="saveReport"]');await until(()=>state.draft.id&&!state.saving,'report save');const reportId=state.draft.id;assert.equal(state.dirty,false);
  const apiModule=browser.modules.get(join(root,'ui/api.js')).namespace;await apiModule.api.saveReport({...state.draft,title:'다른 창 변경'});input('#report-text',state.draft.text+'\n내 변경');click('[data-action="saveReport"]');await until(()=>state.conflict&&!state.saving,'conflict');assert.ok(state.draft.text.includes('내 변경'));click('[data-action="viewConflict"]');assert.ok(document.querySelector('#dialog').textContent.includes('다른 창 변경'));click('[data-action="closeModal"]');click('[data-action="replaceConflict"]');click('[data-action="confirm"]');await until(()=>state.draft.version===3&&!state.saving,'replace');assert.equal(state.dirty,false);check('Report conflict preserves edits and requires reviewed version before replacement');
  const release=browser.hold('/api/reports');input('#report-title','저장 요청 시점');click('[data-action="saveReport"]');await until(()=>state.saving,'saving');input('#report-text',state.draft.text+'\n저장 중 편집');release();await until(()=>!state.saving,'save race');assert.equal(state.dirty,true);assert.ok(state.draft.text.includes('저장 중 편집'));click('[data-action="saveReport"]');await until(()=>!state.saving&&!state.dirty,'second save');check('Concurrent editing while saving preserves unsaved changes');
  click('[data-action="submitReport"]');click('[data-action="confirm"]');await until(()=>state.draft.status==='review','submission');assert.ok(document.querySelector('#report-text').hasAttribute('readonly'));click('[data-nav="admin"]');click('[data-action="adminTab"][data-id="approvals"]');await until(()=>!state.adminLoading&&state.changes.some(c=>c.kind==='report.approve'),'approval list');const pending=state.changes.find(c=>c.kind==='report.approve');click(`[data-action="reviewChange"][data-id="${pending.id}"]`);await until(()=>document.querySelector('[data-action=approveChange]'),'review dialog');click('[data-action=approveChange]');click('[data-action=confirm]');await until(()=>state.reports.find(r=>r.id===reportId)?.status==='approved','approval');check('Report submission locks edits and administrator approval persists status');
  click('[data-nav="reports"]');click('[data-action="templateNoon"]');await until(()=>state.draft.body?.template==='noon','Noon');const noonId=state.draft.id;assert.match(state.draft.text,/흘수: 7 m/);click('[data-nav="reports"]');click('[data-action="templateMrv"]');await until(()=>state.draft.body?.template==='mrv','MRV');assert.notEqual(state.draft.id,noonId);assert.ok(state.reports.some(r=>r.id===noonId));check('Noon and MRV templates save as separate reopenable reports with data fields');
  click('[data-nav="admin"]');click('[data-action="adminTab"][data-id="users"]');await until(()=>!state.adminLoading,'users');click('[data-action="newUser"]');input('#f-name','추가 관리자');input('#f-username','another-admin');input('#f-password','another-password');submit('#userForm');await until(()=>state.users.some(u=>u.username==='another-admin'),'user create');check('User management form creates an additional administrator');
  click('[data-action="adminTab"][data-id="logs"]');await until(()=>!state.adminLoading&&state.logs.length,'logs');assert.ok(document.querySelector('table'));click('[data-action="adminTab"][data-id="backup"]');await until(()=>!state.adminLoading,'backups');click('[data-action="createBackup"]');await until(()=>state.backups.length,'backup');assert.equal(state.backups[0].counts.operations,1);check('Audit log and full backup list show persisted data and timestamps');
  click('[data-action="logout"]');await until(()=>state.ready&&state.user?.role==='guest'&&!state.connecting,'logout');assert.equal(state.user.id,guestId);assert.equal(state.page,'chat');assert.equal(document.querySelector('[data-nav=admin]'),null);assert.ok(document.querySelector('[data-action=openLogin]'));assert.equal(state.draft.text,'');assert.equal(state.users.length,0);assert.equal(state.logs.length,0);click('[data-nav=docs]');assert.equal(document.querySelector('[data-action=newDocument]'),null);click('[data-action=document]');assert.ok(document.querySelector('.paper'));assert.equal(document.querySelector('[data-action=editDocument]'),null);assert.equal(document.querySelector('[data-action=deleteDocument]'),null);click('[data-nav=operations]');click('[data-tab=overview]');for(const action of ['newShip','importOperations','newRecord','editShip','editRecord','deleteRecord'])assert.equal(document.querySelector('[data-action='+action+']'),null,action);assert.ok(document.querySelector('[data-action=recordDetail]'));assert.ok(![...document.querySelectorAll('th')].some(t=>t.textContent==='관리'));check('Logout preserves guest reading but hides every document/vessel/record mutation and the management column');
  click('[data-nav=reports]');click('[data-action=newReport]');await until(()=>document.querySelector('#report-title'),'new guest draft');input('#report-title','일반 사용자 초안');input('#report-text','로그인 없이 작성한 보고서');click('[data-action=saveReport]');await until(()=>state.draft.id&&!state.saving,'guest draft');const guestReport=state.draft.id;
  click('[data-action=openLogin]');input('#auth-username','admin');input('#auth-password','1234');submit('#authForm');await until(()=>state.ready&&state.user.role==='admin'&&!state.connecting,'second login');assert.notEqual(state.draft.id,guestReport);click('[data-action=logout]');await until(()=>state.ready&&state.user.role==='guest'&&!state.connecting,'second logout');assert.equal(state.draft.id,guestReport);assert.equal(state.draft.text,'로그인 없이 작성한 보고서');check('Guest draft survives administrator login/logout without mixing ownership');
  for(const id of timerIds)clearTimeout(id);
  console.log(JSON.stringify({passed:checks.length,scope:'DOM + actual HTTP/SQLite; no real browser layout or external model',checks},null,2));
} finally {if(server.exitCode===null&&server.signalCode===null){const done=once(server,'exit');server.kill();await done;}await rm(temp,{recursive:true,force:true});}
