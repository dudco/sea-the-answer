import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
const require = createRequire(import.meta.url);
const React = require('react');
const {renderToStaticMarkup} = require('react-dom/server');
const babel = require('next/dist/compiled/babel/bundle');

function load(file, imports) {
  const source = readFileSync(new URL(file, import.meta.url), 'utf8');
  const {code} = babel.core().transformSync(source, {babelrc:false, configFile:false,
    presets:[[babel.presetReact().default, {runtime:'classic'}]], plugins:[babel.pluginTransformModulesCommonjs().default]});
  const module = {exports:{}};
  new Function('require','module','exports', code)(id=>imports[id] || {}, module, module.exports);
  return module.exports;
}

const QuestionWorkflow = load('../src/components/question-workflow.jsx', {
  react: React,
  './ui-language': {UiText:({children})=>children, UiControl:({as='div', ...props})=>React.createElement(as, props)},
  '../workspace/provider': {useWorkspace:()=>({workspace:{state:{answer:null, docs:[], turns:[], busy:false}}})},
  './skill-result': {SkillResult:()=>React.createElement('i', null, 'RESULT')},
}).default;

const answer = {id:'a1', workflow:{missing:[], routing:{method:'model_tools'}, scope:{action:'operations_summary', document_ids:[],
  ships:[{name:'해답 2호'}], periods:[{start:'2026-10-01', end:'2026-10-31'}]},
  results:[{kind:'operations_summary', status:'completed', result:{}}], comparisons:[]}};
const html = props => renderToStaticMarkup(React.createElement(QuestionWorkflow, {answer, ...props}));

test('the answer part shows results without the interpreted scope', () => {
  const main = html({part:'answer'});
  assert.match(main, /RESULT/);
  assert.doesNotMatch(main, /해석한 실행 범위/);
});

test('a chart answer keeps both scope and results behind the toggle', () => {
  assert.doesNotMatch(html({part:'answer', results:false}), /RESULT|해석한 실행 범위/);
  const details = html({part:'details', results:true});
  assert.match(details, /해석한 실행 범위/);
  assert.match(details, /RESULT/);
});
