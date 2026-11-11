import {test, expect} from '@playwright/test';

// UI regression with a deterministic API. Database ownership/persistence is tested
// independently in backend/tests/test_conversations.py.
test('six UI requirements: language, transcript, source, history and deletion', async ({page}) => {
  const requests=[], turns=[], conversations=new Map();
  const errors=[]; page.on('pageerror', e=>errors.push(e.message));
  const doc={id:'d1',logical_id:'d1',title:'문서',reference:'한국어 원문',version:'1',active:true,kind:'onboard',hasPdf:false,meta:{scope:'all',issuer:'발행기관 원본'},sections:[{id:'c1',text:'변경하지 않을 문서 본문',heading:'원문 제목',page:1}]};
  await page.route('**/api/**', async route => {
    const req=route.request(),path=new URL(req.url()).pathname;let result={};
    if(path==='/api/health')result={authenticated:true,csrfToken:'test',llmConfigured:true,user:{id:'u1',name:'홍길동',role:'admin',must_change_password:false}};
    else if(path==='/api/documents')result={documents:[doc]};
    else if(path==='/api/operations')result={ships:[{id:'s1',name:'HAE 01',dwt:50000,sample:true}],records:[]};
    else if(path==='/api/reports')result={reports:[]};
    else if(path==='/api/ask'){
      const body=req.postDataJSON();requests.push(body);
      const id='q'+(turns.length+1), cid=body.conversationId||id;
      result={id,conversationId:cid,question:body.question,language:'ko',task:'documents',generation:'extractive',status:'evidence_found',notice:'원본 답변 안내',warnings:[],statements:[{text:'문서',chunkId:'c1'}],evidence:[{id:'c1',document_id:'d1',text:'질문 '+id+'의 원문 근거',title:'문서',version:'1',page:1}],toolRuns:[]};
      turns.push(result);conversations.set(cid,[...(conversations.get(cid)||[]),result]);
    }else if(path==='/api/conversations')result={history:[...conversations].map(([id,a])=>({id,question:a[0].question,count:a.length,at:'2026-11-09T00:00:00Z'}))};
    else if(path==='/api/conversations/delete'){const id=req.postDataJSON().id;conversations.delete(id);result={deleted:id};}
    else if(path.startsWith('/api/conversations/')){const id=path.split('/').at(-1);result={id,turns:conversations.get(id).map(a=>({id:a.id,question:a.question,answer:a}))};}
    else if(path==='/api/skills')result={skills:[]};
    await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(result)});
  });
  await page.goto('/chat');
  await expect(page.locator('.composer')).toBeVisible();
  await expect(page.locator('.local-note')).toHaveCount(0);
  await expect(page.locator('.query-controls select')).toHaveCount(1);
  await expect(page.getByLabel('답변 방식',{exact:true})).toHaveCount(0);
  await expect(page.getByLabel('검색 범위',{exact:true})).toHaveValue('all');
  await expect(page.locator('.query-context')).toHaveCount(0);
  await expect(page.locator('.composer select')).toHaveCount(1);
  await page.locator('#question').fill('입력 중 질문');
  await page.locator('.language-button').click();await page.getByRole('button',{name:'English',exact:true}).click();
  await expect(page.locator('[data-nav="docs"]')).toHaveText('Documents');
  await expect(page.getByLabel('Answer mode',{exact:true})).toHaveValue('llm');
  await expect(page.locator('#question')).toHaveValue('입력 중 질문');
  await expect(page.locator('.brand-title-en')).toHaveText('SEATHE ANSWER');
  await expect(page.locator('.brand-title-en br')).toHaveCount(1);
  await expect(page.locator('.brand small')).toHaveCount(0);
  await expect(page.locator('#question')).toHaveAttribute('placeholder',/Ask about/);
  for (const tab of ['docs', 'operations', 'reports', 'admin']) {
    await page.locator('[data-nav="'+tab+'"]').click();
    await expect(page.getByText('화면을 불러오지 못했어요.')).toHaveCount(0);
    await expect(page).toHaveURL(new RegExp({docs:'/documents',operations:'/operations',reports:'/reports',admin:'/admin'}[tab]+'$'));
    await expect(page.locator('main h1')).toBeVisible();
  }
  await page.locator('[data-nav="chat"]').click();
  await page.locator('#question').fill('첫 질문');await page.locator('.sendbtn').click();
  await expect(page.locator('.chat-turn')).toHaveCount(1);
  await page.locator('#question').fill('둘째 질문');await page.locator('.sendbtn').click();
  await expect(page.locator('.chat-turn')).toHaveCount(2);
  await expect.poll(()=>page.evaluate(()=>Math.abs(document.documentElement.scrollHeight-innerHeight-scrollY))).toBeLessThan(3);
  if (process.env.CAPSTONE_UI_SCREENSHOTS) await page.screenshot({path:process.env.CAPSTONE_UI_SCREENSHOTS+'/desktop.png',fullPage:true});
  expect(requests.map(r=>[r.question,r.language,r.mode,r.task])).toEqual([['첫 질문','auto','llm','auto'],['둘째 질문','auto','llm','auto']]);
  expect(requests[1].conversationId).toBe('q1');
  await expect(page.locator('.chat-turn').first().locator('.answer > p').nth(1)).toContainText('문서');
  const gap=await page.locator('.chat-turn').first().evaluate(e=>e.querySelector('.answer').getBoundingClientRect().top-e.querySelector('.question-bubble').getBoundingClientRect().bottom);
  expect(gap).toBe(20);
  const between=await page.locator(".chat-content").evaluate(e=>{const t=e.querySelectorAll(".chat-turn");return t[1].querySelector(".question-bubble").getBoundingClientRect().top-t[0].querySelector(".answer").getBoundingClientRect().bottom;});
  expect(between).toBeCloseTo(50.4, 1);
  await page.locator('.chat-turn').first().locator('.citation').click();
  await expect(page.locator('.quote')).toHaveText('질문 q1의 원문 근거');
  await page.locator('[data-action="closeModal"]').click();
  await page.locator('.brand').click();await expect(page.locator('.chat-turn')).toHaveCount(0);
  await page.locator('[data-action="history"]').click();
  await expect(page.locator('.history-row')).toHaveCount(1);
  await expect(page.locator('.history-delete')).toHaveCSS('color', 'rgb(130, 153, 165)');
  await page.locator('.history-delete').hover();
  await expect(page.locator('.history-delete')).toHaveCSS('color', 'rgb(180, 81, 81)');
  await expect(page.locator('.history-delete')).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)');
  await expect(page.locator('.history-delete')).toHaveCSS('border-top-width', '0px');
  await page.locator('.history-item').click();await expect(page.locator('#dialog')).not.toBeVisible();await expect(page.locator('.chat-turn')).toHaveCount(2);
  await page.locator('[data-nav="docs"]').click();await expect(page.locator('.docmain h3')).toHaveText('문서');
  await page.locator('[data-nav="chat"]').click();await expect(page.locator('.chat-turn')).toHaveCount(0);
  await page.locator('[data-action="history"]').click();await page.locator('.history-item').click();await expect(page.locator('.chat-turn')).toHaveCount(2);
  await page.reload();await expect(page.locator('[data-nav="docs"]')).toHaveText('Documents');
  await page.locator('[data-action="history"]').click();await page.locator('.history-item').click();await expect(page.locator('#dialog')).not.toBeVisible();
  await page.locator('#question').fill('셋째 질문');await page.locator('.sendbtn').click();await expect(page.locator('.chat-turn')).toHaveCount(3);
  expect(requests.at(-1).conversationId).toBe('q1');
  await page.locator('[data-action="history"]').click();await page.locator('.history-delete').click();
  await expect(page.locator('.history-row')).toHaveCount(0);
  await expect(page.locator('.chat-turn')).toHaveCount(0);
  await page.locator('[data-action="closeModal"]').click();
  await page.locator('.language-button').click();await page.getByRole('button',{name:'한국어',exact:true}).click();
  await expect(page.locator('[data-nav="docs"]')).toHaveText('문서');
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.setViewportSize({width:390,height:844});
  await expect(page.locator('.composer')).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  if (process.env.CAPSTONE_UI_SCREENSHOTS) await page.screenshot({path:process.env.CAPSTONE_UI_SCREENSHOTS+'/mobile.png',fullPage:true});
  expect(errors).toEqual([]);
});

test('browser title stays fixed across routes, languages and account screens', async ({page}) => {
  let loggedIn = true;
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname;
    let data = {};
    if (path === '/api/auth/logout') loggedIn = false;
    if (path === '/api/health') data = {authenticated:loggedIn, csrfToken:'test', user:{id:'u1',name:'관리자',role:loggedIn?'admin':'guest',must_change_password:false}};
    if (path === '/api/documents') data = {documents:[]};
    if (path === '/api/reports') data = {reports:[]};
    if (path === '/api/operations') data = {ships:[],records:[]};
    await route.fulfill({contentType:'application/json',body:JSON.stringify(data)});
  });
  for (const route of ['/chat','/documents','/operations','/reports','/admin']) {
    await page.goto(route);
    await expect(page.locator('.sidebar')).toBeVisible();
    await expect(page).toHaveTitle('해답 · SEA THE ANSWER');
  }
  await page.goto('/chat');
  await page.locator('.language-button').click();
  await page.getByRole('button',{name:'English',exact:true}).click();
  await expect(page.locator('html')).toHaveAttribute('lang','en');
  await expect(page).toHaveTitle('해답 · SEA THE ANSWER');
  await page.getByRole('button',{name:'Change password',exact:true}).click();
  await expect(page.locator('#passwordForm')).toBeVisible();
  await expect(page).toHaveTitle('해답 · SEA THE ANSWER');
  await page.goto('/chat');
  await page.getByRole('button',{name:'Sign out',exact:true}).click();
  await expect(page.locator('#authForm')).toBeVisible();
  await expect(page).toHaveTitle('해답 · SEA THE ANSWER');
});
