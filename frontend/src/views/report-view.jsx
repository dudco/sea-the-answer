import React from 'react';
import * as helpers from '../components/common';
export function createReportViews(model, views) {
  const noop = () => {};
  const { state, reportTypes, canWrite, isAdmin } = model;
  const { esc, btn, badge, dateText, options, head, notice, empty } = helpers;
  const { contextControls } = views;
  const { statusName } = views;
  function reportsPage() {
    const rows = state.reports.filter((r) =>
      (r.title + ' ' + r.type).toLowerCase().includes(state.reportQuery.toLowerCase()),
    );
    return (
      <>
        {
          <>
            {head(
              '보고서',
              '여러 보고서를 따로 보관하고 검토 상태를 확인하세요.',
              canWrite() ? btn('빈 초안 작성', 'newReport', 'primary', 'plus') : '',
            )}
            {canWrite() ? (
              <details
                className={'card pad mb'}
                {...(!state.reports.length
                  ? {
                      open: true,
                    }
                  : {})}
              >
                <summary>{'운항 기록으로 초안 만들기'}</summary>
                {contextControls()}
                <div className={'actions wrap'}>
                  {btn('Noon Report', 'templateNoon', '', 'ship')}
                  {btn('MRV 검토 보고서', 'templateMrv', '', 'chart')}
                  {btn('작성 중인 초안', 'editReport', 'ghost', 'edit')}
                  {btn('초안 JSON 가져오기', 'importDraft', 'ghost', 'database')}
                </div>
                <p className={'footnote mt'}>
                  {
                    'Noon은 선택 기간의 마지막 하루, MRV는 선택 기간 전체 기록을 사용합니다. 팀 검토용 양식이며 제출 전 필수 항목을 확인해 주세요.'
                  }
                </p>
              </details>
            ) : (
              ''
            )}
          </>
        }
        {
          <>
            <form className={'controls'} id={'reportSearch'}>
              <input
                className={'control'}
                name={'query'}
                aria-label={'보고서 검색'}
                placeholder={'제목 또는 유형 검색'}
                defaultValue={state.reportQuery}
                onChange={noop}
              />
              <button className={'btn'}>{'검색'}</button>
              {btn('새로고침', 'refreshReports', 'ghost', 'refresh')}
            </form>
            <div className={'card'}>
              {rows.length
                ? rows.map((r, __index) => (
                    <React.Fragment key={__index}>
                      {
                        <div className={'docrow'}>
                          <div className={'docicon'}>{'보고'}</div>
                          <div className={'docmain'}>
                            <h3>{r.title}</h3>
                            <p className={'small muted'}>
                              {r.type}
                              {' · '}
                              {dateText(r.updatedAt)}
                              {' · 버전 '}
                              {r.version}
                            </p>
                            <p className={'small'}>
                              {r.body?.from ? `${r.body.from} ~ ${r.body.to}` : ''}
                            </p>
                            {badge(
                              statusName[r.status],
                              r.status === 'approved'
                                ? 'good'
                                : r.status === 'review'
                                  ? 'warn'
                                  : '',
                            )}
                          </div>
                          {btn('열기', 'openReport', 'sm', '', {
                            'data-id': r.id,
                          })}
                        </div>
                      }
                    </React.Fragment>
                  ))
                : empty('저장된 보고서가 없어요', '빈 초안을 작성하거나 운항 기록으로 시작하세요.')}
            </div>
          </>
        }
      </>
    );
  }
  function editorPage() {
    const d = state.draft,
      editable =
        canWrite() && d.status === 'draft' && (!d.owner || d.owner === state.user.id || isAdmin());
    return (
      <>
        {head(
          '보고서 작성',
          '내용과 출처를 확인한 뒤 저장·검토를 진행하세요.',
          btn('목록으로', 'reportList', '', 'arrowback'),
        )}
        {
          <>
            <div className={'controls report-controls'}>
              <div className={'field'}>
                <label htmlFor={'report-type'}>{'보고서 유형'}</label>
                <select
                  id={'report-type'}
                  data-report={'type'}
                  {...(!editable
                    ? {
                        disabled: true,
                      }
                    : {})}
                  value={d.type}
                  onChange={noop}
                >
                  {options(reportTypes)}
                </select>
              </div>
              {badge(statusName[d.status] || '작성 중', d.status === 'approved' ? 'good' : '')}
              <span className={'small muted'}>
                {'버전 '}
                {d.version}
              </span>
              <div className={'actions'}>
                {btn('미리보기', 'previewReport', 'sm', 'file')}
                {canWrite() ? btn('새 초안으로 복사', 'copyReport', 'sm', 'plus') : ''}
              </div>
            </div>
            {state.reportError ? notice(state.reportError, 'warning') : ''}
            {state.conflict ? (
              <div className={'card pad mb'}>
                <h3>{'다른 창에서 변경되었어요.'}</h3>
                <p className={'small muted'}>
                  {'서버 버전 '}
                  {state.conflict.version}
                  {' · '}
                  {dateText(state.conflict.updatedAt)}
                  {'. 편집 중인 내용은 유지됩니다.'}
                </p>
                <div className={'actions mt'}>
                  {btn('서버 내용 확인', 'viewConflict', 'sm')}
                  {btn('내 초안 JSON 보관', 'backupDraft', 'sm')}
                  {btn('확인 후 대체 저장', 'replaceConflict', 'sm')}
                </div>
              </div>
            ) : (
              ''
            )}
            <div className={'report-layout'}>
              <section className={'card'}>
                <label className={'a11y-hidden'} htmlFor={'report-title'}>
                  {'보고서 제목'}
                </label>
                <input
                  id={'report-title'}
                  className={'report-title'}
                  data-report={'title'}
                  maxLength={'120'}
                  placeholder={'보고서 제목'}
                  value={d.title}
                  {...(!editable
                    ? {
                        readOnly: true,
                      }
                    : {})}
                  onChange={noop}
                />
                <label className={'a11y-hidden'} htmlFor={'report-text'}>
                  {'보고서 본문'}
                </label>
                <textarea
                  id={'report-text'}
                  className={'editor'}
                  data-report={'text'}
                  maxLength={'200000'}
                  {...(!editable
                    ? {
                        readOnly: true,
                      }
                    : {})}
                  value={d.text}
                  onChange={noop}
                ></textarea>
                <div className={'report-actions'}>
                  <span id={'saveStatus'} className={'saved-state'}>
                    {state.localFailed
                      ? '브라우저 보관 실패 · 파일로 보관해 주세요'
                      : state.dirty
                        ? '브라우저 임시 보관 · 저장 전'
                        : '저장된 내용'}
                  </span>
                  <div className={'actions wrap'}>
                    {btn('파일 출력', 'downloadReport', '', 'download')}
                    {editable
                      ? btn(
                          state.saving ? '저장 중…' : '저장',
                          'saveReport',
                          'primary',
                          'save',
                          state.saving
                            ? {
                                disabled: true,
                              }
                            : {},
                        )
                      : ''}
                    {editable && d.id
                      ? btn(
                          '검토 요청',
                          'submitReport',
                          '',
                          '',
                          state.dirty
                            ? {
                                disabled: true,
                                title: '먼저 저장해 주세요',
                              }
                            : {},
                        )
                      : ''}
                  </div>
                </div>
              </section>
              <aside>
                <div className={'card pad'}>
                  <h3>{'작성 근거'}</h3>
                  {d.sources.length ? (
                    d.sources.map((id, __index) => {
                      const s = state.docs.find((x) => x.id === id);
                      return (
                        <React.Fragment key={__index}>
                          {
                            <div className={'mt'}>
                              <button className={'source-card'} data-action={'source'} data-id={id}>
                                <strong>{s?.title || '열람 불가 문서'}</strong>
                                <small>{s?.version || ''}</small>
                              </button>
                              {editable
                                ? btn('제거', 'removeSource', 'ghost sm', '', {
                                    'data-id': id,
                                  })
                                : ''}
                            </div>
                          }
                        </React.Fragment>
                      );
                    })
                  ) : (
                    <p className={'small muted mt'}>{'연결된 문서가 없습니다.'}</p>
                  )}
                </div>
                <div className={'mt'}>
                  {notice(
                    d.status === 'approved'
                      ? '담당자가 승인한 버전입니다. 수정하려면 새 초안으로 복사하세요.'
                      : '승인 전 검토용 초안입니다. 누락 항목과 원본 기록을 확인해 주세요.',
                  )}
                </div>
              </aside>
            </div>
          </>
        }
      </>
    );
  }
  return {
    reportsPage,
    editorPage,
  };
}
