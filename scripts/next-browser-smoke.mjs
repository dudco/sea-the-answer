// Real Next.js + real SQLite, isolated database. Never uses the user's data directory.
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdtemp, mkdir, writeFile, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { resolve, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { once } from 'node:events';
import { createServer } from 'node:net';
import { chromium } from 'playwright';
const root = fileURLToPath(new URL('../', import.meta.url));
const run = await mkdtemp(join(tmpdir(), 'haedap-next-browser-'));
const probe = createServer();
probe.listen(0, '127.0.0.1');
await once(probe, 'listening');
const port = probe.address().port;
await new Promise((r) => probe.close(r));
const server = spawn(
  process.execPath,
  [
    'scripts/run.mjs',
    ...(process.env.HAEDAP_TEST_DEV ? ['--dev'] : []),
    '--port',
    String(port),
  ],
  {
    cwd: root,
    env: {
      ...process.env,
      HAEDAP_DB_PATH: join(run, 'test.sqlite'),
      OPENAI_API_KEY: '',
      OPENAI_MODEL: '',
      NEXT_TELEMETRY_DISABLED: '1',
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  },
);
let serverLog = '',
  browser,
  lastPage;
server.stdout.on('data', (d) => (serverLog += d));
server.stderr.on('data', (d) => (serverLog += d));
const checks = [],
  errors = [],
  warnings = [];
const base = `http://127.0.0.1:${port}`;
const check = (name) => {
  checks.push(name);
  console.log('PASS:', name);
};
try {
  let ready = false;
  for (let i = 0; i < 400; i++) {
    try {
      ready = (await fetch(base + '/api/health')).ok;
      if (ready) break;
    } catch {}
    if (server.exitCode !== null) break;
    await new Promise((r) => setTimeout(r, 150));
  }
  assert.ok(ready, serverLog);
  let launch = {
    headless: true,
    ...(process.env.CHROME_PATH
      ? { executablePath: process.env.CHROME_PATH }
      : {}),
  };
  if (process.env.HAEDAP_CHROMIUM_MODULE) {
    const { default: binary } = await import(
      pathToFileURL(process.env.HAEDAP_CHROMIUM_MODULE)
    );
    launch = {
      headless: true,
      executablePath:
        process.env.CHROME_PATH || (await binary.executablePath()),
      args: binary.args,
    };
  }
  browser = await chromium.launch(launch);
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    locale: 'ko-KR',
  });
  const page = await context.newPage();
  lastPage = page;
  page.setDefaultTimeout(15000);
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('console', (m) => {
    if (['error', 'warning'].includes(m.type())) warnings.push(m.text());
  });
  const go = async (name) => {
    await page.locator(`[data-nav=${name}]`).click();
    await page.waitForTimeout(100);
  };
  const action = (a) => page.locator(`[data-action=${a}]`);
  const api = async (path, body) =>
    page.evaluate(
      async ({ path, body }) => {
        const health = await (await fetch('/api/health')).json();
        const r = await fetch(path, {
          method: body ? 'POST' : 'GET',
          headers: body
            ? {
                'Content-Type': 'application/json',
                'X-Haedap-Token': health.csrfToken,
                'X-Haedap-Identity': health.user.id,
              }
            : {},
          body: body ? JSON.stringify(body) : undefined,
        });
        return { status: r.status, data: await r.json() };
      },
      { path, body },
    );
  const login = async (password = '1234') => {
    await action('openLogin').click();
    await page.locator('#auth-username').fill('admin');
    await page.locator('#auth-password').fill(password);
    await page.locator('#authForm').evaluate((f) => f.requestSubmit());
  };
  const confirm = () => action('confirm').click();
  const close = () => action('closeModal').click();
  await page.goto(base);
  await action('openLogin').waitFor();
  await page.waitForURL('**/chat');
  assert.equal(new URL(page.url()).pathname, '/chat');
  assert.equal(
    await page.locator('.brand small').innerText(),
    'SEA THE ANSWER',
  );
  check('Next.js root redirect, public workspace and brand');
  await page.locator('#question').fill('연료 황 함유량 기준을 알려줘');
  await page.locator('#askForm').evaluate((f) => f.requestSubmit());
  await page.locator('.answer').waitFor();
  assert.match(await page.locator('.answer').innerText(), /0.50%/);
  await action('source').first().click();
  assert.ok(await page.locator('dialog').evaluate((d) => d.open));
  await close();
  check('React input, real search, source dialog');
  await go('docs');
  assert.equal(await action('newDocument').count(), 0);
  await action('document').first().click();
  await page.waitForURL('**/documents/*');
  assert.equal(await action('editDocument').count(), 0);
  const documentUrl = page.url();
  await page.reload();
  await page.locator('.paper h2').waitFor();
  assert.equal(page.url(), documentUrl);
  check('Document routing, direct refresh, guest controls');
  await go('operations');
  for (const a of [
    'newShip',
    'newRecord',
    'importOperations',
    'editRecord',
    'deleteRecord',
  ])
    assert.equal(await action(a).count(), 0);
  assert.equal(
    (await api('/api/changes', { kind: 'ship.save', payload: {} })).status,
    403,
  );
  check('Guest mutation buttons hidden and backend rejects writes');
  await login('wrong');
  await page.locator('#authError').filter({ hasText: '올바르지' }).waitFor();
  assert.equal(
    await page.locator('#authForm button[type=submit]').isDisabled(),
    false,
  );
  await page.locator('#auth-password').fill('1234');
  await page.locator('#authForm').evaluate((f) => f.requestSubmit());
  await action('logout').waitFor();
  await go('operations');
  await action('seedExample').click();
  await confirm();
  await page.locator('table tbody tr').first().waitFor();
  assert.equal((await api('/api/operations')).data.records.length, 21);
  check('Failed login retry, admin login, sample initialization');
  await go('docs');
  await action('newDocument').click();
  await page.locator('#f-title').fill('Next.js 검증 문서');
  await page.locator('#f-reference').fill('NEXT TEST');
  await page
    .locator('#f-text')
    .fill('--- PAGE 7 ---\n원문을 확인하고 운항 기록을 점검합니다.');
  await page.locator('[name=checked]').check();
  await page.locator('#documentForm').evaluate((f) => f.requestSubmit());
  await page
    .locator('.docrow')
    .filter({ hasText: 'Next.js 검증 문서' })
    .waitFor();
  await page
    .locator('.docrow')
    .filter({ hasText: 'Next.js 검증 문서' })
    .locator('[data-action=document]')
    .click();
  await action('editDocument').click();
  assert.equal(
    await page.locator('#documentForm button[type=submit]').innerText(),
    '저장',
  );
  await page.locator('#f-title').fill('Next.js 수정 문서');
  await page.locator('#f-version').fill('2');
  await page.locator('[name=checked]').check();
  await page.locator('#documentForm').evaluate((f) => f.requestSubmit());
  await page.waitForFunction(() => !document.querySelector('dialog').open);
  await go('docs');
  await page
    .locator('.docrow')
    .filter({ hasText: 'Next.js 수정 문서' })
    .locator('[data-action=document]')
    .click();
  await action('deleteDocument').click();
  assert.equal(await action('confirm').innerText(), '삭제');
  await confirm();
  await page.waitForURL('**/documents');
  assert.equal(
    await page
      .locator('.docrow')
      .filter({ hasText: 'Next.js 수정 문서' })
      .count(),
    0,
  );
  check('Document create, revision and immediate deletion');

  // A real one-page PDF exercises the local PDF.js worker and persisted source bytes.
  const pdfText = 'Next.js migration PDF evidence.';
  const content = `BT /F1 12 Tf 50 750 Td (${pdfText}) Tj ET`;
  const objects = [
    '<< /Type /Catalog /Pages 2 0 R >>',
    '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
    `<< /Length ${content.length} >>\nstream\n${content}\nendstream`,
  ];
  let pdf = '%PDF-1.4\n',
    offsets = [0];
  objects.forEach((o, i) => {
    offsets.push(Buffer.byteLength(pdf));
    pdf += `${i + 1} 0 obj\n${o}\nendobj\n`;
  });
  const xref = Buffer.byteLength(pdf);
  pdf += `xref\n0 6\n0000000000 65535 f \n${offsets
    .slice(1)
    .map((x) => String(x).padStart(10, '0') + ' 00000 n ')
    .join(
      '\n',
    )}\ntrailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF`;
  await go('docs');
  await action('newDocument').click();
  await page
    .locator('#document-file')
    .setInputFiles({
      name: 'migration.pdf',
      mimeType: 'application/pdf',
      buffer: Buffer.from(pdf),
    });
  await page.waitForFunction(() =>
    document
      .querySelector('#f-text')
      ?.value.includes('Next.js migration PDF evidence.'),
  );
  await page.locator('#f-title').fill('원문 PDF 검증');
  await page.locator('[name=checked]').check();
  await page.locator('#documentForm').evaluate((f) => f.requestSubmit());
  await page
    .locator('.docrow')
    .filter({ hasText: '원문 PDF 검증' })
    .locator('[data-action=document]')
    .click();
  await action('documentPdf').click();
  const pdfResponse = await context.request.get(
    await page
      .locator('iframe.pdf-frame')
      .getAttribute('src')
      .then((src) => base + src),
  );
  assert.equal(pdfResponse.status(), 200);
  assert.match(pdfResponse.headers()['content-type'], /application\/pdf/);
  assert.equal((await pdfResponse.body()).toString(), pdf);
  check('PDF.js extraction, page provenance, persisted PDF retrieval');
  await go('operations');
  await action('newShip').click();
  await page.locator('#f-name').fill('Next 검증 선박');
  await page.locator('#f-type').fill('벌크선');
  await page.locator('#f-dwt').fill('2000');
  await page.locator('#shipForm').evaluate((f) => f.requestSubmit());
  await page.waitForFunction(() => !document.querySelector('dialog').open);
  assert.equal((await api('/api/operations')).data.ships.length, 4);
  await action('newRecord').click();
  await page.locator('#f-date').fill('2026-09-30');
  for (const [field, val] of Object.entries({
    fuel: '20',
    factor: '3.114',
    distance: '200',
    speed: '10',
    fuelType: 'LSFO',
  }))
    await page.locator('#f-' + field).fill(val);
  await page.locator('#recordForm').evaluate((f) => f.requestSubmit());
  await page.waitForFunction(() => !document.querySelector('dialog').open);
  const newRecord = (await api('/api/operations')).data.records.find(
    (r) => r.date === '2026-09-30',
  );
  assert.ok(newRecord);
  await page
    .locator(`[data-action=deleteRecord][data-id="${newRecord.id}"]`)
    .click();
  await confirm();
  await page.waitForFunction(() => !document.querySelector('dialog').open);
  assert.equal((await api('/api/operations')).data.records.length, 21);
  check('Ship and record registration, date filters and record deletion');
  await page.locator('#to').fill('2026-09-28');
  await go('operations');
  await action('editRecord').first().click();
  await page.locator('#f-note').fill('React 즉시 수정 검증');
  await page.locator('#recordForm').evaluate((f) => f.requestSubmit());
  await page.waitForFunction(() => !document.querySelector('dialog').open);
  assert.ok(
    (await api('/api/operations')).data.records.some(
      (r) => r.note === 'React 즉시 수정 검증',
    ),
  );
  check('Record editing, controlled refresh');
  await page.locator('[data-tab=calculation]').click();
  await action('useSampleInputs').click();
  await page.locator('#calcForm').evaluate((f) => f.requestSubmit());
  await page.locator('.formula').waitFor();
  assert.match(await page.locator('.calculation-result').innerText(), /CO₂/);
  check('Server calculation and rendered result');
  await go('operations');
  await page.locator('[data-tab=overview]').click();
  await action('importOperations').click();
  const ship = (await api('/api/operations')).data.ships[0].id;
  await page
    .locator('#csvForm [type=file]')
    .setInputFiles({
      name: 'voyage.csv',
      mimeType: 'text/csv',
      buffer: Buffer.from(
        `ship,date,fuel,factor,distance,speed,fuelType\n${ship},2026-09-29,20,3.114,200,10,LSFO`,
      ),
    });
  await page.locator('#csvForm').evaluate((f) => f.requestSubmit());
  await action('commitCsv').waitFor();
  await action('commitCsv').click();
  await page.waitForFunction(() => !document.querySelector('dialog').open);
  assert.equal((await api('/api/operations')).data.records.length, 22);
  check('CSV upload, validation preview portal and immediate import');
  await action('logout').click();
  await action('openLogin').waitFor();
  await go('reports');
  await action('templateNoon').click();
  await page.locator('#report-text').waitFor();
  await page.waitForFunction(() =>
    document.querySelector('#report-text')?.value.includes('Noon'),
  );
  const reportUrl = page.url();
  assert.match(reportUrl, /\/reports\/(?!new)/);
  await page.locator('#report-title').fill('게스트 Next 보고서');
  await action('saveReport').click();
  await page.waitForFunction(
    () => document.querySelector('#saveStatus')?.textContent === '저장된 내용',
  );
  await go('docs');
  await page.goBack();
  await page.locator('#report-title').waitFor();
  assert.equal(
    await page.locator('#report-title').inputValue(),
    '게스트 Next 보고서',
  );
  await page.reload();
  await page.locator('#report-text').waitFor();
  assert.equal(
    await page.locator('#report-title').inputValue(),
    '게스트 Next 보고서',
  );
  if (await action('submitReport').isDisabled()) {
    await action('saveReport').click();
    await page.waitForFunction(
      () => !document.querySelector('[data-action=submitReport]').disabled,
    );
  }
  await action('submitReport').click();
  await confirm();
  await page.waitForFunction(
    () => document.querySelector('#report-text')?.readOnly,
  );
  check(
    'Guest report generation, saving, navigation, reload, review submission',
  );
  await login();
  await action('logout').waitFor();
  await go('admin');
  await action('adminTab').filter({ hasText: '승인' }).click();
  await page
    .locator('.docrow')
    .filter({ hasText: '보고서 확정 검토' })
    .locator('[data-action=reviewChange]')
    .click();
  await action('approveChange').click();
  await confirm();
  await page.waitForFunction(() => !document.querySelector('dialog').open);
  assert.equal(
    (await api('/api/reports')).data.reports.find(
      (r) => r.title === '게스트 Next 보고서',
    ).status,
    'approved',
  );
  check('Existing report approval workflow');
  await action('adminTab').filter({ hasText: '백업·복구' }).click();
  await action('createBackup').click();
  await action('downloadBackup').first().waitFor();
  check('Persistent data backup');

  await action('restoreBackup').first().click();
  await page.locator('#f-confirm').fill('복구');
  await page.locator('#restoreForm').evaluate((f) => f.requestSubmit());
  await action('openLogin').waitFor();
  assert.equal((await api('/api/health')).data.user.role, 'guest');
  assert.equal((await api('/api/operations')).data.records.length, 22);
  check('Backup restoration and login invalidation');
  await go('chat');
  await page.waitForFunction(() => !document.querySelector('.toast'));
  await page.screenshot({ path: join(run, 'desktop.png'), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.locator('.mobile-menu').click();
  assert.ok(
    await page
      .locator('.sidebar')
      .evaluate((el) => el.classList.contains('open')),
  );
  await page.locator('[data-nav=docs]').click();
  await page.waitForTimeout(300);
  assert.ok(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth + 1,
    ),
  );
  await page.screenshot({ path: join(run, 'mobile.png'), fullPage: true });
  check('Mobile navigation and overflow');
  assert.deepEqual(errors, [], 'Browser runtime errors');
  const significant = warnings.filter(
    (t) =>
      !t.includes('favicon') &&
      !t.includes('403') &&
      !t.includes('401') &&
      !t.includes('[HMR]') &&
      !t.includes('React DevTools'),
  );
  assert.deepEqual(significant, [], 'React/browser warnings');
  check('No browser exceptions or React warnings');
  console.log('ALL', checks.length, 'CHECKS PASSED. Screenshots:', run);
} finally {
  if (lastPage) {
    await lastPage
      .screenshot({ path: join(run, 'last-state.png'), fullPage: true })
      .catch(() => {});
    await writeFile(
      join(run, 'overlay.txt'),
      await lastPage
        .locator('nextjs-portal')
        .evaluateAll((els) =>
          els
            .map((el) => el.shadowRoot?.textContent || el.textContent)
            .join('\n'),
        )
        .catch(() => ''),
    );
  }
  await writeFile(
    join(run, 'result.json'),
    JSON.stringify({ checks, errors, warnings }, null, 2),
  );
  await writeFile(join(run, 'server.log'), serverLog);
  await browser?.close();
  if (server.exitCode === null) {
    const ended = once(server, 'exit');
    server.kill('SIGTERM');
    await ended;
  }
  console.log('QA files:', run);
}
