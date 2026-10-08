import React from 'react';
import * as helpers from '../components/common';
import { sectionsToText } from '../lib/pdf';
export function createForms(model, views) {
  const noop = () => {};
  const { state, isAdmin } = model;
  const { esc, options, notice } = helpers;
  const { roleName } = views;
  const today = () => new Date().toISOString().slice(0, 10);
  function field(name, label, value = '', type = 'text', extra = '') {
    return (
      <div className={'field'}>
        <label htmlFor={'f-' + name}>{label}</label>
        <input
          id={'f-' + name}
          name={name}
          type={type}
          defaultValue={value ?? ''}
          {...extra}
          onChange={noop}
        />
      </div>
    );
  }
  function select(name, label, list, value) {
    return (
      <div className={'field'}>
        <label htmlFor={'f-' + name}>{label}</label>
        <select id={'f-' + name} name={name} defaultValue={value} onChange={noop}>
          {options(list)}
        </select>
      </div>
    );
  }
  function area(name, label, value = '', extra = '') {
    return (
      <div className={'field'}>
        <label htmlFor={'f-' + name}>{label}</label>
        <textarea
          id={'f-' + name}
          name={name}
          {...extra}
          defaultValue={value}
          onChange={noop}
        ></textarea>
      </div>
    );
  }
  function form(id, body, label) {
    return (
      <form id={id} className={'workspace-form'}>
        {body}
        <p className={'inline-error mt'} id={'formError'} role={'alert'}></p>
        <div className={'form-progress small muted'} role={'status'}></div>
        <div className={'actions mt'}>
          <button className={'btn primary'} type={'submit'}>
            {label || '저장'}
          </button>
        </div>
      </form>
    );
  }
  function documentForm(d) {
    const m = d?.meta || {};
    return form(
      'documentForm',
      <>
        <p className={'small muted mb'}>
          {'PDF를 선택하면 페이지별 본문을 읽습니다. 추출 결과와 적용 조건을 확인한 뒤 등록하세요.'}
        </p>
        <div className={'field'}>
          <label htmlFor={'document-file'}>{'PDF 파일 (최대 25MB)'}</label>
          <input
            id={'document-file'}
            name={'file'}
            type={'file'}
            accept={'.pdf,application/pdf'}
            onChange={noop}
          />
        </div>
        <div id={'pdfProgress'} className={'small muted mt'} role={'status'}></div>
        {d?.hasPdf ? (
          <p className={'small muted'}>{'새 파일을 선택하지 않으면 기존 원본 PDF를 유지합니다.'}</p>
        ) : (
          ''
        )}
        <div className={'grid2 mt'}>
          {field('title', '문서명', d?.title || '', 'text', {
            required: true,
            maxLength: '200',
          })}
          {field('version', '버전', d?.version || '1', 'text', {
            required: true,
            maxLength: '100',
          })}
          {select(
            'kind',
            '문서 종류',
            [
              ['onboard', '선내 문서·규정 원문'],
              ['official-summary', '공식 안내 요약'],
              ['sample', '가상 샘플'],
            ],
            d?.kind || 'onboard',
          )}
          {field('issuer', '발행기관', m.issuer, 'text', {
            maxLength: '200',
          })}
          {field('issuedAt', '발행일', m.issuedAt, 'date')}
          {field('revisedAt', '개정일', m.revisedAt, 'date')}
          {select(
            'scope',
            '열람 범위',
            [
              ['all', '누구나 열람'],
              ...(state.user?.role !== 'guest' ? [['operator', '담당자·관리자']] : []),
              ...(isAdmin() ? [['admin', '관리자만']] : []),
            ],
            m.scope || 'all',
          )}
          {select(
            'status',
            '적용 상태',
            [
              ['active', '사용 중'],
              ['retired', '폐기'],
            ],
            m.status || 'active',
          )}
          {field('reference', '조항·참조명', d?.reference || '본문', 'text', {
            required: true,
            maxLength: '200',
          })}
          {field('url', '외부 원문 링크 (선택)', d?.url || '', 'url', {
            placeholder: 'https://…',
          })}
        </div>
        {area('applicability', '적용 조건 (선종·운항구역·기간 등)', m.applicability, {
          rows: '2',
          maxLength: '1000',
        })}
        {area('text', '검색할 본문 · 페이지 구분 유지', d ? sectionsToText(d.sections) : '', {
          required: true,
          rows: '10',
          maxLength: '2200000',
          placeholder:
            'PDF를 선택하거나 본문을 입력하세요. 페이지별로 --- PAGE 1 --- 구분자를 사용할 수 있습니다.',
        })}
        <label className={'checkline mt'}>
          <input name={'checked'} type={'checkbox'} required onChange={noop} />
          {' 추출 본문·페이지와 적용 버전을 확인했습니다.'}
        </label>
      </>,
    );
  }
  function shipForm(s = {}) {
    return form(
      'shipForm',
      <div className={'grid2'}>
        {field('name', '선박명', s.name, 'text', {
          required: true,
          maxLength: '100',
        })}
        {field('type', '선종', s.type, 'text', {
          required: true,
          maxLength: '80',
        })}
        {field('dwt', '재화중량 DWT (t)', s.dwt, 'number', {
          required: true,
          min: '1',
          max: '10000000',
          step: 'any',
        })}
        {field('imo', 'IMO 번호 (선택)', s.imo)}
        {field('from', '출발 항만', s.from)}
        {field('to', '도착 항만', s.to)}
      </div>,
    );
  }
  function recordForm(r = {}) {
    return form(
      'recordForm',
      <>
        <div className={'grid2'}>
          {select(
            'ship',
            '선박',
            state.ships.map((s) => [s.id, s.name]),
            r.ship || state.ship,
          )}
          {field('date', '기록 일자', r.date || today(), 'date', {
            required: true,
          })}
          {field('fuel', '연료 소비량 (t)', r.fuel, 'number', {
            required: true,
            min: '0',
            max: '10000000',
            step: 'any',
          })}
          {field('factor', '배출계수 (t CO₂ / t)', r.factor ?? 3.114, 'number', {
            required: true,
            min: '0.000001',
            max: '10',
            step: 'any',
          })}
          {field('distance', '운항거리 (nm)', r.distance, 'number', {
            required: true,
            min: '0',
            max: '10000000',
            step: 'any',
          })}
          {field('speed', '속력 (kn)', r.speed, 'number', {
            required: true,
            min: '0',
            max: '100',
            step: 'any',
          })}
          {field('fuelType', '연료 종류', r.fuelType, 'text', {
            required: true,
            maxLength: '80',
          })}
          {field('voyage', '항차', r.voyage)}
        </div>
        <p className={'small muted'}>
          {'CO₂는 입력한 연료 × 배출계수로 계산됩니다. 배출계수는 연료 종류에 맞게 확인해 주세요.'}
        </p>
        <details
          className={'mt'}
          {...(r.position || r.draft || r.engineHours
            ? {
                open: true,
              }
            : {})}
        >
          <summary>{'Noon Report 상세 항목'}</summary>
          <div className={'grid2 mt'}>
            {field('position', '위치', r.position)}
            {field('draft', '흘수 (m)', r.draft, 'number', {
              min: '0',
              max: '40',
              step: 'any',
            })}
            {field('weather', '기상', r.weather)}
            {field('engineHours', '기관 운전시간 (h)', r.engineHours, 'number', {
              min: '0',
              max: '24',
              step: 'any',
            })}
          </div>
        </details>
        {area('note', '점검 사유·비고', r.note, {
          rows: '2',
          maxLength: '1000',
          placeholder: '이전 기록보다 연료가 2배 이상이면 점검 사유가 필요합니다.',
        })}
      </>,
    );
  }
  function userForm(u = {}) {
    return form(
      'userForm',
      <>
        <div className={'grid2'}>
          {field('name', '이름', u.name, 'text', {
            required: true,
            maxLength: '80',
          })}
          {field('username', '아이디', u.username, 'text', {
            required: true,
            minLength: '3',
            maxLength: '40',
          })}
          {select('role', '권한', [['admin', '관리자']], u.role || 'admin')}
          {select(
            'active',
            '계정 상태',
            [
              ['true', '활성'],
              ['false', '비활성'],
            ],
            u.active === 0 ? 'false' : 'true',
          )}
        </div>
        {field('password', u.id ? '새 비밀번호 (변경 시 입력)' : '비밀번호', '', 'password', {
          ...(u.id
            ? {}
            : {
                required: true,
              }),
          minLength: '10',
          maxLength: '128',
          autoComplete: 'new-password',
        })}
        <p className={'small muted mt'}>
          {'추가 로그인 계정은 관리자용입니다. 일반 사용자는 계정이 필요하지 않습니다.'}
        </p>
      </>,
      '계정 저장',
    );
  }
  function criterionForm() {
    const r = state.criterion || {},
      docs = state.docs.filter((d) => d.active),
      d = docs.find((d) => d.id === (r.documentId || docs[0]?.id));
    return form(
      'criterionForm',
      <>
        {notice(
          '원문에서 확인한 수치 기준만 입력해 주세요. 비교 결과는 단일 입력 기준에 대한 검토이며 전체 규정 준수 판정은 아닙니다.',
        )}
        <div className={'mt'}>
          {select(
            'documentId',
            '근거 문서',
            docs.map((d) => [d.id, d.title]),
            d?.id,
          )}
          {select(
            'chunkId',
            '근거 구간',
            (d?.sections || []).map((s) => [
              s.id,
              `${s.page ? 'p.' + s.page + ' · ' : ''}${s.heading}`,
            ]),
            r.chunkId,
          )}
          <blockquote className={'quote'} id={'criterionSource'}>
            {d?.sections.find((s) => s.id === r.chunkId)?.text || d?.sections[0]?.text || ''}
          </blockquote>
          {area('quote', '기준이 포함된 원문 구절', r.quote, {
            required: true,
            rows: '3',
            minLength: '8',
          })}
          <div className={'grid2'}>
            {select(
              'metric',
              '비교 지표',
              [
                ['fuel', '기간 연료 합계 (t)'],
                ['emission', '기간 CO₂ 합계 (t)'],
                ['intensity', '기간 단순 집약도'],
                ['speed', '일별 속력 평균 (kn)'],
              ],
              r.metric || 'emission',
            )}
            {select(
              'operator',
              '조건',
              [
                ['lte', '이하'],
                ['gte', '이상'],
              ],
              r.operator || 'lte',
            )}
            {field('limit', '기준값', r.limit, 'number', {
              required: true,
              min: '0',
              max: '1000000000000',
              step: 'any',
            })}
          </div>
          <label className={'checkline mt'}>
            <input type={'checkbox'} name={'confirmed'} required onChange={noop} />
            {' 이 선박·기간·단위에 적용되는 기준임을 확인했습니다.'}
          </label>
        </div>
      </>,
      '기준 적용',
    );
  }
  return {
    field,
    select,
    area,
    form,
    documentForm,
    shipForm,
    recordForm,
    userForm,
    criterionForm,
  };
}
