// Production Next.js UI with mocked domain HTTP data; real DB coverage is separate.
import { test, expect } from '@playwright/test';

async function setup(page) {
  const calls = [], errors = [];
  page.on('pageerror', e => errors.push(e.message));
  const control = { calls, errors, delay: null, error: false, multi: false, quality: false, guidance: false };
  const source = { id: 'ais', url: 'https://example.org/ais', retrieved_at: '2026-11-04T00:00:00Z', attribution: 'test fixture' };
  await page.route('**/api/**', async route => {
    const req = route.request(), path = new URL(req.url()).pathname;
    const json = (data, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) });
    const user = { id: 'viewer-1', name: '참조 조회자', role: 'viewer', version: 1 };
    if (path === '/api/health') return json({ csrfToken: 'csrf-test', user, authenticated: true, publicAccess: false, llmConfigured: false });
    if (path === '/api/operations') return json({ ships: [
      { id: 'ship-1', name: '참조 선박 A', type: 'Bulk carrier', imo: '7422881', dwt: 1000, version: 3 },
      { id: 'ship-2', name: '미연결 선박 B', type: 'Bulk carrier', imo: '9074729', dwt: 1000, version: 2 },
      { id: 'sample', name: '가상 선박', type: 'Bulk carrier', dwt: 1000, version: 1, sample: true },
    ], records: [] });
    if (path === '/api/operations/port-references') {
      calls.push({ path });
      const ports = [{ port_id: 'WPI:24020', name: 'Gothenburg', unlocode: 'SEGOT', source_id: 'berths',
        capture_issue: control.multi ? 'PORT_CAPTURE_STALE' : null, berths: [
        { berth_id: 'WPI:24020:BERTH:510', label: '510', issues: [] },
        { berth_id: 'WPI:24020:BERTH:812', label: '812', issues: ['DUPLICATE_BERTH_VARIANTS_REQUIRE_REVIEW'] },
      ] }];
      if (control.multi) ports.push({ port_id: 'WPI:28190', name: 'Helsinki', unlocode: 'FIHEL', source_id: 'helsinki_berths',
        capture_issue: null, retrieved_at: '2026-11-04T00:00:00Z', berths: [{ berth_id: 'WPI:28190:BERTH:LHD', label: 'LHD', issues: [] }] });
      return json({ generated_at: '2026-11-04T00:00:00Z', ais_observation_count: 2,
        ais_unique_vessels: 2, ais_source_counts: { ais: 1, ais_no: 1 },
        freshness: { ais_capture_issue: null, port_capture_issue: null },
        ports });
    }
    if (path === '/api/operations/port-reference-screen') {
      const body = req.postDataJSON();
      calls.push({ path, body, headers: req.headers() });
      if (control.delay) await control.delay;
      if (control.error) return json({ error: { code: 'DATA_SOURCE_UNAVAILABLE', message: '참조 자료의 준비 상태를 확인해 주세요.' } }, 503);
      if (body.ship === 'ship-2') return json({ status: 'needs_mapping', context: { ship: body.ship, ship_version: 2 }, result: null, notice: '명시적 연결이 필요합니다.' });
      return json({ status: 'ok', context: { ship: body.ship, ship_version: 3, imo_number: '7422881' },
        notice: '입항 허가는 별도 확인이 필요합니다.', latest_record_draught: { date: '2026-10-01', draught_m: '6.2', measurement_time: null, notice: '측정 시각 확인 필요.' },
        result: { port_name: body.port_id === 'WPI:28190' ? 'Helsinki' : 'Gothenburg', assessed_at: '2026-11-04T00:00:00Z', ship_issues: ['AIS_RECORD_STALE'],
          ...(control.guidance ? {official_guidance:{notice:'공식 게시 지침이며 적용 여부·입항 승인 확인이 필요합니다.',documents:[{
            id:body.port_id==='WPI:28190'?'helsinki_regulations':'gothenburg_draught',title:'Official guidance',attribution:'Port authority',url:'https://example.org/guidance',
            displayed_updated_on:body.port_id==='WPI:28190'?null:'2021-01-31',effective_on:body.port_id==='WPI:28190'?'2023-02-07':null,
            retrieved_at:'2026-11-05T00:00:00Z',displayed_revision_age_status:'older_than_one_year',capture_age_status:'within_age_window',facts:[{
              id:'reviewed-condition',title:body.port_id==='WPI:28190'?'현 수심 확인':'수로 선저 여유',summary:'현재 확인이 필요한 게시 조건입니다.',
              scope:'접근 수로에 한함. 현재 선석 수심과 구분합니다.',values:body.port_id==='WPI:28190'?[]:[{label:'수로 게시 최소 UKC',value:'0.7',unit:'m'}],
              evidence_text:'<script>Source text remains text.</script>',locator:'normalized-main-text:10-60'}]}]}}:{}),
          ...(control.quality ? {static_reference:{status:'reference_available',candidate_count:1,as_of:'2026-11-01T00:00:00Z',length_m:'140',beam_m:'23',
            notice:'과거 등록값이며 현재 실측과 구분합니다.',candidates:[{registry_imo_number:'7422881',mmsi:'123456789',reference_length_m:'140',reference_beam_m:'23',registry_draught_m:'8.02',valid_from:'2021-01-08T00:00:00Z',valid_to:null,issues:[]}]},
            environment:{notice:'지역 관측이며 선석 현장값·예보가 아닙니다.',observations:body.port_id==='WPI:24020'?[{
              station_name:'Göteborg-Tångudden',value:'-13.4',unit:'cm',vertical_datum:'RH2000',quality:'O',quality_status:'unchecked',
              observed_at:'2026-11-04T00:00:00Z',age_status:'stale',capture_age_status:'stale',latitude:'57.6821',longitude:'11.8722',
              station_metadata:{url:'https://example.org/station'},datum_evidence:{url:'https://example.org/datum'},source_ref:{source_id:'smhi_water_gothenburg'}}]:[]}}:{}),
          observation: { metadata_received_at: '2026-10-31T00:00:00Z' }, sources: [source],
          berths: [{ berth_id: body.berth_id || 'WPI:24020:BERTH:510', status: 'insufficient_data',
            checks: [{ kind: 'draught', vessel_reported_m: '6.5', berth_listed_m: '7', status: 'unavailable', reasons: ['AIS_RECORD_STALE'] }],
            ...(control.quality ? {static_reference_checks:[{kind:'length',reference_value_m:'140',berth_listed_m:'100',status:'reference_value_exceeded'}]} : {}),
            conditions: ['Tug approval required.'] }] } });
    }
    return json({ documents: [], reports: [], history: [], changes: [], logs: [], users: [], backups: [], skills: [] });
  });
  await page.goto('/operations');
  await expect(page.locator('#ship')).toHaveValue('ship-1');
  return control;
}
const open = async page => { await page.getByText('항구·선석 참조 비교', { exact: true }).click(); await expect(page.getByLabel('참조 항구')).toHaveValue('WPI:24020'); };

test('official guidance qualifies old revision dates and follows the selected port without filling scenario',async({page})=>{
  const state=await setup(page);await open(page);state.guidance=true;state.multi=true;
  await page.getByRole('button',{name:'선석 참조 비교',exact:true}).click();
  const guidance=page.locator('[data-official-guidance]');
  await guidance.locator('[data-guidance-document] > summary').click();
  await expect(guidance).toContainText('2021-01-31');await expect(guidance).toContainText('1년 초과');
  await expect(guidance).toContainText('수로 게시 최소 UKC: 0.7 m');
  await guidance.getByText('근거 문구·위치',{exact:true}).click();
  await expect(guidance).toContainText('<script>Source text remains text.</script>');
  await expect(guidance.locator('script')).toHaveCount(0);
  await page.getByText('가정 조건 비교 (선택)',{exact:true}).click();
  await expect(page.getByLabel('가정 선저 여유',{exact:true})).toHaveValue('');
  await page.getByText('항구·선석 참조 비교',{exact:true}).click();
  await page.getByText('항구·선석 참조 비교',{exact:true}).click();
  await expect(page.getByLabel('참조 항구').locator('option')).toHaveCount(3);
  await page.getByLabel('참조 항구').selectOption('WPI:28190');
  await page.getByRole('button',{name:'선석 참조 비교',exact:true}).click();
  await expect(guidance.locator('[data-guidance-document="gothenburg_draught"]')).toHaveCount(0);
  await guidance.locator('[data-guidance-document] > summary').click();
  await expect(guidance).toContainText('2023-02-07');await expect(guidance).toContainText('현 수심 확인');
  expect(state.errors).toEqual([]);
});

test('historical references and unchecked regional readings stay separate from scenario and port selection', async ({page}) => {
  const state=await setup(page);await open(page);state.quality=true;state.multi=true;
  await page.getByText('가정 조건 비교 (선택)',{exact:true}).click();
  await page.getByRole('button',{name:'선석 참조 비교',exact:true}).click();
  await expect(page.locator('[data-static-reference]')).toContainText('길이 140 m');
  await expect(page.locator('[data-historical-checks]')).toContainText('과거 등록값이 공개 수치 초과');
  await expect(page.locator('[data-environment-context]')).toContainText('-13.4 cm / RH2000');
  await expect(page.locator('[data-environment-context]')).toContainText('O (미검수)');
  await expect(page.locator('[data-environment-context]')).toContainText('2시간 초과');
  await expect(page.getByLabel('가정 풍속',{exact:true})).toHaveValue('');
  await expect(page.getByLabel('가정 선저 여유',{exact:true})).toHaveValue('');
  expect(state.calls.find(c=>c.body).body.scenario).toBeUndefined();
  await page.getByText('등록 후보·유효기간 확인',{exact:true}).click();
  await expect(page.locator('[data-static-reference]')).toContainText('등록 흘수 8.02 m');
  await page.getByText('항구·선석 참조 비교',{exact:true}).click();
  await page.getByText('항구·선석 참조 비교',{exact:true}).click();
  await expect(page.getByLabel('참조 항구').locator('option')).toHaveCount(3);
  await page.getByLabel('참조 항구').selectOption('WPI:28190');
  await page.getByRole('button',{name:'선석 참조 비교',exact:true}).click();
  await expect(page.locator('[data-static-reference]')).toBeVisible();
  await expect(page.locator('[data-environment-context]')).toHaveCount(0);
  expect(state.errors).toEqual([]);
});

test('hypothetical operational inputs preserve explicit zero, clear stale results and reset for another ship', async ({page}) => {
  const state=await setup(page);await open(page);
  await expect(page.locator('main')).toContainText('노르웨이 Kystverket 1건');
  await page.getByText('가정 조건 비교 (선택)',{exact:true}).click();
  await page.getByLabel('가정 풍속',{exact:true}).fill('13');
  await page.getByLabel('가정 예선 수',{exact:true}).fill('0');
  await page.getByLabel('가정 선저 여유',{exact:true}).fill('0.1');
  await page.getByRole('button',{name:'선석 참조 비교',exact:true}).click();
  await expect(page.locator('[data-port-reference-result]')).toBeVisible();
  expect(state.calls.find(c=>c.body).body.scenario).toEqual({wind_m_s:'13',available_tugs:0,ukc_m:'0.1'});
  await page.getByLabel('가정 선저 여유',{exact:true}).fill('0.2');
  await expect(page.locator('[data-port-reference-result]')).toHaveCount(0);
  await page.locator('#ship').selectOption('ship-2');await open(page);
  await page.getByText('가정 조건 비교 (선택)',{exact:true}).click();
  await expect(page.getByLabel('가정 풍속',{exact:true})).toHaveValue('');
  await expect(page.getByLabel('가정 예선 수',{exact:true})).toHaveValue('');
  expect(state.errors).toEqual([]);
});

test('reference panel lazily uses selected ship and session; dated draft and stale values stay qualified', async ({ page }) => {
  const state = await setup(page);
  expect(state.calls).toHaveLength(0);
  await open(page);
  await page.getByLabel('참조 선석').selectOption('WPI:24020:BERTH:510');
  await page.getByRole('button', { name: '선석 참조 비교', exact: true }).click();
  const result = page.locator('[data-port-reference-result]');
  await expect(result).toContainText('6.5 m');
  await expect(result).toContainText('비교 보류');
  await expect(result).toContainText('24시간');
  await expect(result).toContainText('2026-10-01');
  await expect(result).toContainText('이 비교에는 사용하지 않았습니다');
  await result.getByText('원문 조건 확인 · 자동 판정에 미반영', { exact: true }).click();
  await expect(result).toContainText('Tug approval required.');
  const call = state.calls.find(c => c.body);
  expect(call.body).toEqual({ ship: 'ship-1', port_id: 'WPI:24020', berth_id: 'WPI:24020:BERTH:510' });
  expect(call.headers.authorization).toBeUndefined();
  expect(call.headers['x-haedap-token']).toBe('csrf-test');
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  expect(state.errors).toEqual([]);
});

test('changing selected ship or berth discards delayed results; sample ships are blocked', async ({ page }) => {
  const state = await setup(page);
  await open(page);
  let release;
  state.delay = new Promise(resolve => { release = resolve; });
  await page.getByRole('button', { name: '선석 참조 비교', exact: true }).click();
  await expect.poll(() => state.calls.filter(c => c.body).length).toBe(1);
  await page.locator('#ship').selectOption('ship-2');
  release(); state.delay = null;
  await open(page);
  await expect(page.locator('[data-port-reference-result]')).toHaveCount(0);
  await page.getByRole('button', { name: '선석 참조 비교', exact: true }).click();
  await expect(page.locator('[data-port-reference-result]')).toContainText('명시적 연결');
  await page.locator('#ship').selectOption('ship-1');
  await open(page);
  state.delay = new Promise(resolve => { release = resolve; });
  await page.getByRole('button', { name: '선석 참조 비교', exact: true }).click();
  await expect.poll(() => state.calls.filter(c => c.body).length).toBe(3);
  await page.getByLabel('참조 선석').selectOption('WPI:24020:BERTH:812');
  release(); state.delay = null;
  await expect(page.locator('[data-port-reference-result]')).toHaveCount(0);
  await page.locator('#ship').selectOption('sample');
  await open(page);
  await expect(page.getByRole('button', { name: '선석 참조 비교', exact: true })).toBeDisabled();
  expect(state.errors).toEqual([]);
});

test('optional reference API failure stays local to the panel', async ({ page }) => {
  const state = await setup(page); state.error = true;
  await open(page);
  await page.getByRole('button', { name: '선석 참조 비교', exact: true }).click();
  await expect(page.getByRole('alert').filter({ hasText: '참조 자료' })).toContainText('준비 상태');
  await expect(page.locator('#ship')).toBeEnabled();
  await expect(page.locator('[data-port-reference-result]')).toHaveCount(0);
  expect(state.errors).toEqual([]);
});

test('multiple ports require selection, isolate source age and clear results on catalog reload', async ({ page }) => {
  const state = await setup(page); state.multi = true;
  await page.getByText('항구·선석 참조 비교', { exact: true }).click();
  await expect(page.getByLabel('참조 항구').locator('option')).toHaveCount(3);
  await expect(page.getByLabel('참조 항구')).toHaveValue('');
  const compare = page.getByRole('button', { name: '선석 참조 비교', exact: true });
  await expect(compare).toBeDisabled();
  await page.getByLabel('참조 항구').selectOption('WPI:24020');
  await expect(page.locator('main')).toContainText('항구 자료 수집 후 30일');
  let release;
  state.delay = new Promise(resolve => { release = resolve; });
  await compare.click();
  await expect.poll(() => state.calls.filter(c => c.body).length).toBe(1);
  await page.getByLabel('참조 항구').selectOption('WPI:28190');
  await expect(page.locator('main')).not.toContainText('항구 자료 수집 후 30일');
  await expect(page.locator('main')).toContainText('크루즈 선석 자료입니다');
  release(); state.delay = null;
  await expect(page.locator('[data-port-reference-result]')).toHaveCount(0);
  await page.getByLabel('참조 선석').selectOption('WPI:28190:BERTH:LHD');
  await compare.click();
  await expect(page.locator('[data-port-reference-result]')).toContainText('Helsinki');
  const call = state.calls.filter(c => c.body).at(-1);
  expect(call.body.port_id).toBe('WPI:28190');
  await page.getByText('항구·선석 참조 비교', { exact: true }).click();
  await page.getByText('항구·선석 참조 비교', { exact: true }).click();
  await expect(page.getByLabel('참조 항구')).toHaveValue('WPI:28190');
  await expect(page.getByLabel('참조 선석')).toHaveValue('');
  await expect(page.locator('[data-port-reference-result]')).toHaveCount(0);
  expect(state.errors).toEqual([]);
});
