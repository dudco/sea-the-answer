import test from 'node:test';
import assert from 'node:assert/strict';
import {createApiClient} from '../src/lib/api.js';
import {generationFailureMessage} from '../src/lib/generation-failure.js';

test('server model budget can exceed 32 seconds without cancelling an otherwise valid AI reply',async(t)=>{
  const budgets=[];
  t.mock.method(AbortSignal,'timeout',ms=>{budgets.push(ms);return new AbortController().signal;});
  t.mock.method(globalThis,'fetch',async path=>({ok:true,json:async()=>path==='/api/health'
    ? {csrfToken:'fixture',user:{id:'fixture'},askTimeoutMs:75000}
    : {status:'completed'}}));
  const client=createApiClient();await client.health();
  await client.request('/api/ask',{question:'문서 설명'});
  assert.equal(budgets.at(-1),75000);
  await client.documents();assert.equal(budgets.at(-1),32000);
});

test('invalid server timeout cannot create unbounded browser requests',async(t)=>{
  const budgets=[];
  t.mock.method(AbortSignal,'timeout',ms=>{budgets.push(ms);return new AbortController().signal;});
  t.mock.method(globalThis,'fetch',async()=>({ok:true,json:async()=>({askTimeoutMs:Infinity})}));
  const client=createApiClient();await client.health();await client.request('/api/ask',{});
  assert.equal(budgets.at(-1),95000);
});

test('different model failures are distinguishable and unknown text is not rendered',()=>{
  assert.match(generationFailureMessage('MODEL_TIMEOUT'),/시간/);
  assert.match(generationFailureMessage('MODEL_CITATION_MISMATCH'),/인용/);
  assert.notEqual(generationFailureMessage('MODEL_TIMEOUT'),generationFailureMessage('MODEL_INVALID_JSON'));
  assert.equal(generationFailureMessage('https://secret.invalid/key'),'');
});
