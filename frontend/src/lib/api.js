export function createApiClient() {
  // UI와 기존 서버 사이의 유일한 HTTP 경계. API 키는 서버에만 둡니다.
  let token = '';
  let identity = '';
  class ApiError extends Error {
    constructor(message, code, status) {
      super(message);
      this.code = code;
      this.status = status;
    }
  }
  async function request(path, body, retry = true) {
    let response;
    try {
      response = await fetch(path, {
        method: body === undefined ? 'GET' : 'POST',
        cache: 'no-store',
        credentials: 'same-origin',
        headers: {
          ...(path === '/api/health'
            ? {}
            : {
                'X-Haedap-Identity': identity,
              }),
          ...(body === undefined
            ? {}
            : {
                'Content-Type': 'application/json',
                'X-Haedap-Token': token,
              }),
        },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: AbortSignal.timeout(32000),
      });
    } catch (error) {
      throw new ApiError(
        error.name === 'TimeoutError'
          ? '응답 시간이 초과됐어요. 저장 요청이었다면 서버 초안을 먼저 확인해 주세요.'
          : '서버에 연결할 수 없어요. 실행 창을 확인하고 다시 연결해 주세요.',
        'NETWORK',
        0,
      );
    }
    let data;
    try {
      data = await response.json();
    } catch {
      throw new ApiError(
        '서버 응답을 읽을 수 없어요. 서버 주소로 접속했는지 확인해 주세요.',
        'RESPONSE',
        response.status,
      );
    }
    if (!response.ok) {
      if (retry && data.error?.code === 'SESSION_EXPIRED') {
        await health(); // 토큰 검증에서 거부된 요청만 1회 재시도합니다.
        return request(path, body, false);
      }
      throw new ApiError(
        data.error?.message || '요청을 처리하지 못했어요.',
        data.error?.code,
        response.status,
      );
    }
    return data;
  }
  async function health() {
    const data = await request('/api/health', undefined, false);
    token = data.csrfToken;
    identity = data.user?.id || '';
    return data;
  }
  const api = {
    health,
    request,
    documents: () => request('/api/documents'),
    operations: () => request('/api/operations'),
    reports: () => request('/api/reports'),
    ask: (body) => request('/api/ask', body),
    calculate: (body) => request('/api/tools/calculate_emissions', body),
    voyageTime: (body) => request('/api/tools/voyage_time', body),
    saveReport: (body) => request('/api/reports', body),
    report: (id) => request('/api/reports/' + encodeURIComponent(id)),
    change: (kind, payload) =>
      request('/api/changes', {
        kind,
        payload,
      }),
  };
  return api;
}
