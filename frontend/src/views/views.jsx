import {UiControl} from '../components/ui-language';
import React from 'react';
import {UiText} from '../components/ui-language';
import { SkillResult } from '../components/skill-result';
import { AnswerPresentation } from '../components/answer-presentation';
import { validatedPresentation } from '../lib/answer-presentation';
import SkillsPanel from '../components/skills-panel';
import * as helpers from '../components/common';
import NavigationAnswer from '../components/navigation-answer';
import QuestionWorkflow from '../components/question-workflow';
import DatasetStatus from '../components/dataset-status';
import {generationFailureMessage} from '../lib/generation-failure';
export function createMainViews(model, views) {
  const noop = () => {};
  const { state, canWrite, isAdmin } = model;
  const { esc, I, btn, badge, n, options, head, notice, empty, docKind, safeUrl } = helpers;
  const { operationsPage } = views;
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
          <UiText>{d.active ? '사용 중' : d.meta?.status === 'retired' ? '폐기' : '이전 버전'}</UiText>
        </small>
      </button>
    ) : (
      <p className={'unknown-source'}><UiText>{'열람할 수 없는 근거입니다.'}</UiText></p>
    );
  }
  function composer() {
    return (
      <><form id={'askForm'} className={'composer'}>
        <UiControl as="textarea"
          id={'question'}
          aria-label={'질문 입력'}
          placeholder={'규정의 근거, 운항 기록이나 필요한 보고서를 질문해 보세요.'}
          maxLength={'2000'}
          required
          value={state.question}
          onChange={noop}
        ></UiControl>
        <div className={'composer-bottom'}>
          <div className={'query-controls'}>
            <UiControl as="select" aria-label="답변 방식" data-field="mode" value={state.mode} onChange={noop}>
              {state.health?.llmConfigured && <option value="llm"><UiText>{'AI 답변'}</UiText></option>}
              <option value="extractive"><UiText>{'원문 발췌'}</UiText></option>
            </UiControl>
            <UiControl as="select"
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
            </UiControl>
          </div>
          <UiControl as="button"
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
          </UiControl>
        </div>
      </form></>
    );
  }
  function answerView(a) {
    if (!a) return '';
    const en = a.language === 'en',
      sources = [...new Set(a.evidence.map((e) => e.document_id))],
      presentation = validatedPresentation(a.presentation, a.evidence);
    return (
      <article className={'card answer'} data-answer-id={a.id}>
        <div className={'inline wrap'}>
          <h2>
            <UiText>{en
              ? 'Answer & evidence'
              : a.status === 'insufficient_evidence'
                ? '답변 근거를 확인해 주세요'
                : '답변과 확인 근거'}</UiText>
          </h2>
          {badge(a.dataStatus ? '자료 등록 현황' : a.routing?.route==='clarify' ? '질문 확인' : a.navigation?.kind==='catalog-status' ? 'AIS 자료 현황' : a.navigation ? '항구 참조 비교' : a.workflow ? '업무 조회·계산' : a.skill ? '업무 스킬' : a.generation === 'llm' ? 'AI 초안' : '문서 검색', 'teal')}
        </div>
        <p className={'small muted'}>{a.notice}</p>
        {/* Only model warnings mean the AI answer failed; e.g. OPERATIONS_CONTEXT_REQUIRED has its own notice. */}
        <UiText>{a.warnings.some((w) => w === 'MODEL_FAILED_EXTRACTIVE_FALLBACK' || w === 'MODEL_NOT_CONFIGURED')
          ? notice(
              generationFailureMessage(a.generationFailure?.code,en) || (en
                ? 'AI unavailable. Showing source excerpts.'
                : 'AI 답변을 생성하지 못해 원문 근거를 표시합니다.'),
              'warning',
            )
          : ''}</UiText>
        {!a.navigation && <>
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
        <AnswerPresentation answer={a} presentation={presentation} />
        <UiText>{!a.evidence.length && !a.workflow && !a.skill && !a.operations?.count && presentation?.source !== 'operations'
          ? notice(
              en
                ? 'Insufficient document evidence. Ask the responsible officer.'
                : '문서 근거가 부족합니다. 관련 문서를 등록하거나 담당자에게 확인해 주세요.',
              'warning',
            )
          : ''}</UiText>
        {operationAnswer(a)}
        {a.skill && <><h3>{a.skill.name}</h3><SkillResult answer={a} /></>}
        {a.toolRuns.map((t, __index) => (
          <React.Fragment key={__index}>
            {
              <div className={'card pad mt'}>
                {'CO₂ '}
                {n(t.emission, 3)}
                <UiText>{' t · 집약도 '}</UiText>
                {n(t.intensity, 3)}
                {' gCO₂/(DWT·nm)'}
              </div>
            }
          </React.Fragment>
        ))}
        {sources.length ? (
          <div className={'answer-sources'}>
            <h3><UiText>{en ? 'Sources' : '확인한 근거'}</UiText></h3>
            {sources.map((id, __index) => (
              <React.Fragment key={__index}>
                {sourceCard(id, a.evidence.find((e) => e.document_id === id)?.id)}
              </React.Fragment>
            ))}
          </div>
        ) : (
          ''
        )}
        </>}
        {a.navigation && <NavigationAnswer answer={a} />}
        {a.dataStatus && <DatasetStatus value={a.dataStatus} />}
        {a.workflow && <QuestionWorkflow answer={a} />}
        <div className={'answer-actions'}>
          <UiText>{canWrite() && (a.statements.length || a.operations?.count || a.toolRuns.length)
            ? btn(en ? 'Add to report' : '보고서에 담기', 'answerReport', 'primary', 'edit')
            : ''}</UiText>
          <UiText>{a.reportSuggested && canWrite()
            ? btn(en ? 'Choose report template' : '보고서 양식 선택', 'reportList', '', 'file')
            : ''}</UiText>
        </div>
        <SkillsPanel group="evaluation" targetAnswerId={a.id} />
      </article>
    );
  }
  function chatPage() {
    const toolbar = (
        <div className={'chat-toolbar'}>
          <div className={'actions'}>
            <UiText>{state.turns.length || state.busy ? btn('새 질문', 'newQuestion', 'ghost sm', 'plus') : ''}</UiText>
            {btn('질의 이력', 'history', 'ghost sm', 'clock')}
          </div>
        </div>
      ),
      context = state.criterion ? <p className="small muted">
        <UiText>{'비교 기준이 설정됨 '}</UiText>{btn('기준 해제', 'clearCriterion', 'ghost sm')}
      </p> : null;
    if (!state.turns.length && !state.busy && !state.askError)
      return (
        <>
          {toolbar}
          {
            <div className={'chat-intro'}>
              <div className={'hero-symbol'}>{I('spark')}</div>
              <h1>
                <UiText>{'오늘 운항에 필요한 정보,'}</UiText>
                <br />
                <span><UiText>{'무엇이 궁금하신가요?'}</UiText></span>
              </h1>
              <p><UiText>{'규정의 근거를 찾고, 운항 기록을 확인하고, 보고서로 정리하세요.'}</UiText></p>
              {context}
              {composer()}
              <div className={'suggest-label'}><UiText>{'이런 질문으로 시작해 보세요'}</UiText></div>
              <div className={'grid3'}>
                {[
                  ['file', '연료 황 함유량 기준을 알려줘', '문서 검색 · 근거 확인'],
                  ['chart', '우리 배의 연료 추이를 보여줘', '운항 조회 · 지표 확인'],
                  ['edit', '지난달 운항 실적을 요약해줘', '기록 조회 · 보고서 연결'],
                ].map(([i, q, sub], __index) => (
                  <React.Fragment key={__index}>
                    {
                      <button className={'suggest'} data-question={q}>
                        {I(i)}
                        <strong><UiText>{q}</UiText></strong>
                        <small><UiText>{sub}</UiText></small>
                      </button>
                    }
                  </React.Fragment>
                ))}
              </div>
              <p className={'footnote center mt'}>
                <UiText>{'근거 문단은 원문 언어로 표시됩니다. AI 답변은 설정된 경우 사용할 수 있습니다.'}</UiText>
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
            {state.turns.map(turn => <section className="chat-turn" key={turn.id}>
              <div className="question-bubble">{turn.question}</div>
              <UiText>{turn.answer ? answerView(turn.answer) : notice('근거가 삭제되었거나 현재 열람 권한이 없어 답변을 표시하지 않습니다.', 'warning')}</UiText>
            </section>)}
            {(state.busy || state.askError) && <div className="question-bubble">{state.pendingQuestion}</div>}
            {state.busy ? (
              <div className={'thinking'} role={'status'}>
                <span className={'spinner'}></span>
                <div>
                  <strong><UiText>{'문서와 데이터를 확인하고 있어요'}</UiText></strong>
                  {state.slow ? (
                    <p className={'progress-extra'}>
                      <UiText>{'15초 이상 소요되고 있어요. 처리가 계속 진행 중입니다.'}</UiText>
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
            <UiText>{isAdmin() ? btn('문서 등록', 'newDocument', 'primary', 'plus') : ''}</UiText>
          </>,
        )}
        {
          <>
            <form className={'controls'} id={'docSearch'}>
              <div className={'searchbox'}>
                {I('search')}
                <UiControl as="input"
                  className={'control'}
                  name={'query'}
                  defaultValue={state.docQuery}
                  placeholder={'문서명, 조항 또는 본문 검색'}
                  aria-label={'문서 검색어'}
                  onChange={noop}
                />
              </div>
              <UiControl as="select"
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
              </UiControl>
              <UiControl as="select"
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
              </UiControl>
              <button className={'btn'}><UiText>{'검색'}</UiText></button>
            </form>
            <div className={'sectiontitle'}>
              <h3>
                <UiText>{'문서 '}</UiText>
                {docs.length}
                <UiText>{'개'}</UiText>
              </h3>
              <span className={'small muted'}><UiText>{'열람 가능한 문서만 표시'}</UiText></span>
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
                              <span>{d.meta.issuer || <UiText>발행기관 미입력</UiText>}</span>
                              <span>
                                <UiText>{'개정 '}</UiText>
                                {d.meta.revisedAt || <UiText>미입력</UiText>}
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
              <UiText>{
                '‘사용 중’은 내부에서 선택한 적용 버전입니다. 외부 원문의 최신성은 발행일·개정일과 함께 확인하세요.'
              }</UiText>
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
          <span>{d.title}</span>,
          <span>{d.reference}</span>,
          <>
            {btn('돌아가기', 'backDocument', '', 'arrowback')}
            {isAdmin() ? (
              <>
                {btn('개정·정보 수정', 'editDocument', '', 'edit', {
                  'data-id': d.id,
                })}
                <UiText>{d.active
                  ? btn('삭제', 'deleteDocument', 'danger-outline', '', {
                      'data-id': d.id,
                    })
                  : ''}</UiText>
              </>
            ) : (
              ''
            )}
          </>,
        )}
        {
          <>
            <UiText>{!d.active
              ? notice('이전 버전 또는 폐기된 문서입니다. 적용 여부를 확인해 주세요.', 'warning')
              : ''}</UiText>
            <div className={'docviewer'}>
              <div className={'paper-shell'}>
                <div className={'actions mb'}>
                  {btn(
                    '저장 텍스트',
                    'documentText',
                    state.docView === 'text' ? 'primary sm' : 'sm',
                  )}
                  <UiText>{d.hasPdf
                    ? btn('PDF 원문', 'documentPdf', state.docView === 'pdf' ? 'primary sm' : 'sm')
                    : ''}</UiText>
                </div>
                {state.docView === 'pdf' && d.hasPdf ? (
                  <UiControl as="iframe"
                    className={'pdf-frame'}
                    title={d.title + ' 원문 PDF'}
                    src={'/api/documents/' + encodeURIComponent(d.id) + '/pdf#page=' + page}
                  ></UiControl>
                ) : (
                  <article className={'paper'}>
                    <div className={'doc-kicker'}>{'SEA THE ANSWER / DOCUMENT'}</div>
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
                                <UiText>{s.page ? 'p.' + s.page : '페이지 미지정'}</UiText>
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
                <h3><UiText>{'문서 정보'}</UiText></h3>
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
                      all: '로그인 사용자',
                      operator: '담당자·관리자',
                      admin: '관리자',
                    }[d.meta.scope],
                  ],
                ].map(([k, v], __index) => (
                  <React.Fragment key={__index}>
                    {
                      <div className={'metaitem'}>
                        <label><UiText>{k}</UiText></label>
                        <p>{v || <UiText>미입력</UiText>}</p>
                      </div>
                    }
                  </React.Fragment>
                ))}
                {url ? (
                  <a className={'btn mt'} href={url} target={'_blank'} rel={'noopener noreferrer'}>
                    <UiText>{'외부 원문'}</UiText>
                  </a>
                ) : (
                  ''
                )}
                <div className={'divider'}></div>
                <h3><UiText>{'저장된 버전'}</UiText></h3>
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
        {d.active && <SkillsPanel group="document" documentId={d.id} />}
      </>
    );
  }
  function shell(content) {
    if (state.loginOpen || state.passwordOpen || state.user?.must_change_password || state.user?.role === 'guest') return authPage();
    if (!state.user)
      return (
        <main className={'login-layout'}>
          <section className={'login-card'}>
            <h1><UiText>{'해답'}</UiText></h1>
            <p role={'status'}>{state.connectionError || '작업공간에 연결하고 있어요…'}</p>
            <UiText>{state.connectionError ? btn('다시 연결', 'reconnect', 'mt') : ''}</UiText>
          </section>
        </main>
      );
    const page = state.page;
    return (
      <div className={'app'}>
        <UiControl as="button"
          className={'menu-scrim ' + (state.menu ? 'visible' : '')}
          data-action={'menu'}
          aria-label={'메뉴 닫기'}
        ></UiControl>
        <UiControl as="aside" className={'sidebar ' + (state.menu ? 'open' : '')} aria-label={'주 메뉴'}>
          <UiControl as="button" type={'button'} className={'brand' + (state.uiLanguage === 'en' ? ' brand-english' : '')} data-action={'home'} aria-label={'SEA THE ANSWER · 통합 질문으로 이동'}>
            <div className={'brandmark'}>{I('ship')}</div>
            <div>
              {state.uiLanguage === 'en' ? (
                <strong className="brand-title-en">SEA<br />THE ANSWER</strong>
              ) : <><strong>해답</strong><small>SEA THE ANSWER</small></>}
            </div>
          </UiControl>
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
                  <span><UiText>{l}</UiText></span>
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
                <span><UiText>{'관리'}</UiText></span>
              </button>
            </div>
          ) : (
            ''
          )}
          <div className={'sidebar-bottom'}>
            <div className={'account'}>
              <div className={'avatar'}>{state.user.name.slice(0, 1)}</div>
              <div>
                <span className={'small'}><UiText>{state.user.role === 'guest' ? '일반 사용자' : state.user.name}</UiText></span>
                <div className={'account-note'}><UiText>{roleName[state.user.role]}</UiText></div>
              </div>
            </div>
            <div className="account-actions">
              <button className={'sidebar-logout'} data-action={'changePassword'}><UiText>{"비밀번호 변경"}</UiText></button>
              <button className={'sidebar-logout'} data-action={'logout'}>
                <UiText>{'로그아웃'}</UiText>
              </button>
              <button className="sidebar-logout language-button" data-action="selectLanguage">Select Language</button>
            </div>
          </div>
        </UiControl>
        <div className={'layout'}>
          <header className={'topbar'}>
            <div className={'crumb'}>
              <UiControl as="button"
                className={'iconbtn mobile-menu'}
                data-action={'menu'}
                aria-label={'메뉴 열기'}
              >
                {I('menu')}
              </UiControl>
              <span><UiText>{'워크스페이스'}</UiText></span>
              {I('chevron')}
              <strong><UiText>{pageNames[page]}</UiText></strong>
            </div>
            <div className={'top-right'}>
              <span className={'connection ' + (state.ready ? '' : 'off')}>
                <UiText>{state.ready ? '서버 연결됨' : '연결 확인'}</UiText>
              </span>
              <UiControl as="button" className={'iconbtn'} data-action={'help'} aria-label={'사용 안내'}>
                {I('info')}
              </UiControl>
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
