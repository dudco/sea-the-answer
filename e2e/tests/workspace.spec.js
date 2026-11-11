// Full workspace flow in one browser session (ported from scripts/next-browser-smoke.mjs).
// Steps share state (login, sample data, created records), so they run in order inside one test.
import { test, expect } from '@playwright/test';

// A real one-page PDF exercises the local PDF.js worker and persisted source bytes.
function onePagePdf(text) {
  const content = `BT /F1 12 Tf 50 750 Td (${text}) Tj ET`;
  const objects = [
    '<< /Type /Catalog /Pages 2 0 R >>',
    '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
    `<< /Length ${content.length} >>\nstream\n${content}\nendstream`,
  ];
  let pdf = '%PDF-1.4\n';
  const offsets = [];
  objects.forEach((o, i) => {
    offsets.push(Buffer.byteLength(pdf));
    pdf += `${i + 1} 0 obj\n${o}\nendobj\n`;
  });
  const xref = Buffer.byteLength(pdf);
  pdf += `xref\n0 6\n0000000000 65535 f \n${offsets
    .map((x) => String(x).padStart(10, '0') + ' 00000 n ')
    .join('\n')}\ntrailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF`;
  return pdf;
}

test.beforeAll(async ({ request }) => {
  // The stack may still be starting (local runs); compose waits on health checks already.
  await expect
    .poll(async () => (await request.get('/api/health').catch(() => null))?.ok() ?? false, {
      timeout: 120_000,
      intervals: [500, 1000, 2000],
    })
    .toBe(true);
});

test('workspace: documents, operations, reports, admin review, backup', async ({ page, context }, testInfo) => {
  const errors = [];
  const warnings = [];
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('console', (m) => {
    if (['error', 'warning'].includes(m.type())) warnings.push(m.text());
  });

  const action = (a) => page.locator(`[data-action=${a}]`);
  const go = async (name) => {
    await page.locator(`[data-nav=${name}]`).click();
    const route = name === 'docs' ? 'documents' : name;
    await expect(page).toHaveURL(new RegExp(`/${route}$`));
  };
  const confirm = () => action('confirm').click();
  const close = () => action('closeModal').click();
  const submit = (form) => page.locator(form).evaluate((f) => f.requestSubmit());
  const dialogClosed = () => page.waitForFunction(() => !document.querySelector('dialog').open);
  const login = async (password = 'E2e-personal-admin-2026', username = 'e2e-admin') => {
    await page.locator('#auth-username').fill(username);
    await page.locator('#auth-password').fill(password);
    await submit('#authForm');
  };
  // Calls the API from the page, like the UI does (CSRF token + identity headers).
  const api = (path, body) =>
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
  const records = async () => (await api('/api/operations')).data.records;

  await test.step('Anonymous access blocked; bootstrap password rotation and crew provisioning', async () => {
    await page.goto('/');
    await page.locator('#authForm').waitFor();
    expect((await api('/api/documents')).status).toBe(401);
    await expect(page.locator('#question')).toHaveCount(0);
    await login('E2e-initial-only-2026');
    await page.locator('#passwordForm').waitFor();
    expect((await api('/api/documents')).data.error.code).toBe('PASSWORD_CHANGE_REQUIRED');
    await page.locator('#auth-password').fill('E2e-initial-only-2026');
    await page.locator('#auth-new-password').fill('E2e-personal-admin-2026');
    await page.locator('#auth-confirm-password').fill('E2e-personal-admin-2026');
    await submit('#passwordForm');
    await page.locator('#question').waitFor();
    await expect(page).toHaveURL(/\/chat$/);
    await expect(page.locator('.brand small')).toHaveText('SEA THE ANSWER');
    await go('admin');
    await action('adminTab').filter({ hasText: '사용자' }).click();
    await action('newUser').click();
    await page.locator('#f-name').fill('E2E 선원');
    await page.locator('#f-username').fill('e2e-crew');
    await expect(page.locator('#f-role')).toHaveValue('operator');
    await page.locator('#f-password').fill('E2e-initial-crew-2026');
    await submit('#userForm');
    await dialogClosed();
    await action('logout').click();
    await page.locator('#authForm').waitFor();
    await login('E2e-initial-crew-2026', 'e2e-crew');
    await page.locator('#passwordForm').waitFor();
    await page.locator('#auth-password').fill('E2e-initial-crew-2026');
    await page.locator('#auth-new-password').fill('E2e-personal-crew-2026');
    await page.locator('#auth-confirm-password').fill('E2e-personal-crew-2026');
    await submit('#passwordForm');
    await page.locator('#question').waitFor();
    expect((await api('/api/users')).status).toBe(403);
  });

  await test.step('Inventory questions use real empty SQL tables rather than unrelated legal evidence', async () => {
    for (const question of ['mrv 관련 데이터 있어?', 'MRV 관련 정보를 알려줘']) {
      await page.locator('#question').fill(question);
      const reply=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/ask' && r.request().method()==='POST');
      await submit('#askForm');
      const value=await (await reply).json();
      expect(value.generation).toBe('tool');
      expect(value.dataStatus.datasets[0]).toMatchObject({dataset:'mrv',status:'empty',row_count:0});
      expect(value.evidence).toEqual([]);
      await expect(page.locator('[data-dataset-status]').last()).toContainText('실제 MRV 연간 보고');
      await expect(page.locator('[data-dataset-status]').last()).toContainText('등록 건수 0');
      await expect(page.locator('.answer').last()).not.toContainText('AI 답변을 생성하지 못해');
      await expect(page.locator('.answer').last()).not.toContainText('문서 근거가 부족합니다');
    }
    await page.locator('#question').fill('AIS 관련 정보를 알려줘');
    const reply=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/ask' && r.request().method()==='POST');
    await submit('#askForm');
    const value=await (await reply).json();
    expect(value.navigation.kind).toBe('catalog-status');
    expect(value.navigation.status).toBe('unavailable');
    expect(value.evidence).toEqual([]);
    await expect(page.locator('.answer').last()).toContainText('AIS 자료 현황');
    await expect(page.locator('.answer').last()).toContainText('AIS 참조 수집본을 확인할 수 없습니다');
    await page.getByRole('button',{name:'새 질문',exact:true}).click();
    await expect(page.locator('.chat-turn')).toHaveCount(0);
  });

  await test.step('Question, real search, source dialog', async () => {
    await page.locator('#question').fill('연료 황 함유량 기준을 알려줘');
    const answerResponse = page.waitForResponse(
      (response) => new URL(response.url()).pathname === '/api/ask' && response.request().method() === 'POST',
      { timeout: 60_000 },
    );
    await submit('#askForm');
    expect((await answerResponse).ok()).toBe(true);
    await expect(page.locator('.answer')).toContainText('0.50%');
    await action('source').first().click();
    expect(await page.locator('dialog').evaluate((d) => d.open)).toBe(true);
    await close();
  });

  await test.step('Document routing, direct refresh, crew controls', async () => {
    await go('docs');
    await expect(action('newDocument')).toHaveCount(0);
    await action('document').first().click();
    await page.waitForURL('**/documents/*');
    await expect(action('editDocument')).toHaveCount(0);
    const documentUrl = page.url();
    await page.reload();
    await page.locator('.paper h2').waitFor();
    expect(page.url()).toBe(documentUrl);
  });

  await test.step('Crew mutation buttons hidden and backend rejects writes', async () => {
    await go('operations');
    for (const a of ['newShip', 'newRecord', 'importOperations', 'editRecord', 'deleteRecord'])
      await expect(action(a)).toHaveCount(0);
    expect((await api('/api/changes', { kind: 'ship.save', payload: {} })).status).toBe(403);
  });

  await test.step('Failed login retry, admin login, sample initialization', async () => {
    await action('logout').click();
    await page.locator('#authForm').waitFor();
    await login('wrong');
    await page.locator('#authError').filter({ hasText: '올바르지' }).waitFor();
    await expect(page.locator('#authForm button[type=submit]')).toBeEnabled();
    await page.locator('#auth-password').fill('E2e-personal-admin-2026');
    await submit('#authForm');
    await action('logout').waitFor();
    await go('operations');
    await action('seedExample').click();
    await confirm();
    await page.locator('table tbody tr').first().waitFor();
    expect(await records()).toHaveLength(21);
  });

  await test.step('Natural-language table and chart requests use real document and operation data', async () => {
    await go('chat');
    await page.locator('#question').fill('연료 황 함유량 한도를 표로 보여줘');
    const tableResponse = page.waitForResponse(
      response => new URL(response.url()).pathname === '/api/ask' && response.request().method() === 'POST',
      { timeout: 60_000 },
    );
    await submit('#askForm');
    const tableResult = await tableResponse;
    expect(tableResult.ok()).toBe(true);
    // No outputFormat shortcut: the server must recognize the question's table request.
    expect(tableResult.request().postDataJSON().outputFormat).toBeUndefined();
    expect(tableResult.request().postDataJSON().task).toBe('auto');
    const documentAnswer = await tableResult.json();
    expect(documentAnswer.presentation.type).toBe('table');
    expect(documentAnswer.presentation.source).toBe('documents');
    expect(documentAnswer.generation).toBe('extractive'); // This stack intentionally has no real LLM.
    const documentTable = page.getByRole('table', { name: documentAnswer.presentation.title, exact: true });
    await expect(documentTable).toBeVisible();
    await expect(documentTable).toContainText('0.50%');
    const citation = documentAnswer.presentation.rows[0].citations[0];
    const source = documentAnswer.evidence.find(item => item.id === citation.chunkId);
    expect(source.text).toContain(citation.quote);
    await documentTable.locator('[data-action=source]').first().click();
    await expect(page.locator('.modal-body .quote')).toHaveText(source.text);
    await close();
    await dialogClosed();

    const operations = (await api('/api/operations')).data;
    const ship = operations.ships.find(item => operations.records.some(row => row.ship === item.id));
    const rows = operations.records.filter(row => row.ship === ship.id).sort((a, b) => a.date.localeCompare(b.date));
    expect(rows.length).toBeGreaterThan(0);
    await expect(page.locator('.query-context')).toHaveCount(0);
    await page.locator('#question').fill('일별 CO₂ 배출량을 막대그래프로 보여줘');
    const initialChartResponse=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/ask' && r.request().method()==='POST');
    await submit('#askForm');
    expect((await (await initialChartResponse).json()).workflow.clarification.field).toBe('ships');
    const shipChoiceResponse=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/ask' && r.request().method()==='POST');
    await page.locator(`[data-workflow-choice="${ship.id}"]`).click();
    expect((await (await shipChoiceResponse).json()).workflow.clarification.field).toBe('periods');
    await page.locator('#question').fill(`${rows[0].date}부터 ${rows.at(-1).date}까지`);
    const chartResponse = page.waitForResponse(
      response => new URL(response.url()).pathname === '/api/ask' && response.request().method() === 'POST',
      { timeout: 60_000 },
    );
    await submit('#askForm');
    const chartResult = await chartResponse;
    expect(chartResult.ok()).toBe(true);
    const operationAnswer = await chartResult.json(), presentation = operationAnswer.presentation;
    expect(presentation.type).toBe('chart');
    expect(presentation.chartType).toBe('bar');
    expect(presentation.source).toBe('operations');
    expect(operationAnswer.operations.ship.id).toBe(ship.id);
    expect(operationAnswer.compliance.status).toBe('unknown');
    expect(presentation.points).toHaveLength(rows.length);
    for (const point of presentation.points) {
      const record = rows.find(row => row.date === point.label);
      expect(record).toBeTruthy();
      expect(point.value).toBeCloseTo(record.fuel * record.factor, 6);
    }
    expect(chartResult.request().postDataJSON().task).toBe('auto');
    const chart = page.locator(`[data-answer-id="${operationAnswer.id}"] .answer-presentation svg`);
    await expect(documentTable).toBeVisible();
    await expect(chart).toBeVisible();
    await expect(chart.getByText(presentation.xLabel, { exact: true })).toBeVisible();
    await expect(chart.getByText(`${presentation.yLabel} (${presentation.unit})`, { exact: true })).toBeVisible();
    await expect(chart.locator('rect')).toHaveCount(rows.length);
    await page.getByText('차트 데이터 표 보기', { exact: true }).click();
    const dataTable = page.getByRole('table', { name: `${presentation.title} 데이터`, exact: true });
    await expect(dataTable).toBeVisible();
    const firstPoint = presentation.points[0];
    const firstRow = dataTable.getByRole('row').filter({ hasText: firstPoint.label });
    await expect(firstRow.getByRole('cell', {
      name: firstPoint.value.toLocaleString('ko-KR', { maximumFractionDigits: 6 }), exact: true,
    })).toBeVisible();
  });

  await test.step('Document create, revision and immediate deletion', async () => {
    await go('docs');
    await action('newDocument').click();
    await page.locator('#f-title').fill('Next.js 검증 문서');
    await page.locator('#f-reference').fill('NEXT TEST');
    await page.locator('#f-text').fill('--- PAGE 7 ---\n원문을 확인하고 운항 기록을 점검합니다.');
    await page.locator('[name=checked]').check();
    await submit('#documentForm');
    const created = page.locator('.docrow').filter({ hasText: 'Next.js 검증 문서' });
    await created.waitFor();
    await created.locator('[data-action=document]').click();
    await expect(page).toHaveURL(/\/documents\/[^/]+$/);
    const before = (await api('/api/documents')).data.documents.find((d) => d.title === 'Next.js 검증 문서');
    const writes = [];
    const recordWrite = (request) => {
      if (request.url().endsWith('/api/changes') && request.method() === 'POST') writes.push(request.postDataJSON());
    };
    page.on('request', recordWrite);
    await action('editDocument').click();
    await expect(page.locator('#f-documentMode')).toHaveValue('metadata');
    await expect(page.locator('#f-text')).toBeHidden();
    await expect(page.locator('#f-text')).toHaveValue('');
    await page.locator('[name=checked]').check();
    await submit('#documentForm');
    await dialogClosed();
    expect(writes).toHaveLength(0);
    await action('editDocument').click();
    await page.locator('#f-issuer').fill('재청킹 방지 검증');
    await page.locator('[name=checked]').check();
    await submit('#documentForm');
    await dialogClosed();
    expect(writes).toHaveLength(1);
    expect(writes[0].payload.mode).toBe('metadata');
    expect(writes[0].payload.document).toEqual({ id: before.logical_id });
    const after = (await api('/api/documents')).data.documents.find((d) => d.id === before.id);
    expect(after.sections).toEqual(before.sections);
    expect(after.reviewed_at).toBe(before.reviewed_at);
    expect(after.meta.issuer).toBe('재청킹 방지 검증');
    page.off('request', recordWrite);
    await action('editDocument').click();
    await expect(page.locator('#documentForm button[type=submit]')).toHaveText('저장');
    await page.locator('#f-documentMode').selectOption('content');
    await page.locator('#f-title').fill('Next.js 수정 문서');
    await page.locator('#f-version').fill('2');
    await expect(page.locator('#f-text')).toHaveValue('');
    await page.locator('[name=checked]').check();
    await submit('#documentForm');
    expect(await page.locator('dialog').evaluate((d) => d.open)).toBe(true);
    expect(await page.locator('#f-text').evaluate((el) => el.validity.valueMissing)).toBe(true);
    await page.locator('#f-text').fill('--- PAGE 7 ---\n개정된 원문 전체를 다시 검토합니다.');
    await page.locator('[name=checked]').check();
    await submit('#documentForm');
    await dialogClosed();
    await go('docs');
    const revised = page.locator('.docrow').filter({ hasText: 'Next.js 수정 문서' });
    await revised.locator('[data-action=document]').click();
    await action('deleteDocument').click();
    await expect(action('confirm')).toHaveText('삭제');
    await confirm();
    await page.waitForURL('**/documents');
    await expect(revised).toHaveCount(0);
  });

  await test.step('PDF.js extraction, page provenance, persisted PDF retrieval', async () => {
    const pdfText = 'Next.js migration PDF evidence.';
    const pdf = onePagePdf(pdfText);
    await go('docs');
    await action('newDocument').click();
    await page
      .locator('#document-file')
      .setInputFiles({ name: 'migration.pdf', mimeType: 'application/pdf', buffer: Buffer.from(pdf) });
    await page.waitForFunction(
      (t) => document.querySelector('#f-text')?.value.includes(t),
      pdfText,
    );
    await page.locator('#f-title').fill('원문 PDF 검증');
    await page.locator('[name=checked]').check();
    await submit('#documentForm');
    await page.locator('.docrow').filter({ hasText: '원문 PDF 검증' }).locator('[data-action=document]').click();
    await action('documentPdf').click();
    const src = await page.locator('iframe.pdf-frame').getAttribute('src');
    const response = await context.request.get(src);
    expect(response.status()).toBe(200);
    expect(response.headers()['content-type']).toMatch(/application\/pdf/);
    expect((await response.body()).toString()).toBe(pdf);
  });

  await test.step('Ship and record registration, record deletion', async () => {
    await go('operations');
    await action('newShip').click();
    await page.locator('#f-name').fill('Next 검증 선박');
    await page.locator('#f-type').fill('벌크선');
    await page.locator('#f-dwt').fill('2000');
    await submit('#shipForm');
    await dialogClosed();
    expect((await api('/api/operations')).data.ships).toHaveLength(4);
    await action('newRecord').click();
    await page.locator('#f-date').fill('2026-09-30');
    for (const [field, value] of Object.entries({ fuel: '20', factor: '3.114', distance: '200', speed: '10', fuelType: 'LSFO' }))
      await page.locator('#f-' + field).fill(value);
    await submit('#recordForm');
    await dialogClosed();
    const added = (await records()).find((r) => r.date === '2026-09-30');
    expect(added).toBeTruthy();
    await page.locator(`[data-action=deleteRecord][data-id="${added.id}"]`).click();
    await confirm();
    await dialogClosed();
    expect(await records()).toHaveLength(21);
  });

  await test.step('Record editing with date filter', async () => {
    await page.locator('#to').fill('2026-09-28');
    await go('operations');
    await action('editRecord').first().click();
    await page.locator('#f-note').fill('React 즉시 수정 검증');
    await submit('#recordForm');
    await dialogClosed();
    expect((await records()).some((r) => r.note === 'React 즉시 수정 검증')).toBe(true);
  });

  await test.step('Server calculation and rendered result', async () => {
    await page.locator('[data-tab=calculation]').click();
    await action('useSampleInputs').click();
    await submit('#calcForm');
    await page.locator('.formula').waitFor();
    await expect(page.locator('.calculation-result')).toContainText('CO₂');
  });

  await test.step('CSV upload, validation preview and import', async () => {
    await go('operations');
    await page.locator('[data-tab=overview]').click();
    await action('importOperations').click();
    const ship = (await api('/api/operations')).data.ships[0].id;
    await page.locator('#csvForm [type=file]').setInputFiles({
      name: 'voyage.csv',
      mimeType: 'text/csv',
      buffer: Buffer.from(`ship,date,fuel,factor,distance,speed,fuelType\n${ship},2026-09-29,20,3.114,200,10,LSFO`),
    });
    await submit('#csvForm');
    await action('commitCsv').click();
    await expect(page.locator('[data-import-database]')).toBeVisible();
    await close();
    await dialogClosed();
    expect(await records()).toHaveLength(22);
  });

  await test.step('Crew report generation, saving, navigation, reload, review submission', async () => {
    await action('logout').click();
    await page.locator('#authForm').waitFor();
    await login('E2e-personal-crew-2026', 'e2e-crew');
    await page.locator('#question').waitFor();
    await go('reports');
    await action('templateNoon').click();
    await page.waitForFunction(() => document.querySelector('#report-text')?.value.includes('Noon'));
    expect(page.url()).toMatch(/\/reports\/(?!new)/);
    await page.locator('#report-title').fill('게스트 Next 보고서');
    await action('saveReport').click();
    await page.waitForFunction(() => document.querySelector('#saveStatus')?.textContent === '저장된 내용');
    await go('docs');
    await page.goBack();
    await expect(page.locator('#report-title')).toHaveValue('게스트 Next 보고서');
    await page.reload();
    await page.locator('#report-text').waitFor();
    await expect(page.locator('#report-title')).toHaveValue('게스트 Next 보고서');
    if (await action('submitReport').isDisabled()) {
      await action('saveReport').click();
      await expect(action('submitReport')).toBeEnabled();
    }
    await action('submitReport').click();
    await confirm();
    await page.waitForFunction(() => document.querySelector('#report-text')?.readOnly);
    await expect(action('deleteReport')).toHaveCount(0);
    const guestReportId = decodeURIComponent(new URL(page.url()).pathname.split('/').at(-1));
    expect((await api('/api/reports/delete', { id: guestReportId, version: 1 })).status).toBe(403);
  });

  await test.step('Report approval workflow', async () => {
    await action('logout').click();
    await page.locator('#authForm').waitFor();
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
    await dialogClosed();
    const report = (await api('/api/reports')).data.reports.find((r) => r.title === '게스트 Next 보고서');
    expect(report.status).toBe('approved');
  });

  await test.step('Admin report deletion and pending review cleanup', async () => {
    await go('reports');
    await page.locator('.docrow').filter({ hasText: '게스트 Next 보고서' }).locator('[data-action=openReport]').click();
    const id = decodeURIComponent(new URL(page.url()).pathname.split('/').at(-1));
    await action('deleteReport').click();
    await confirm();
    await page.waitForURL('**/reports');
    expect((await api('/api/reports/' + id)).status).toBe(404);
    const created = await api('/api/reports', { title: '삭제 대기 보고서', type: '규정 검토',
      text: '검토 대기 삭제 검증', sources: [], version: 0, body: {} });
    const report = created.data.report;
    const submitted = await api('/api/reports/submit', { id: report.id, version: report.version });
    expect((await api('/api/reports/delete', { id: report.id, version: report.version + 1 })).status).toBe(409);
    expect((await api('/api/reports/delete', { id: report.id, version: report.version })).status).toBe(200);
    const changes = (await api('/api/changes')).data.changes;
    expect(changes.find(change => change.id === submitted.data.id).status).toBe('rejected');
    expect((await api('/api/changes/review', { id: submitted.data.id, decision: 'approve' })).status).toBe(409);
    await go('admin');
  });

  await test.step('Backup creation, restoration and login invalidation', async () => {
    await action('adminTab').filter({ hasText: '백업·복구' }).click();
    const created = page.waitForResponse((response) =>
      response.url().endsWith('/api/backups') && response.request().method() === 'POST');
    await action('createBackup').click();
    const { backup } = await (await created).json();
    const restore = page.locator(`[data-action=restoreBackup][data-id="${backup.id}"]`);
    await restore.click();
    await page.locator('#f-confirm').fill('복구');
    // Exercise a BUSY response deterministically, then use the real restore API.
    // The automatic backup can also hold its DB lock outside HTTP request slots.
    await page.route('**/api/backups/restore', route => route.fulfill({
      status: 409, contentType: 'application/json',
      body: JSON.stringify({error: {code: 'BUSY', message: '다른 요청 또는 복구가 진행 중입니다.'}}),
    }), {times: 1});
    const restoreDeadline = Date.now() + 15_000;
    let busyResponses = 0;
    for (;;) {
      await expect(page.locator('#restoreForm button[type=submit]')).toBeEnabled();
      const restoreResponse = page.waitForResponse(response =>
        new URL(response.url()).pathname === '/api/backups/restore' && response.request().method() === 'POST');
      await submit('#restoreForm');
      const restored = await restoreResponse;
      const restoreResult = await restored.json();
      if (restored.status() === 409 && restoreResult.error?.code === 'BUSY' && Date.now() < restoreDeadline) {
        busyResponses++;
        await expect(page.locator('#restoreForm')).toBeVisible();
        await expect(page.locator('#f-confirm')).toHaveValue('복구');
        await page.waitForTimeout(250); // Back off only for the documented BUSY rejection.
        continue;
      }
      expect(restored.status(), JSON.stringify(restoreResult.error || {})).toBe(200);
      break;
    }
    expect(busyResponses).toBeGreaterThanOrEqual(1);
    await page.locator('#authForm').waitFor();
    expect((await api('/api/health')).data.user.role).toBe('guest');
    expect((await api('/api/operations')).status).toBe(401);
    await login();
    await action('logout').waitFor();
    expect(await records()).toHaveLength(22);
  });

  await test.step('Skills: selected documents and checklist stay within scope without a model', async () => {
    await go('chat');
    await expect(page.locator('[data-nav=skills]')).toHaveCount(0);
    await expect(page.locator('[data-workflow=documents]')).toHaveCount(0);
    const docs = (await api('/api/documents')).data.documents.filter(d => d.active);
    const source = docs.find(d => d.sections.some(s => s.text.includes('연료'))) || docs[0];
    const question = source.sections[0].text.slice(0, 80);
    await page.goto('/documents/' + encodeURIComponent(source.id));
    const panel=page.locator('[data-workflow=document]');
    await panel.locator('summary').first().click();
    await panel.getByLabel('실행할 기능').selectOption('selected-document-answer');
    const selectedDocument = panel.locator(`[data-document-id="${source.id}"]`);
    await selectedDocument.check();
    await panel.getByLabel('질문 또는 작업 목적').fill('선택 상태 유지 확인');
    await expect(selectedDocument).toBeChecked();
    await selectedDocument.uncheck();
    await expect(selectedDocument).not.toBeChecked();
    await selectedDocument.check();
    const secondSource = docs.find(d=>d.id!==source.id);
    if(secondSource){
      const secondDocument=panel.locator(`[data-document-id="${secondSource.id}"]`);
      await secondDocument.check();
      await expect(selectedDocument).toBeChecked();
      await expect(secondDocument).toBeChecked();
      await secondDocument.uncheck();
    }
    await panel.getByLabel('질문 또는 작업 목적').fill(question);
    let releaseExecution;
    const executionGate = new Promise(resolve=>{releaseExecution=resolve;});
    const holdExecution = async route=>{await executionGate; await route.continue();};
    await page.route('**/api/skills/run',holdExecution);
    const response = page.waitForResponse(r => r.url().endsWith('/api/skills/run') && r.request().method() === 'POST');
    await panel.getByRole('button', { name: '실행', exact: true }).click();
    try {
      await expect(selectedDocument).toBeDisabled();
      await expect(panel.getByLabel('질문 또는 작업 목적')).toBeDisabled();
    } finally { releaseExecution(); }
    const value = await (await response).json();
    await page.unroute('**/api/skills/run',holdExecution);
    expect(value.evidence.length).toBeGreaterThan(0);
    expect(value.evidence.every(e => e.document_id === source.id)).toBe(true);
    expect(value.generation).toBe('extractive');
    await expect(page.locator('.skill-evidence').first()).toBeVisible();
    await page.goto('/documents/' + encodeURIComponent(source.id));
    const documentPanel = page.locator('[data-workflow=document]');
    await documentPanel.locator('summary').first().click();
    await expect(documentPanel.locator(`[data-document-id="${source.id}"]`)).toBeChecked();
    await documentPanel.getByLabel('실행할 기능').selectOption('checklist');
    await documentPanel.getByLabel('질문 또는 작업 목적').fill(question);
    await documentPanel.getByRole('button', { name: '실행', exact: true }).click();
    await expect(page.getByRole('heading', { name: '점검 항목 초안', exact: true })).toBeVisible();
    await expect(page.getByRole('checkbox', { name: '점검 항목 1', exact: true })).not.toBeChecked();
  });

  await test.step('Skills: operation summary, report preview and explicit draft save', async () => {
    const ops = (await api('/api/operations')).data;
    const ship = ops.ships[0];
    const days = ops.records.filter(r => r.ship === ship.id).map(r => r.date).sort();
    await go('operations');
    const panel = page.locator('[data-workflow=operations]');
    await panel.locator('summary').first().click();
    await panel.getByLabel('실행할 기능').selectOption('operation-summary');
    await panel.getByLabel('선박', { exact: true }).selectOption(ship.id);
    await panel.getByLabel('시작일', { exact: true }).fill(days[0]);
    await panel.getByLabel('종료일', { exact: true }).fill(days.at(-1));
    await panel.getByLabel('질문 또는 작업 목적').fill('기간 운항 실적을 요약해줘');
    await panel.getByRole('button', { name: '실행', exact: true }).click();
    await expect(page.locator('.skill-metrics')).toContainText('계산 CO₂');
    const before = (await api('/api/reports')).data.reports.length;
    await go('reports');
    const reportPanel = page.locator('[data-workflow=reports]');
    await reportPanel.locator('summary').first().click();
    await reportPanel.getByLabel('선박', { exact: true }).selectOption(ship.id);
    await reportPanel.getByLabel('시작일', { exact: true }).fill(days[0]);
    await reportPanel.getByLabel('종료일', { exact: true }).fill(days.at(-1));
    await reportPanel.getByLabel('질문 또는 작업 목적').fill('보고서 초안을 만들어줘');
    const response = page.waitForResponse(r => r.url().endsWith('/api/skills/run') && r.request().method() === 'POST');
    await reportPanel.getByRole('button', { name: '실행', exact: true }).click();
    const value = await (await response).json();
    await expect(page.getByLabel('보고서 초안 내용')).toContainText('검토용');
    expect((await api('/api/reports')).data.reports).toHaveLength(before);
    let releaseSave;
    const saveGate = new Promise(resolve=>{releaseSave=resolve;});
    const holdSave = async route=>{if(route.request().method()==='POST')await saveGate; await route.continue();};
    await page.route('**/api/reports',holdSave);
    await page.getByRole('button', { name: '새 보고서 초안으로 저장', exact: true }).click();
    try {
      await expect(reportPanel.getByRole('button',{name:'실행',exact:true})).toBeDisabled();
      await expect(reportPanel.getByLabel('선박',{exact:true})).toBeDisabled();
    } finally { releaseSave(); }
    await expect(page.getByRole('button', { name: '초안 저장됨', exact: true })).toBeDisabled();
    await page.unroute('**/api/reports',holdSave);
    await expect(reportPanel).toContainText('새 보고서 초안으로 저장했습니다. 제출되지 않았습니다.');
    expect((await api('/api/reports')).data.reports).toHaveLength(before + 1);
    await page.getByRole('button', { name: '저장한 초안 열기', exact: true }).click();
    await expect(page).toHaveURL(/\/reports\//);
    await expect(page.locator('#report-title')).toHaveValue(value.result.draft.title);
    await expect(page.locator('#report-text')).toHaveValue(value.result.draft.text);
    await go('reports');
    const savedRow = page.locator('.docrow').filter({ hasText: value.result.draft.title });
    await expect(savedRow).toContainText(`${value.result.from} ~ ${value.result.to}`);
    await go('chat');
    await action('history').click();
    await page.locator(`[data-action=historyAnswer][data-id="${value.id}"]`).click();
    const evaluation = page.locator('[data-workflow=evaluation]');
    await evaluation.locator('summary').first().click();
    await evaluation.getByRole('button', { name: '응답 점검 실행', exact: true }).click();
    await expect(page.locator('.skill-result table')).toContainText('사람 검토 필요');
  });

  await test.step('Skills: MRV requires an explicit real vessel mapping', async () => {
    const ship = (await api('/api/operations')).data.ships[0];
    await go('operations');
    const panel = page.locator('[data-workflow=operations]');
    await panel.locator('summary').first().click();
    await panel.getByLabel('실행할 기능').selectOption('mrv-analysis');
    await panel.getByLabel('선박', { exact: true }).selectOption(ship.id);
    await panel.getByLabel('MRV 보고연도').fill('2018');
    await panel.getByLabel('질문 또는 작업 목적').fill('MRV 참고값을 확인해줘');
    await panel.getByRole('button', { name: '실행', exact: true }).click();
    await expect(page.locator('article')).toContainText('명시적 연결이 필요합니다');
  });

  await test.step('Mobile navigation and overflow', async () => {
    await go('chat');
    await action('history').click();
    await page.locator('[data-action=historyAnswer]').first().click();
    await expect(page.locator('article.answer')).toContainText('업무 스킬');
    await page.waitForFunction(() => !document.querySelector('.toast'));
    await page.screenshot({ path: testInfo.outputPath('desktop.png'), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator('.mobile-menu').click();
    await expect(page.locator('.sidebar')).toHaveClass(/\bopen\b/);
    await page.locator('[data-nav=docs]').click();
    await page.waitForTimeout(300);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath('mobile.png'), fullPage: true });
  });

  await test.step('No browser exceptions or React warnings', async () => {
    expect(errors, 'Browser runtime errors').toEqual([]);
    const significant = warnings.filter(
      (t) => !['favicon', '403', '401', '404', '409', '[HMR]', 'React DevTools'].some((s) => t.includes(s)),
    );
    expect(significant, 'React/browser warnings').toEqual([]);
  });
});
