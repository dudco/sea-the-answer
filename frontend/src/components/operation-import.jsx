'use client';
import React,{useEffect,useRef,useState} from 'react';
const labels={daily:'일별 운항 기록',source_files:'출처',vessels:'원본 선박',annual_reports:'MRV 보고기간 자료',synthetic_noon:'Synthetic Noon (가상)',synthetic_voyages:'가상 항차',quality_issues:'품질 정보',capacity_candidates:'DWT 후보 (참고)'};
const endpoint='/api/operations/import/';
function encode(buffer){const bytes=new Uint8Array(buffer);let binary='';for(let i=0;i<bytes.length;i+=16384)binary+=String.fromCharCode(...bytes.subarray(i,i+16384));return btoa(binary);}
export default function OperationImport({api,ships,onSaved}) {
 const [files,setFiles]=useState([]),[busy,setBusy]=useState(false),[progress,setProgress]=useState('');
 const [preview,setPreview]=useState(null),[error,setError]=useState(''),[database,setDatabase]=useState(null),[reference,setReference]=useState(null);
 const [mapExisting,setMapExisting]=useState(true),[includeReference,setIncludeReference]=useState(true),[replace,setReplace]=useState(false);
 const active=useRef(null),sequence=useRef(0);
 useEffect(()=>()=>{sequence.current++;const id=active.current;if(id)api.request(endpoint+'cancel',{id}).catch(()=>{});},[api]);
 async function clear(){const id=active.current;active.current=null;if(id)await api.request(endpoint+'cancel',{id}).catch(()=>{});}
 async function validate(event){
  event.preventDefault();event.stopPropagation();const seq=++sequence.current;
  setBusy(true);setError('');setPreview(null);setDatabase(null);setReference(null);setReplace(false);
  try{
   await clear();if(seq!==sequence.current)return;if(!files.length)throw Error('가져올 CSV·JSON·ZIP 파일을 선택해 주세요.');
   const opened=await api.request(endpoint+'start',{files:files.map(f=>({name:f.name,size:f.size}))});
   if(seq!==sequence.current){await api.request(endpoint+'cancel',{id:opened.id}).catch(()=>{});return;}
   active.current=opened.id;const total=files.reduce((n,f)=>n+f.size,0);let sent=0;
   for(let i=0;i<files.length;i++)for(let offset=0;offset<files[i].size;offset+=opened.chunk_bytes){
    if(seq!==sequence.current)return;
    const buffer=await files[i].slice(offset,offset+opened.chunk_bytes).arrayBuffer();
    await api.request(endpoint+'chunk',{id:opened.id,index:i,offset,data:encode(buffer)});
    sent+=buffer.byteLength;setProgress(`파일 전송 ${Math.round(sent/total*100)}% · ${files[i].name}`);
   }
   setProgress('서식·출처·중복·현재 DB를 검증하고 있습니다.');
   const result=await api.request(endpoint+'preview',{id:opened.id});if(seq===sequence.current)setPreview(result);
  }catch(e){if(seq===sequence.current)setError(e.message);}
  finally{if(seq===sequence.current){setBusy(false);setProgress('');}}
 }
 async function commit(event){
  event.preventDefault();event.stopPropagation();if(!preview||!active.current)return;
  const seq=sequence.current;setBusy(true);setError('');let dbResult=database;
  try{
   const body={id:active.current,preview_hash:preview.preview_hash};
   if(preview.has_database&&!dbResult){setProgress('DB에 등록하고 있습니다.');dbResult=await api.request(endpoint+'commit',{...body,map_existing:mapExisting});if(seq!==sequence.current)return;setDatabase(dbResult);await onSaved();}
   if(preview.reference&&includeReference&&!reference){setProgress('참조 파일을 연결하고 있습니다.');const r=await api.request(endpoint+'reference',{...body,replace});if(seq!==sequence.current)return;setReference(r);}
   setProgress('선택한 자료의 등록을 완료했습니다.');
  }catch(e){if(seq===sequence.current)setError((dbResult?'DB 등록은 완료됐습니다. 참조 파일 연결 결과를 확인하세요. ':'')+e.message);}
  finally{if(seq===sequence.current)setBusy(false);}
 }
 return <form id="csvForm" onSubmit={validate} onChange={e=>e.stopPropagation()} onInput={e=>e.stopPropagation()}>
  <p>일별 운항 CSV, 준비된 MRV·Noon CSV 묶음, DWT 후보 CSV, AIS·항만 JSON 또는 반입 ZIP을 선택하세요.</p>
  <p className="small muted">연간 자료는 MRV 테이블에, 일별 기록은 운항 기록에 저장합니다. 원시 MRV 열과 단위는 추측하지 않습니다. 최대 16개·합계 128MiB입니다.</p>
  <p className="small">등록 선박: {ships.length?ships.map(s=>`${s.name}: ${s.id}`).join(' · '):'없음. MRV 원본은 적재할 수 있으며 앱에서 조회할 실제 선박은 이후 등록·연결해야 합니다.'}</p>
  <button type="button" className="btn sm" data-action="csvTemplate">일별 CSV 서식 받기</button>
  <input aria-label="운항 자료 파일" name="file" className="file-input" type="file" accept=".csv,.json,.zip,text/csv,application/json,application/zip" multiple required disabled={busy}
   onChange={e=>{e.stopPropagation();sequence.current++;setFiles([...e.target.files]);setPreview(null);setError('');setDatabase(null);setReference(null);clear();}} />
  <button type="submit" className="btn primary mt" disabled={busy}>파일 검증</button>
  {progress&&<p role="status">{progress}</p>}{error&&<p role="alert" className="notice warning">{error}</p>}
  {preview&&<section className="mt" data-import-preview><p>{preview.notice}</p>
   {!!preview.datasets.length&&<><div className="table-wrap"><table><thead><tr><th>자료 종류</th><th>행 수</th><th>신규</th><th>동일 자료</th></tr></thead><tbody>{preview.datasets.map(row=><tr key={row.kind}><td>{labels[row.kind]||row.kind}</td><td>{row.rows}</td><td>{row.new}</td><td>{row.unchanged}</td></tr>)}</tbody></table></div><p className="small muted">연료 t · CO₂ t · 거리 nm · 속력 kn. 연간/일별·실제/가상 구분을 원본대로 유지합니다.</p></>}
   {preview.has_database&&<label className="inline mt"><input type="checkbox" checked={mapExisting} disabled={busy||!!database} onChange={e=>setMapExisting(e.target.checked)} /> 동일 IMO의 유일한 기존 실제 앱 선박 연결 ({preview.existing_ship_links}건 예상)</label>}
   {preview.reference&&<div className="card pad mt"><h3>AIS·항만 참조 파일</h3><p>항구 {preview.reference.ports?.length??0}개 · 수집 시각과 레코드 나이는 원래 값으로 유지됩니다.</p>
    <label><input type="checkbox" checked={includeReference} disabled={busy||!!reference} onChange={e=>setIncludeReference(e.target.checked)} /> 참조 파일도 연결</label>
    {preview.reference_previous_sha256&&<label className="inline mt"><input type="checkbox" checked={replace} disabled={busy||!!reference} onChange={e=>setReplace(e.target.checked)} /> 기존 참조 파일을 보존한 후 교체</label>}
   </div>}
   {preview.ignored_files>0&&<p className="small muted">반입 묶음의 안내·실행 파일 등 {preview.ignored_files}개는 실행하거나 등록하지 않습니다.</p>}
   <button className="btn primary mt" type="button" data-action="commitCsv" disabled={busy||(!preview.has_database&&!includeReference)||(!!database&&(!preview.reference||!includeReference||!!reference))||(!preview.has_database&&!!reference)} onClick={commit}>등록</button>
   {database&&<p role="status" data-import-database>DB 등록 완료 · 신규 {database.datasets.reduce((n,r)=>n+r.new,0)}행 · 기존 동일 자료 보존 · 선박 연결 {database.linked_ships}건</p>}
   {reference&&<p role="status" data-import-reference>참조 파일 연결 완료 · 원래 출처·수집 시각 유지</p>}
  </section>}
 </form>;
}
