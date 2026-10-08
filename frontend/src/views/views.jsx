import React from 'react';
import * as helpers from '../components/common';
export function createMainViews(model, views) {
  const noop = () => {};
  const { state, canWrite, isAdmin } = model;
  const { esc, I, btn, badge, n, options, head, notice, empty, docKind, safeUrl } = helpers;
  const { operationsPage, contextControls } = views;
  const { reportsPage, editorPage } = views;
  const { authPage, adminPage, operationAnswer, roleName } = views;
  const pageNames = {
    chat: '통합 질문',
    docs: '문서',
    document: '문서 내용',
    operations: '운항 정보',
    reports: '보고서',
    editor: '보고서 작성',
    admin: '관리',
  };
  function sourceCard(id, section = '') {
    const d = state.docs.find((d) => d.id === id);
    return d ? (
      <button className={'source-card'} data-action={'source'} data-id={id} data-section={section}>
        <strong>
          {I('file')} {d.title}
        </strong>
        <small>
          {d.version}
          {' · '}
          {d.active ? '사용 중' : d.meta?.status === 'retired' ? '폐기' : '이전 버전'}
        </small>
      </button>
    ) : (
      <p className={'unknown-source'}>{'열람할 수 없는 근거입니다.'}</p>
    );
  }
  function composer() {
    return (
      <form id={'askForm'} className={'composer'}>
        <textarea
          id={'question'}
          aria-label={'질문 입력'}
          placeholder={'규정의 근거, 운항 기록이나 필요한 보고서를 질문해 보세요.'}
          maxLength={'2000'}
          required
          value={state.question}
          onChange={noop}
        ></textarea>
        <div className={'composer-bottom'}>
          <div className={'query-controls'}>
            <select aria-label={'질문 종류'} data-field={'task'} value={state.task} onChange={noop}>
              {options([
                ['auto', '작업 자동 선택'],
                ['documents', '문서 검색'],
                ['operations', '운항 분석'],
                ['integrated', '통합 확인'],
                ['report', '보고서'],
              ])}
            </select>
            <select
              aria-label={'답변 언어'}
              data-field={'language'}
              value={state.language}
              onChange={noop}
            >
              {options([
                ['auto', '언어 자동'],
                ['ko', '한국어'],
                ['en', 'English'],
              ])}
            </select>
            <select aria-label={'답변 방식'} data-field={'mode'} value={state.mode} onChange={noop}>
              {options([
                ['extractive', '근거 문단 보기'],
                ...(state.health?.llmConfigured ? [['llm', 'AI 답변']] : []),
              ])}
            </select>
            <select
              aria-label={'검색 범위'}
              data-field={'filter'}
              value={state.filter}
              onChange={noop}
            >
              {options([
                ['all', '모든 문서'],
                ['imo', '공식 안내 요약'],
                ['manual', '선내·샘플'],
              ])}
            </select>
          </div>
          <button
            className={'sendbtn'}
            type={'submit'}
            aria-label={'질문 보내기'}
            {...(state.busy || !state.ready
              ? {
                  disabled: true,
                }
              : {})}
          >
            {I('send')}
          </button>
        </div>
      </form>
    );
  }
  function answerView(a) {
    if (!a) return '';
    const en = a.language === 'en',
      sources = [...new Set(a.evidence.map((e) => e.document_id))];
    return (
      <article className={'card answer'}>
        <div className={'inline wrap'}>
          <h2>
            {en
              ? 'Answer & evidence'
              : a.status === 'insufficient_evidence'
                ? '답변 근거를 확인해 주세요'
                : '답변과 확인 근거'}
          </h2>
          {badge(a.generation === 'llm' ? 'AI 초안' : '문서 검색', 'teal')}
        </div>
        <p className={'small muted'}>{a.notice}</p>
        {a.warnings.length
          ? notice(
              en
                ? 'AI unavailable. Showing source excerpts.'
                : 'AI 답변을 생성하지 못해 원문 근거를 표시합니다.',
              'warning',
            )
          : ''}
        {a.statements.map((s, __index) => {
          const e = a.evidence.find((e) => e.id === s.chunkId);
          return (
            <React.Fragment key={__index}>
              {
                <p>
                  {s.text}{' '}
                  {e ? (
                    <button
                      className={'citation'}
                      data-action={'source'}
                      data-id={e.document_id}
                      data-section={e.id}
                    >
                      {'['}
                      {sources.indexOf(e.document_id) + 1}
                      {e.page ? ' · p.' + e.page : ''}
                      {']'}
                    </button>
                  ) : (
                    ''
                  )}
                </p>
              }
            </React.Fragment>
          );
        })}
        {!a.evidence.length
          ? notice(
              en
                ? 'Insufficient document evidence. Ask the responsible officer.'
                : '문서 근거가 부족합니다. 관련 문서를 등록하거나 담당자에게 확인해 주세요.',
              'warning',
            )
          : ''}
        {operationAnswer(a)}
        {a.toolRuns.map((t, __index) => (
          <React.Fragment key={__index}>
            {
              <div className={'card pad mt'}>
                {'CO₂ '}
                {n(t.emission, 3)}
                {' t · 집약도 '}
                {n(t.intensity, 3)}
                {' gCO₂/(DWT·nm)'}
              </div>
            }
          </React.Fragment>
        ))}
        {sources.length ? (
          <div className={'answer-sources'}>
            <h3>{en ? 'Sources' : '확인한 근거'}</h3>
            {sources.map((id, __index) => (
              <React.Fragment key={__index}>
                {sourceCard(id, a.evidence.find((e) => e.document_id === id)?.id)}
              </React.Fragment>
            ))}
          </div>
        ) : (
          ''
        )}
        <div className={'answer-actions'}>
          {canWrite() && (a.statements.length || a.operations?.count || a.toolRuns.length)
            ? btn(en ? 'Add to report' : '보고서에 담기', 'answerReport', 'primary', 'edit')
            : ''}
          {a.reportSuggested && canWrite()
            ? btn(en ? 'Choose report template' : '보고서 양식 선택', 'reportList', '', 'file')
            : ''}
        </div>
      </article>
    );
  }
  function chatPage() {
    const toolbar = (
        <div className={'chat-toolbar'}>
          <span className={'muted small'}>{'문서의 근거와 운항 정보를 한곳에서'}</span>
          <div className={'actions'}>
            {state.answer ? btn('새 질문', 'newQuestion', 'ghost sm', 'plus') : ''}
            {btn('질의 이력', 'history', 'ghost sm', 'clock')}
          </div>
        </div>
      ),
      context = (
        <details
          className={'query-context'}
          {...(state.ship
            ? {
                open: true,
              }
            : {})}
        >
          <summary>
            {'운항 분석 대상 '}
            {state.ships.find((s) => s.id === state.ship)?.name
              ? '· ' + state.ships.find((s) => s.id === state.ship).name
              : '선택'}
          </summary>
          {contextControls(true)}
          {state.criterion ? (
            <p className={'small muted'}>
              {'비교 기준이 설정됨 '}
              {btn('기준 해제', 'clearCriterion', 'ghost sm')}
            </p>
          ) : (
            ''
          )}
        </details>
      );
    if (!state.answer && !state.busy && !state.askError)
      return (
        <>
          {toolbar}
          {
            <div className={'chat-intro'}>
              <div className={'hero-symbol'}>{I('spark')}</div>
              <h1>
                {'오늘 운항에 필요한 정보,'}
                <br />
                <span>{'무엇이 궁금하신가요?'}</span>
              </h1>
              <p>{'규정의 근거를 찾고, 운항 기록을 확인하고, 보고서로 정리하세요.'}</p>
              {context}
              {composer()}
              <div className={'suggest-label'}>{'이런 질문으로 시작해 보세요'}</div>
              <div className={'grid3'}>
                {[
                  ['file', '연료 황 함유량 기준을 알려줘', '문서 검색 · 근거 확인'],
                  ['chart', '선택한 선박의 연료 추이를 분석해줘', '운항 조회 · 지표 확인'],
                  ['edit', '선택한 기간의 Noon 보고서를 준비해줘', '기록 조회 · 보고서 연결'],
                ].map(([i, q, sub], __index) => (
                  <React.Fragment key={__index}>
                    {
                      <button className={'suggest'} data-question={q}>
                        {I(i)}
                        <strong>{q}</strong>
                        <small>{sub}</small>
                      </button>
                    }
                  </React.Fragment>
                ))}
              </div>
              <p className={'footnote center mt'}>
                {'근거 문단은 원문 언어로 표시됩니다. AI 답변은 설정된 경우 사용할 수 있습니다.'}
              </p>
            </div>
          }
        </>
      );
    return (
      <>
        {toolbar}
        {
          <div className={'chat-content'}>
            <div className={'question-bubble'}>
              {state.answer?.question || state.pendingQuestion || state.question}
            </div>
            {state.busy ? (
              <div className={'thinking'} role={'status'}>
                <span className={'spinner'}></span>
                <div>
                  <strong>{'문서와 데이터를 확인하고 있어요'}</strong>
                  {state.slow ? (
                    <p className={'progress-extra'}>
                      {'15초 이상 소요되고 있어요. 처리가 계속 진행 중입니다.'}
                    </p>
                  ) : (
                    ''
                  )}
                </div>
              </div>
            ) : (
              ''
            )}
            {state.askError
              ? notice(
                  <>
                    {state.askError + ' '}
                    {btn('다시 시도', 'retryQuestion', 'sm')}
                  </>,
                  'warning',
                )
              : ''}
            {answerView(state.answer)}
            <div className={'mt'}>
              {context}
              {composer()}
            </div>
          </div>
        }
      </>
    );
  }
  function docsPage() {
    const q = state.docQuery.trim().toLowerCase(),
      docs = state.docs
        .filter(
          (d) =>
            (state.docStatus === 'all' ||
              (state.docStatus === 'active' ? !!d.active : !d.active)) &&
            (state.docKind === 'all' || d.kind === state.docKind),
        )
        .filter((d) =>
          (d.title + ' ' + d.reference + ' ' + d.sections.map((s) => s.text).join(' '))
            .toLowerCase()
            .includes(q),
        );
    return (
      <>
        {head(
          '문서',
          '문서를 등록하고 버전과 적용 조건을 확인하세요.',
          <>
            {btn('새로고침', 'refreshDocuments', '', 'refresh')}
            {isAdmin() ? btn('문서 등록', 'newDocument', 'primary', 'plus') : ''}
          </>,
        )}
        {
          <>
            <form className={'controls'} id={'docSearch'}>
              <div className={'searchbox'}>
                {I('search')}
                <input
                  className={'control'}
                  name={'query'}
                  defaultValue={state.docQuery}
                  placeholder={'문서명, 조항 또는 본문 검색'}
                  aria-label={'문서 검색어'}
                  onChange={noop}
                />
              </div>
              <select
                className={'control'}
                aria-label={'문서 유형'}
                data-field={'docKind'}
                value={state.docKind}
                onChange={noop}
              >
                {options([
                  ['all', '모든 유형'],
                  ['official-summary', '공식 안내 요약'],
                  ['onboard', '선내 문서'],
                  ['sample', '가상 샘플'],
                ])}
              </select>
              <select
                className={'control'}
                aria-label={'문서 상태'}
                data-field={'docStatus'}
                value={state.docStatus}
                onChange={noop}
              >
                {options([
                  ['active', '사용 중'],
                  ['all', '모든 버전'],
                  ['old', '이전·폐기'],
                ])}
              </select>
              <button className={'btn'}>{'검색'}</button>
            </form>
            <div className={'sectiontitle'}>
              <h3>
                {'문서 '}
                {docs.length}
                {'개'}
              </h3>
              <span className={'small muted'}>{'열람 가능한 문서만 표시'}</span>
            </div>
            <div className={'card'}>
              {docs.length
                ? docs.map((d, __index) => (
                    <React.Fragment key={__index}>
                      {
                        <div className={'docrow'}>
                          <div className={'docicon'}>{I('file')}</div>
                          <div className={'docmain'}>
                            <button className={'tabletitle'} data-doc={d.id}>
                              <h3>{d.title}</h3>
                            </button>
                            <div className={'inline wrap'}>
                              {badge(docKind(d))}
                              {badge(
                                d.active
                                  ? '사용 중'
                                  : d.meta.status === 'retired'
                                    ? '폐기'
                                    : '이전 버전',
                                d.active ? 'good' : 'warn',
                              )}
                              {d.hasPdf ? badge('PDF') : ''}
                            </div>
                            <div className={'docmeta'}>
                              <span>{d.version}</span>
                              <span>{d.meta.issuer || '발행기관 미입력'}</span>
                              <span>
                                {'개정 '}
                                {d.meta.revisedAt || '미입력'}
                              </span>
                            </div>
                          </div>
                          {btn('열기', 'document', 'sm', '', {
                            'data-id': d.id,
                          })}
                        </div>
                      }
                    </React.Fragment>
                  ))
                : empty('검색 결과가 없어요', '검색어와 필터를 확인해 주세요.')}
            </div>
            <p className={'footnote mt'}>
              {
                '‘사용 중’은 내부에서 선택한 적용 버전입니다. 외부 원문의 최신성은 발행일·개정일과 함께 확인하세요.'
              }
            </p>
          </>
        }
      </>
    );
  }
  function documentPage() {
    const d = state.docs.find((d) => d.id === state.doc);
    if (!d)
      return empty(
        '문서를 찾을 수 없어요',
        '열람 권한 또는 문서 상태를 확인해 주세요.',
        btn('문서 목록', 'backDocs'),
      );
    const url = safeUrl(d.url),
      section = d.sections.find((s) => s.id === state.section),
      page = section?.page || 1;
    return (
      <>
        {head(
          d.title,
          d.reference,
          <>
            {btn('돌아가기', 'backDocument', '', 'arrowback')}
            {isAdmin() ? (
              <>
                {btn('개정·정보 수정', 'editDocument', '', 'edit', {
                  'data-id': d.id,
                })}
                {d.active
                  ? btn('삭제', 'deleteDocument', 'ghost', '', {
                      'data-id': d.id,
                    })
                  : ''}
              </>
            ) : (
              ''
            )}
          </>,
        )}
        {
          <>
            {!d.active
              ? notice('이전 버전 또는 폐기된 문서입니다. 적용 여부를 확인해 주세요.', 'warning')
              : ''}
            <div className={'docviewer'}>
              <div className={'paper-shell'}>
                <div className={'actions mb'}>
                  {btn(
                    '저장 텍스트',
                    'documentText',
                    state.docView === 'text' ? 'primary sm' : 'sm',
                  )}
                  {d.hasPdf
                    ? btn('PDF 원문', 'documentPdf', state.docView === 'pdf' ? 'primary sm' : 'sm')
                    : ''}
                </div>
                {state.docView === 'pdf' && d.hasPdf ? (
                  <iframe
                    className={'pdf-frame'}
                    title={d.title + ' 원문 PDF'}
                    src={'/api/documents/' + encodeURIComponent(d.id) + '/pdf#page=' + page}
                  ></iframe>
                ) : (
                  <article className={'paper'}>
                    <div className={'doc-kicker'}>{'HAEDAP / DOCUMENT'}</div>
                    <h2>{d.title}</h2>
                    {d.sections.map((s, __index) => (
                      <React.Fragment key={__index}>
                        {
                          <section
                            id={'chunk-' + s.id}
                            className={state.section === s.id ? 'highlight' : ''}
                          >
                            <h3>
                              {s.heading}{' '}
                              <small className={'muted'}>
                                {s.page ? 'p.' + s.page : '페이지 미지정'}
                              </small>
                            </h3>
                            <p>{s.text}</p>
                          </section>
                        }
                      </React.Fragment>
                    ))}
                  </article>
                )}
              </div>
              <aside className={'card pad'}>
                <h3>{'문서 정보'}</h3>
                {[
                  ['버전', d.version],
                  ['발행기관', d.meta.issuer],
                  ['발행일', d.meta.issuedAt],
                  ['개정일', d.meta.revisedAt],
                  ['적용 조건', d.meta.applicability],
                  ['출처 조항', d.reference],
                  [
                    '열람 범위',
                    {
                      all: '누구나 열람',
                      operator: '담당자·관리자',
                      admin: '관리자',
                    }[d.meta.scope],
                  ],
                ].map(([k, v], __index) => (
                  <React.Fragment key={__index}>
                    {
                      <div className={'metaitem'}>
                        <label>{k}</label>
                        <p>{v || '미입력'}</p>
                      </div>
                    }
                  </React.Fragment>
                ))}
                {url ? (
                  <a className={'btn mt'} href={url} target={'_blank'} rel={'noopener noreferrer'}>
                    {'외부 원문'}
                  </a>
                ) : (
                  ''
                )}
                <div className={'divider'}></div>
                <h3>{'저장된 버전'}</h3>
                {state.docs
                  .filter((x) => x.logical_id === d.logical_id)
                  .map((x, __index) => (
                    <React.Fragment key={__index}>
                      {
                        <button className={'history-item'} data-doc={x.id}>
                          {x.version}{' '}
                          {badge(
                            x.active ? '사용 중' : x.meta.status === 'retired' ? '폐기' : '이전',
                          )}
                        </button>
                      }
                    </React.Fragment>
                  ))}
              </aside>
            </div>
          </>
        }
      </>
    );
  }
  function shell(content) {
    if (state.loginOpen) return authPage();
    if (!state.user)
      return (
        <main className={'login-layout'}>
          <section className={'login-card'}>
            <h1>{'해답'}</h1>
            <p role={'status'}>{state.connectionError || '작업공간에 연결하고 있어요…'}</p>
            {state.connectionError ? btn('다시 연결', 'reconnect', 'mt') : ''}
          </section>
        </main>
      );
    const page = state.page;
    return (
      <div className={'app'}>
        <button
          className={'menu-scrim ' + (state.menu ? 'visible' : '')}
          data-action={'menu'}
          aria-label={'메뉴 닫기'}
        ></button>
        <aside className={'sidebar ' + (state.menu ? 'open' : '')} aria-label={'주 메뉴'}>
          <div className={'brand'}>
            <div className={'brandmark'}>{I('ship')}</div>
            <div>
              <strong>{'해답'}</strong>
              <small>{'SEA THE ANSWER'}</small>
            </div>
          </div>
          <div className={'navlabel'}>{'WORKSPACE'}</div>
          {[
            ['chat', 'chat', '통합 질문'],
            ['docs', 'file', '문서'],
            ['operations', 'chart', '운항 정보'],
            ['reports', 'edit', '보고서'],
          ].map(([p, i, l], __index) => (
            <React.Fragment key={__index}>
              {
                <button
                  className={
                    'navitem ' +
                    (page === p ||
                    (p === 'docs' && page === 'document') ||
                    (p === 'reports' && page === 'editor')
                      ? 'active'
                      : '')
                  }
                  data-nav={p}
                >
                  {I(i)}
                  <span>{l}</span>
                </button>
              }
            </React.Fragment>
          ))}
          {isAdmin() ? (
            <div className={'adminnav'}>
              <div className={'navlabel'}>{'WORKSPACE SETTINGS'}</div>
              <button
                className={'navitem ' + (page === 'admin' ? 'active' : '')}
                data-nav={'admin'}
              >
                {I('settings')}
                <span>{'관리'}</span>
              </button>
            </div>
          ) : (
            ''
          )}
          <div className={'sidebar-bottom'}>
            <div className={'local-note'}>
              <b>{'선박 운항 업무지원'}</b>
              <br />
              {'내부 문서와 운항 정보를 한곳에서'}
            </div>
            <div className={'account'}>
              <div className={'avatar'}>{state.user.name.slice(0, 1)}</div>
              <div>
                <span className={'small'}>{state.user.name}</span>
                <div className={'account-note'}>{roleName[state.user.role]}</div>
              </div>
            </div>
            <button className={'sidebar-logout'} data-action={isAdmin() ? 'logout' : 'openLogin'}>
              {isAdmin() ? '로그아웃' : '관리자 로그인'}
            </button>
          </div>
        </aside>
        <div className={'layout'}>
          <header className={'topbar'}>
            <div className={'crumb'}>
              <button
                className={'iconbtn mobile-menu'}
                data-action={'menu'}
                aria-label={'메뉴 열기'}
              >
                {I('menu')}
              </button>
              <span>{'워크스페이스'}</span>
              {I('chevron')}
              <strong>{pageNames[page]}</strong>
            </div>
            <div className={'top-right'}>
              <span className={'connection ' + (state.ready ? '' : 'off')}>
                {state.ready ? '서버 연결됨' : '연결 확인'}
              </span>
              <button className={'iconbtn'} data-action={'help'} aria-label={'사용 안내'}>
                {I('info')}
              </button>
            </div>
          </header>
          <main id={'main'} className={'body'} tabIndex={'-1'}>
            {state.connectionError
              ? notice(
                  <>
                    {state.connectionError + ' '}
                    {btn('다시 연결', 'reconnect', 'sm')}
                  </>,
                  'warning',
                )
              : ''}
            {content}
          </main>
        </div>
      </div>
    );
  }
  return {
    pageNames,
    sourceCard,
    chatPage,
    docsPage,
    documentPage,
    shell,
  };
}
