// Optional real-browser integration check. Uses Chrome's DevTools protocol, no npm dependencies.
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { readFile, mkdtemp, mkdir, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { createServer } from 'node:net';
import { once } from 'node:events';
import { fileURLToPath } from 'node:url';
import { openDatabase, importDocuments } from '../backend/db.mjs';
import { lanInterfaces } from '../backend/network.mjs';

// Updated for connected IA v2 UI. Run locally with CHROME_PATH if Chrome is not in the default Windows path.
const workspace = fileURLToPath(new URL('../', import.meta.url));
const lan = process.argv.includes('--lan');
const lanAddress = lan ? lanInterfaces()[0]?.address : null;
if (lan && !lanAddress) throw new Error('LAN browser check needs a connected IPv4 interface.');
await mkdir(join(workspace, '.verification'), { recursive: true });
const run = await mkdtemp(join(workspace, '.verification', 'backend-browser-'));
const probe = createServer(); probe.listen(0, '127.0.0.1'); await once(probe, 'listening');
const port = probe.address().port; await new Promise(r => probe.close(r));
const server = spawn(process.execPath, ['server.mjs', ...(lan ? ['--lan'] : [])], { cwd: workspace, windowsHide: true, stdio: 'ignore',
  env: { ...process.env, PORT: String(port), HAEDAP_DB_PATH: join(run, 'test.sqlite'), OPENAI_API_KEY: '', OPENAI_MODEL: '' } });
let browser, socket;
const checks = [], exceptions = [];
const pause = ms => new Promise(r => setTimeout(r, ms));
async function until(fn, message) { for (let i = 0; i < 100; i++) { try { if (await fn()) return; } catch {} await pause(100); } throw new Error(message); }
try {
  await until(async () => (await fetch(`http://127.0.0.1:${port}/api/health`)).ok, 'Server startup');
  browser = spawn(process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe',
    ['--headless=new', '--remote-debugging-port=0', `--user-data-dir=${join(run, 'chrome')}`, '--no-first-run', '--no-default-browser-check', '--disable-gpu', 'about:blank'],
    { windowsHide: true, stdio: 'ignore' });
  browser.on('error', error => { console.error('Chrome launch failed. Set CHROME_PATH:', error.message); });
  let debugPort;
  await until(async () => { debugPort = (await readFile(join(run, 'chrome', 'DevToolsActivePort'), 'utf8')).split('\n')[0]; return debugPort; }, 'Chrome startup');
  const pages = await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json();
  socket = new WebSocket(pages.find(p => p.type === 'page').webSocketDebuggerUrl);
  await new Promise((r, reject) => { socket.onopen = r; socket.onerror = reject; });
  let sequence = 0; const pending = new Map();
  function command(method, params = {}) {
    const id = ++sequence;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { pending.delete(id); reject(new Error(`CDP timeout: ${method}`)); }, 15000);
      pending.set(id, { resolve, reject, timer }); socket.send(JSON.stringify({ id, method, params }));
    });
  }
  socket.onmessage = e => {
    const data = JSON.parse(e.data);
    if (data.method === 'Runtime.exceptionThrown') exceptions.push(data.params.exceptionDetails.text + ': ' + (data.params.exceptionDetails.exception?.description || ''));
    if (data.method === 'Page.javascriptDialogOpening') command('Page.handleJavaScriptDialog', { accept: true }).catch(() => {});
    const item = pending.get(data.id);
    if (item) { clearTimeout(item.timer); pending.delete(data.id); data.error ? item.reject(new Error(data.error.message)) : item.resolve(data.result); }
  };
  async function evaluate(expression) {
    const data = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    if (data.exceptionDetails) throw new Error(data.exceptionDetails.exception?.description || data.exceptionDetails.text);
    return data.result.value;
  }
  const waitJs = (expression, name) => until(() => evaluate(expression), name);
  await command('Runtime.enable'); await command('Page.enable');
  await command('Page.navigate', { url: `http://127.0.0.1:${port}/` });
  const stateJs = `(await import('/ui/state.js')).state`;
  await waitJs(`${stateJs}.health && !${stateJs}.connecting`, 'Authentication screen');
  await evaluate(`document.querySelector('[data-action=openLogin]').click();for(const [id,value] of Object.entries({'auth-username':'admin','auth-password':'1234'})){const el=document.getElementById(id);el.value=value;}document.getElementById('authForm').requestSubmit()`);
  await waitJs(`${stateJs}.ready && ${stateJs}.user.role==='admin'`, 'Backend hydration'); checks.push('Backend connected');
  if(lanAddress){await command('Page.navigate',{url:`http://${lanAddress}:${port}/`});await waitJs(`${stateJs}.health && !${stateJs}.connecting`,'LAN login');await evaluate(`document.querySelector('[data-action=openLogin]').click();document.getElementById('auth-username').value='admin';document.getElementById('auth-password').value='1234';document.getElementById('authForm').requestSubmit()`);await waitJs(`${stateJs}.ready && ${stateJs}.user.role==='admin'`,'LAN authenticated');}
  await evaluate(`document.getElementById('question').value='연료 황 함유량 기준'; document.getElementById('question').dispatchEvent(new Event('input',{bubbles:true})); document.getElementById('askForm').requestSubmit()`);
  await waitJs(`${stateJs}.answer && !${stateJs}.busy`, 'Search');
  assert.ok(await evaluate(`document.querySelector('.answer').textContent.includes('0.50%')`)); checks.push('Actual search');
  await evaluate(`document.querySelector('.citation').click()`);
  assert.ok(await evaluate(`document.getElementById('dialog').open`)); checks.push('Evidence dialog');
  await evaluate(`document.querySelector('#dialog [data-action="document"]').click()`);
  assert.ok(await evaluate(`document.querySelector('.paper').textContent.includes('0.50%')`)); checks.push('Stored source document');
  await evaluate(`document.querySelector('[data-action="backDocument"]').click(); document.querySelector('[data-action="answerReport"]').click(); document.getElementById('report-title').value='브라우저 검증 초안'; document.getElementById('report-title').dispatchEvent(new Event('input',{bubbles:true})); document.querySelector('[data-action="saveReport"]').click()`);
  await waitJs(`${stateJs}.draft.version===1 && !${stateJs}.saving`, 'Save'); checks.push('SQLite save');
  await command('Page.reload'); await waitJs(`${stateJs}.ready && ${stateJs}.user.role==='admin'`, 'Reload');
  assert.ok(await evaluate(`document.getElementById('report-text').value.includes('0.50%')`)); checks.push('Draft recovery');
  await evaluate(`document.querySelector('[data-nav="operations"]').click(); document.querySelector('[data-tab="calculation"]').click(); for(const [id,value] of Object.entries({fuel:'100',factor:'3',dwt:'1000',distance:'100'})){const el=document.getElementById(id);el.value=value;el.dispatchEvent(new Event('input',{bubbles:true}));}document.getElementById('calcForm').requestSubmit()`);
  await waitJs(`${stateJs}.calc?.emission===300`, 'Calculation'); checks.push('Actual tool calculation');
  await evaluate(`document.querySelector('[data-nav="chat"]').click(); document.getElementById('question').value='초콜릿 케이크 레시피';document.getElementById('question').dispatchEvent(new Event('input',{bubbles:true}));document.getElementById('askForm').requestSubmit()`);
  await waitJs(`${stateJs}.answer?.status==='insufficient_evidence'`, 'No evidence'); checks.push('No evidence response');
  for(const page of ['docs','operations','reports','admin']){await evaluate(`document.querySelector('[data-nav="${page}"]').click()`);assert.ok(await evaluate(`document.getElementById('main').textContent.length>30`));}checks.push('All primary screens');
  await command('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
  await command('Page.navigate', {url:`http://${lanAddress || '127.0.0.1'}:${port}/#editor`});await waitJs(`${stateJs}.ready && ${stateJs}.user.role==='admin'`, 'Mobile');
  assert.ok(await evaluate('document.documentElement.scrollWidth <= innerWidth + 1')); checks.push('Mobile report width');
  const screenshot = await command('Page.captureScreenshot', { format: 'png' });
  await writeFile(join(run, 'report-mobile.png'), Buffer.from(screenshot.data, 'base64'));
  assert.deepEqual(exceptions, []); checks.push('No JavaScript exceptions');
  await writeFile(join(run, 'results.json'), JSON.stringify({ checkedAt: new Date().toISOString(), mode: lan ? 'lan' : 'local', address: lanAddress || '127.0.0.1', checks, exceptions }, null, 2));
  console.log(JSON.stringify({ mode: lan ? 'lan' : 'local', address: lanAddress || '127.0.0.1', checks, artifactDirectory: run }, null, 2));
} finally {
  socket?.close();
  for (const child of [browser, server].filter(Boolean)) {
    if (child.exitCode === null && child.signalCode === null) { const done = once(child, 'exit'); child.kill(); await done; }
  }
}
