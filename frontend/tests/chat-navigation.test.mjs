import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {createModel} from '../src/lib/model.js';
const require = createRequire(import.meta.url);
const React = require('react');
const babel = require('next/dist/compiled/babel/bundle');
// Exercise the production controller with isolated HTTP/render boundaries.
// Use Next's installed JSX compiler without introducing a second compiler dependency.
function load(file, imports, browser) {
  const source = readFileSync(new URL(file, import.meta.url), 'utf8');
  const {code} = babel.core().transformSync(source, {babelrc:false, configFile:false,
    presets:[[babel.presetReact().default, {runtime:'classic'}]], plugins:[babel.pluginTransformModulesCommonjs().default]});
  const module = {exports:{}};
  new Function('require','module','exports','window','document','requestAnimationFrame','cancelAnimationFrame', code)(
    id=>imports[id] || {}, module, module.exports, browser.window, browser.document, browser.raf, browser.cancel);
  return module.exports;
}
function setup({llmConfigured=false}={}) {
  const pending=[], requests=[], routes=[], scrolls=[];
  const browser={window:{scrollTo:(...args)=>scrolls.push(args),location:{pathname:'/chat'}},document:{querySelector:()=>null}};
  const api={health:async()=>({authenticated:true,llmConfigured,user:{id:'u1',role:'admin'}}),
    documents:async()=>({documents:[]}),operations:async()=>({ships:[],records:[]}),reports:async()=>({reports:[]}),
    ask:body=>{requests.push(body);return new Promise((resolve,reject)=>pending.push({resolve,reject}));}};
  const {createWorkspace}=load('../src/workspace/controller.jsx', {
    react:React, '../lib/model':{createModel}, '../lib/api':{createApiClient:()=>api},
    '../views':{createViews:()=>({})},
  },browser);
  const workspace=createWorkspace();
  workspace.attach({push:(...args)=>routes.push(args)});
  workspace.state.ready=true;workspace.state.user={id:'u1',role:'admin'};
  const click=dataset=>workspace.events.onClick({target:{closest:()=>({dataset})}});
  const reconnect=()=>new Promise(resolve=>{
    const stop=workspace.subscribe(()=>{if(!workspace.state.connecting){stop();resolve();}});
    click({action:'reconnect'});
  });
  return {workspace, pending, requests, routes, scrolls, browser, click, reconnect};
}
test('sending and completing a follow-up preserves the conversation without scrolling to the top',async()=>{
  const t=setup(),w=t.workspace;
  const first=w.ask('first');
  assert.equal(t.scrolls.length,0);
  assert.deepEqual(t.routes.at(-1),['/chat',{scroll:false}]);
  assert.equal(w.state.chatScrollRequest.phase,'pending');
  t.pending.shift().resolve({id:'q1'});await first;
  const second=w.ask('second');
  assert.equal(w.state.turns.length,1);
  assert.equal(t.requests[1].conversationId,'q1');
  t.pending.shift().resolve({id:'q2',conversationId:'q1'});await second;
  assert.deepEqual(w.state.turns.map(t=>t.question),['first','second']);
  assert.equal(t.scrolls.length,0);
  assert.equal(w.state.chatScrollRequest.phase,'complete');
  w.dispose();
});

test('questions never send an answer mode: the server always routes with the model (ADR 0024)',async()=>{
  for(const llmConfigured of [true,false]){
    const t=setup({llmConfigured}),w=t.workspace;
    await w.start();assert.equal('mode' in w.state,false);
    const asked=w.ask('질문');assert.equal('mode' in t.requests[0],false);
    t.pending.shift().resolve({id:'answer'});await asked;w.dispose();
  }
});
test('chat tab starts a new conversation and discards a late response and its scroll request',async()=>{
  const t=setup(),w=t.workspace;
  w.state.turns=[{id:'old'}];w.state.conversationId='old';
  w.state.history=[{id:'old'}];w.state.question='draft';
  const request=w.ask('pending');t.click({nav:'chat'});
  assert.equal(w.state.question,'');assert.equal(w.state.conversationId,'');
  assert.deepEqual(w.state.turns,[]);assert.equal(w.state.chatScrollRequest,null);
  assert.deepEqual(w.state.history,[{id:'old'}]);assert.deepEqual(t.scrolls.at(-1),[0,0]);
  t.pending.shift().resolve({id:'late',conversationId:'old'});await request;
  assert.deepEqual(w.state.turns,[]);assert.equal(w.state.chatScrollRequest,null);
  w.dispose();
});
test('failed question keeps its text and requests the bottom error view',async()=>{
  const t=setup(),w=t.workspace;const request=w.ask('retry me');
  t.pending.shift().reject(new Error('temporary failure'));await request;
  assert.equal(w.state.pendingQuestion,'retry me');assert.equal(w.state.askError,'temporary failure');
  assert.equal(w.state.chatScrollRequest.phase,'complete');assert.equal(t.scrolls.length,0);
  w.dispose();
});

test('automatic first ship and default dates are not silently sent as question scope',async()=>{
  const t=setup(),w=t.workspace;
  w.state.ships=[{id:'first'},{id:'named'}];w.state.ship='first';
  const first=w.ask('연료 얼마나 썼어?');
  assert.equal(t.requests[0].context.ship,'');
  assert.equal(t.requests[0].context.from,undefined);
  assert.equal(t.requests[0].context.to,undefined);
  t.pending.shift().resolve({id:'q1',workflow:{scope:{action:'operations_summary',ships:[{id:'named'}]}}});await first;
  assert.equal(w.state.ship,'named');
  const second=w.ask('지난달');
  assert.equal(t.requests[1].context.ship,'named');
  assert.equal(t.requests[1].context.previousQueryId,'q1');
  assert.equal(t.requests[1].context.from,undefined);
  t.pending.shift().resolve({id:'q2'});await second;w.dispose();
});

test('operation page controls do not become hidden question conditions',async()=>{
  const t=setup(),w=t.workspace;w.state.ship='chosen';
  const request=w.ask('운항 실적을 요약해줘');
  assert.deepEqual(t.requests[0].context,{ship:''});
  t.pending.shift().resolve({id:'q'});await request;w.dispose();
});

test('only the current conversational scope supplies a ship and period to follow-ups',async()=>{
  const t=setup(),w=t.workspace;w.state.ship='unrelated';
  w.state.answer={id:'parent',workflow:{scope:{action:'operations_summary',ships:[{id:'named'}],periods:[{start:'2025-01-01',end:'2025-01-31'}]}}};
  const request=w.ask('2월은?');
  assert.deepEqual(t.requests[0].context,{ship:'named',from:'2025-01-01',to:'2025-01-31',previousQueryId:'parent'});
  t.pending.shift().resolve({id:'q'});await request;w.dispose();
});

test('pending port ship clarification is linked even without a selected ship',async()=>{
  const t=setup(),w=t.workspace;
  w.state.answer={id:'port-parent',navigation:{status:'needs_ship',ship:null}};
  const request=w.ask('해답호');
  assert.equal(t.requests[0].context.previousQueryId,'port-parent');
  assert.equal(t.requests[0].context.ship,'');
  t.pending.shift().resolve({id:'q'});await request;w.dispose();
});
test('chat DOM commit scrolls to the bottom; cancelled requests and other pages cannot steal scroll',()=>{
  const t=setup(),w=t.workspace;w.views.chatPage=()=>null;w.views.reportPage=()=>null;
  const frames=new Map();let nextId=0,cleanup;
  const browser={...t.browser,document:{documentElement:{scrollHeight:4200}},
    raf:fn=>{frames.set(++nextId,fn);return nextId;},cancel:id=>frames.delete(id)};
  const react={...React,useContext:()=>({workspace:w}),useLayoutEffect:fn=>{cleanup=fn();}};
  const {WorkspacePage}=load('../src/workspace/provider.jsx', {react},browser);
  w.state.askSequence=3;w.state.chatScrollRequest={sequence:3,phase:'pending'};
  WorkspacePage({name:'chatPage'});frames.get(nextId)();
  assert.deepEqual(t.scrolls.at(-1),[{top:4200,behavior:'instant'}]);cleanup();
  assert.equal(frames.size,0);
  WorkspacePage({name:'chatPage'});w.state.askSequence++;frames.get(nextId)();cleanup();
  assert.equal(t.scrolls.length,1);
  w.state.chatScrollRequest={sequence:w.state.askSequence,phase:'complete'};
  WorkspacePage({name:'chatPage'});w.state.page='reports';frames.get(nextId)();cleanup();
  assert.equal(t.scrolls.length,1);
  WorkspacePage({name:'reportPage'});assert.equal(frames.size,0);
  w.dispose();
});
