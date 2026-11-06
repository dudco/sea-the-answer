// Real Next.js UI; domain HTTP fixtures. Real PostgreSQL coverage runs separately.
import { test, expect } from '@playwright/test';

async function setup(page) {
  const state = { calls: [], errors: [], delay: null, needsShip: false, unsupported: false, filtered: false };
  page.on('pageerror', e => state.errors.push(e.message));
  const ship = { id: 'real-ship', name: 'VIKING CINDERELLA', imo: '8719188', dwt: 4228, type: 'Passenger ship', version: 1 };
  await page.route('**/api/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname;
    const json = data => route.fulfill({ contentType: 'application/json', body: JSON.stringify(data) });
    if (path === '/api/health') return json({ csrfToken: 'nav-csrf', authenticated: true, publicAccess: false,
      user: { id: 'viewer', role: 'viewer', name: '검증 조회자' }, llmConfigured: false });
    if (path === '/api/operations') return json({ ships: [
      { id: 'sample', name: '가상 선박', dwt: 1000, type: 'Bulk carrier', sample: true }, ship,
      { id: 'another', name: '다른 조회 선박', dwt: 1000, type: 'Bulk carrier' },
    ], records: [] });
    if (path === '/api/ask') {
      const body = request.postDataJSON();
      state.calls.push({ body, headers: request.headers() });
      if (state.delay) await state.delay;
      const source = { id: 'helsinki_berths', url: 'https://www.portofhelsinki.fi/', retrieved_at: '2026-11-04T01:43:00Z', attribution: 'Official port fixture' };
      const nav = { kind: 'port-reference', reference_only: true, admission: 'not_assessed',
        status: state.needsShip ? 'needs_ship' : state.unsupported ? 'unsupported_port' : 'reference_only',
        ship: state.needsShip ? null : ship, context: { imo_number: ship.imo },
        ship_options: state.needsShip ? [ship] : [], port_options: [{ port_id: 'WPI:28190', name: 'Helsinki' }],
        results: [], ports: [] };
      if (!state.needsShip && !state.unsupported) {
        nav.ports = ['Gothenburg', 'Helsinki'].map((name, i) => ({ port_id: 'port-'+i, name,
          berth_count: 1, partial_reference_check: 1, published_reference_exceeded: 0, insufficient_data: 0 }));
        nav.results = nav.ports.map(p => ({ ...p, port_name: p.name, assessed_at: '2026-11-04T02:00:00Z',
          port_source_id: 'helsinki_berths', observation: { metadata_received_at: '2026-11-04T01:42:00Z' },
          sources: [source], ship_issues: [], berths: [{ berth_id: p.port_id+':BERTH:LHD', status: 'partial_reference_check',
            conditions: ['Survey 2021; check local conditions.'], checks: [
              { kind: 'length', vessel_reported_m: '189', berth_listed_m: '360', status: 'within_listed_reference', reasons: [] },
              { kind: 'beam', vessel_reported_m: '34', berth_listed_m: null, status: 'unavailable', reasons: ['BERTH_LIMIT_NOT_PUBLISHED'] },
            ] }] }));
        if (state.filtered) {
          nav.query = { description: { ko: '공개 흘수 제한 8 m 이상', en: 'Published draught limit at least 8 m' } };
          nav.compared_berth_count = 8; nav.matched_berth_count = 4; nav.excluded_unknown_count = 1;
          nav.ports.forEach(p => { p.available_berth_count = 4; });
          nav.previous_query_id = body.context.previousQueryId;
        }
      }
      return json({ id: 'nav-'+state.calls.length, question: body.question, language: 'ko', generation: 'tool',
        status: nav.results.length ? 'reference_found' : 'needs_input', notice: state.unsupported ? '요청한 항구 자료가 없습니다.' : '일부 공개 수치 비교입니다. 실제 입항 허가 판정은 아닙니다.',
        warnings: ['NAVIGATION_REFERENCE_ONLY'], statements: [], evidence: [], toolRuns: [], reportSuggested: false, navigation: nav });
    }
    return json({ documents: [], reports: [], history: [], skills: [] });
  });
  await page.goto('/chat');
  await expect(page.locator('#ship')).toHaveValue('sample');
  return state;
}
async function ask(page, question) {
  await page.locator('#question').fill(question);
  await page.getByRole('button', { name: '질문 보내기', exact: true }).click();
}

test('question alone compares available ports and exact IMO aligns the existing context for the next question', async ({ page }) => {
  const state = await setup(page);
  await ask(page, 'IMO 8719188 선박이 입항 가능한 항구는?');
  const answer = page.locator('[data-navigation-answer]');
  await expect(answer).toContainText('VIKING CINDERELLA');
  await expect(answer.locator('table').first()).toContainText('Gothenburg');
  await expect(answer.locator('table').first()).toContainText('Helsinki');
  await expect(page.locator('#ship')).toHaveValue('real-ship');
  await expect(page.locator('.answer')).not.toContainText('문서 근거가 부족합니다');
  await expect(page.locator('.answer')).not.toContainText('CO₂');
  await answer.getByText('Helsinki · 선석별 근거·부족 항목 (1)', { exact: true }).click();
  await expect(answer).toContainText('189 m / 360 m');
  await expect(answer).toContainText('공개 수치 이내');
  await expect(answer).toContainText('흘수 측정 시각은 아닙니다');
  await page.setViewportSize({ width: 390, height: 844 });
  const detail = answer.locator('tbody tr').filter({ hasText: '선석 LHD' }).last().locator('td').last();
  await expect(detail).toHaveCSS('display', 'block');
  expect(await detail.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await ask(page, '우리 배가 입항 가능한 항구가 어디야?');
  await expect.poll(() => state.calls.length).toBe(2);
  await expect(answer).toBeVisible();
  expect(state.calls[0].body.context.ship).toBe('sample');
  expect(state.calls[1].body.context.ship).toBe('real-ship');
  expect(state.calls[1].body.context.previousQueryId).toBe('nav-1');
  expect(state.calls.every(c => c.headers.authorization === undefined && c.headers['x-haedap-token'] === 'nav-csrf')).toBe(true);
  expect(state.errors).toEqual([]);
});

test('followup sends only the displayed ship answer ID and shows applied reference conditions', async ({ page }) => {
  const state = await setup(page);
  await ask(page, 'IMO 8719188 선박이 입항 가능한 항구는?');
  await expect(page.locator('[data-navigation-answer]')).toBeVisible();
  state.filtered = true;
  await ask(page, '그럼 헬싱키는?');
  await expect.poll(() => state.calls.length).toBe(2);
  expect(state.calls[1].body.context.previousQueryId).toBe('nav-1');
  await expect(page.locator('[data-navigation-conditions]')).toContainText('공개 흘수 제한 8 m 이상');
  await expect(page.locator('[data-navigation-conditions]')).toContainText('8 / 4');
  await expect(page.locator('[data-navigation-conditions]')).toContainText('미확인으로 필터에서 제외: 1');
  await expect(page.locator('[data-navigation-conditions]')).toContainText('현재 자료를 다시 조회');
  await page.locator('#ship').selectOption('another');
  await ask(page, '그럼 예테보리는?');
  await expect.poll(() => state.calls.length).toBe(3);
  expect(state.calls[2].body.context.previousQueryId).toBeUndefined();
  expect(state.errors).toEqual([]);
});

test('a context change while a response is pending discards the previous ship answer', async ({ page }) => {
  const state = await setup(page);
  let release; state.delay = new Promise(resolve => { release = resolve; });
  await ask(page, 'IMO 8719188 선박이 입항 가능한 항구는?');
  await expect.poll(() => state.calls.length).toBe(1);
  await page.locator('#ship').selectOption('another');
  release(); state.delay = null;
  await expect(page.locator('#ship')).toHaveValue('another');
  await expect(page.locator('[data-navigation-answer]')).toHaveCount(0);
  await expect(page.getByRole('button', { name: '질문 보내기', exact: true })).toBeEnabled();
  expect(state.errors).toEqual([]);
});

test('clarification buttons submit a complete identity; unsupported ports never show fabricated candidates', async ({ page }) => {
  const state = await setup(page); state.needsShip = true;
  await ask(page, '우리 배가 입항 가능한 항구는?');
  await expect(page.locator('[data-navigation-answer]')).toBeVisible();
  state.needsShip = false;
  await page.locator('[data-navigation-answer]').getByRole('button', { name: 'VIKING CINDERELLA · 8719188', exact: true }).click();
  await expect.poll(() => state.calls.length).toBe(2);
  expect(state.calls[1].body.question).toContain('IMO 8719188');
  await expect(page.locator('[data-navigation-answer] table').first()).toBeVisible();
  state.unsupported = true;
  await ask(page, '우리 배가 부산항에 입항 가능해?');
  await expect(page.locator('.answer')).toContainText('요청한 항구 자료가 없습니다');
  await expect(page.locator('[data-navigation-answer] table')).toHaveCount(0);
  expect(state.errors).toEqual([]);
});
