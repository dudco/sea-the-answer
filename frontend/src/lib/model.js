// One workspace model per React provider; never shared between requests.
export function createModel() {
  const reportTypes = ['규정 검토', '일일 운항', '배출량 검토', '종합 검토'];
  const keys = {
    draft: 'haedap-workspace-draft-v2',
  };
  function readLocal(k, fallback = null) {
    try {
      return JSON.parse(localStorage.getItem(k)) ?? fallback;
    } catch {
      return fallback;
    }
  }
  function writeLocal(k, v) {
    try {
      localStorage.setItem(k, JSON.stringify(v));
      return true;
    } catch {
      return false;
    }
  }
  function blankDraft() {
    return {
      id: '',
      title: '',
      type: '규정 검토',
      text: '',
      sources: [],
      version: 0,
      status: 'draft',
      body: {},
    };
  }
  function validateDraft(raw) {
    const r = raw?.report || raw;
    if (
      !r ||
      typeof r.title !== 'string' ||
      r.title.length > 120 ||
      typeof r.text !== 'string' ||
      r.text.length > 200000 ||
      !reportTypes.includes(r.type) ||
      !Array.isArray(r.sources) ||
      r.sources.some((s) => typeof s !== 'string')
    )
      throw Error('보고서 파일의 제목·본문·유형·근거 형식을 확인해 주세요.');
    return {
      ...blankDraft(),
      ...r,
      sources: [...new Set(r.sources)],
    };
  }
  const state = {
    page: 'chat',
    menu: false,
    health: null,
    user: null,
    ready: false,
    connecting: true,
    loginOpen: false,
    authError: '',
    connectionError: '',
    docs: [],
    ships: [],
    operationRecords: [],
    reports: [],
    users: [],
    logs: [],
    changes: [],
    backups: [],
    history: [],
    adminTab: 'connection',
    adminLoading: false,
    adminError: '',
    logFilter: 'all',
    question: '',
    answer: null,
    busy: false,
    slow: false,
    askError: '',
    askSequence: 0,
    filter: 'all',
    language: 'auto',
    mode: 'extractive',
    includeCalc: false,
    task: 'auto',
    criterion: null,
    docQuery: '',
    docStatus: 'active',
    docKind: 'all',
    doc: '',
    section: '',
    docBack: 'docs',
    docView: 'text',
    ship: '',
    from: '2026-09-22',
    to: '2026-09-28',
    tab: 'overview',
    compare: [],
    metric: 'fuel',
    calcInputs: {
      fuel: '',
      factor: 3.114,
      dwt: '',
      distance: '',
    },
    calc: null,
    calcBusy: false,
    calcError: '',
    calcSequence: 0,
    timeInputs: {
      start: '2026-09-18T00:00',
      end: '2026-09-18T01:00',
      before: 720,
      after: -720,
    },
    timeResult: null,
    timeBusy: false,
    timeError: '',
    timeSequence: 0,
    draft: blankDraft(),
    draftRevision: 0,
    dirty: false,
    localFailed: false,
    saving: false,
    reportError: '',
    conflict: null,
    reportQuery: '',
  };
  const canWrite = () => ['admin', 'operator', 'guest'].includes(state.user?.role);
  const isAdmin = () => state.user?.role === 'admin';
  function currentShip() {
    return (
      state.ships.find((s) => s.id === state.ship) ||
      state.ships[0] || {
        id: '',
        name: '선박 미선택',
        dwt: 0,
      }
    );
  }
  function records(ship = state.ship) {
    return state.operationRecords.filter(
      (r) => r.ship === ship && r.date >= state.from && r.date <= state.to,
    );
  }
  function metrics(ship = state.ship) {
    const rows = records(ship),
      fuel = rows.reduce((a, r) => a + r.fuel, 0),
      distance = rows.reduce((a, r) => a + r.distance, 0),
      co2 = rows.reduce((a, r) => a + r.fuel * r.factor, 0);
    return {
      fuel,
      distance,
      co2,
      count: rows.length,
      anomalies: rows.filter((r) => r.note && !r.sample).length,
    };
  }
  function draftKey() {
    return keys.draft + '-' + state.user.id;
  }
  function persistDraft() {
    state.draftRevision++;
    state.dirty = true;
    state.localFailed = !writeLocal(draftKey(), state.draft);
  }
  function snapshotDraft() {
    return JSON.stringify(state.draft);
  }
  return {
    reportTypes,
    keys,
    readLocal,
    writeLocal,
    validateDraft,
    blankDraft,
    state,
    persistDraft,
    snapshotDraft,
    metrics,
    records,
    currentShip,
    draftKey,
    canWrite,
    isAdmin,
  };
}
