import test from 'node:test';
import assert from 'node:assert/strict';
import {parseCsv,toCsv} from '../src/lib/csv.js';
import {textToSections,sectionsToText} from '../src/lib/pdf.js';
test('CSV preserves quoted commas, Unicode, newlines and numeric units; rejects incomplete rows',()=>{
 const row={ship:'vessel-1',date:'2026-09-28',fuel:10,factor:3.114,distance:200,speed:11,fuelType:'연료, 검증',note:'첫 줄\n둘째 "줄"'};
 const r=parseCsv(toCsv([row]))[0];assert.equal(r.fuel,10);assert.equal(r.fuelType,row.fuelType);assert.equal(r.note,row.note);assert.equal(r.draft,null);
 assert.throws(()=>parseCsv('ship,date\nvessel-1,2026-09-28'));assert.throws(()=>parseCsv('ship,date,fuel,factor,distance,speed,fuelType\n"unclosed'));
});
test('PDF text editing retains page boundaries and long-page chunk order',()=>{
 const sections=[{page:1,text:'연료 0.50% / 3.114',heading:'A'},{page:2,text:'둘째 페이지',heading:'B'}];
 const out=textToSections(sectionsToText(sections),'제1조');assert.deepEqual(out.map(s=>s.page),[1,2]);assert.equal(out[0].text,sections[0].text);
 const long=textToSections('--- PAGE 5 ---\n'+'가'.repeat(40000),'제2조');assert.equal(long.length,3);assert.ok(long.every(s=>s.page===5&&s.text.length<=19000));assert.equal(long.map(s=>s.text).join('').length,40000);
});
