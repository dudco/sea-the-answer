// Small local workspace services. No external service is required for CRUD/auth/backups.
import { randomUUID, randomBytes, scryptSync, timingSafeEqual, createHash } from 'node:crypto';
import { mkdirSync, readdirSync, readFileSync, writeFileSync, renameSync } from 'node:fs';
import { join } from 'node:path';
import { importDocuments, listDocuments, saveReport, getReport } from './db.mjs';
import { prepareDocument, tokens } from './knowledge.mjs';
import { requireValue, string, number, object } from './validation.mjs';

const now = () => new Date().toISOString();
const parse = value => JSON.parse(value);
const optional = (v, max=1000) => typeof v === 'string' ? v.trim().slice(0,max) : '';
export const isAdmin = u => u?.role === 'admin';
export function permit(user, roles=['admin']) { requireValue(user && roles.includes(user.role), '이 작업을 수행할 권한이 없습니다.', 'FORBIDDEN', 403); }
export function date(value, label='일자') { const s=string(value,label,10); requireValue(/^\d{4}-\d{2}-\d{2}$/.test(s)&&Number.isFinite(Date.parse(s))&&new Date(s).toISOString().slice(0,10)===s, label+'를 확인해 주세요.'); return s; }
export function transaction(db, fn) { const own=!db.isTransaction; if(own)db.exec('BEGIN IMMEDIATE');try{const v=fn();if(own)db.exec('COMMIT');return v;}catch(e){if(own)db.exec('ROLLBACK');throw e;} }
export function initializeWorkspace(db) {
 db.exec(`CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,username TEXT UNIQUE NOT NULL,name TEXT NOT NULL,role TEXT NOT NULL,password TEXT NOT NULL,active INTEGER NOT NULL,version INTEGER NOT NULL);
 CREATE TABLE IF NOT EXISTS document_meta(id TEXT PRIMARY KEY,body TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS document_files(id TEXT PRIMARY KEY,name TEXT NOT NULL,base64 TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS chunk_pages(id TEXT PRIMARY KEY,page INTEGER);
 CREATE TABLE IF NOT EXISTS ships(id TEXT PRIMARY KEY,body TEXT NOT NULL,version INTEGER NOT NULL);
 CREATE TABLE IF NOT EXISTS operations(id TEXT PRIMARY KEY,ship TEXT NOT NULL,date TEXT NOT NULL,body TEXT NOT NULL,version INTEGER NOT NULL,UNIQUE(ship,date));
 CREATE TABLE IF NOT EXISTS report_meta(id TEXT PRIMARY KEY,owner TEXT NOT NULL,status TEXT NOT NULL,body TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS audit(id TEXT PRIMARY KEY,at TEXT NOT NULL,actor TEXT NOT NULL,category TEXT NOT NULL,action TEXT NOT NULL,target TEXT NOT NULL,detail TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS query_owner(id TEXT PRIMARY KEY,owner TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS changes(id TEXT PRIMARY KEY,at TEXT NOT NULL,actor TEXT NOT NULL,kind TEXT NOT NULL,payload TEXT NOT NULL,status TEXT NOT NULL,reviewer TEXT,reviewed_at TEXT,note TEXT);
 CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);`);
 db.prepare("INSERT OR IGNORE INTO settings VALUES ('schema','2')").run();
 db.prepare("INSERT OR IGNORE INTO settings VALUES ('autoBackup','daily')").run();
}
export function audit(db,user,category,action,target,detail={}) { db.prepare('INSERT INTO audit VALUES (?,?,?,?,?,?,?)').run(randomUUID(),now(),user?.name||'시스템',category,action,String(target||''),JSON.stringify(detail)); }
export function publicUser(row) { if(!row)return null;const {password,...u}=row;return u; }
function hashPassword(password,minimum=10) { string(password,'비밀번호',128);requireValue(password.length>=minimum,`비밀번호는 ${minimum}자 이상 입력해 주세요.`);const salt=randomBytes(16).toString('hex');return salt+':'+scryptSync(password,salt,64).toString('hex'); }
// Apply the requested fixed administrator once, including databases from older versions.
export function initializePublicAccess(db) {
 if(db.prepare("SELECT value FROM settings WHERE key='publicAccessV1'").get())return;
 transaction(db,()=>{
  const old=db.prepare("SELECT * FROM users WHERE username='admin'").get(),id=old?.id||randomUUID();
  db.prepare("INSERT INTO users VALUES (?,'admin',?,'admin',?,1,?) ON CONFLICT(username) DO UPDATE SET role='admin',password=excluded.password,active=1,version=excluded.version").run(id,old?.name||'관리자',hashPassword('1234',4),(old?.version||0)+1);
  for(const q of db.prepare('SELECT id FROM queries').all())db.prepare('INSERT OR IGNORE INTO query_owner VALUES (?,?)').run(q.id,id);
  for(const r of db.prepare('SELECT id FROM reports').all())db.prepare("INSERT OR IGNORE INTO report_meta VALUES (?,?,'draft','{}')").run(r.id,id);
  db.prepare("INSERT INTO settings VALUES ('publicAccessV1','1')").run();
  audit(db,{name:'시스템'},'users','일반 접근 및 기본 관리자 설정','admin');
 });
}
export function authenticate(db,username,password) {
 const row=db.prepare('SELECT * FROM users WHERE username=? AND active=1').get(optional(username,80));
 const [salt,hash]=(row?.password||'00000000000000000000000000000000:'+Buffer.alloc(64).toString('hex')).split(':');
 const digest=scryptSync(String(password||'').slice(0,128),salt,64);
 requireValue(row && timingSafeEqual(digest,Buffer.from(hash,'hex')),'아이디 또는 비밀번호가 올바르지 않습니다.','LOGIN_FAILED',401);
 audit(db,row,'auth','로그인',row.username);return publicUser(row);
}
export function saveUser(db,actor,raw,setup=false) {
 object(raw);if(!setup)permit(actor);else requireValue(!db.prepare('SELECT 1 FROM users LIMIT 1').get(),'초기 설정이 이미 완료되었습니다.');
 const username=string(raw.username,'아이디',40);requireValue(/^[a-zA-Z0-9._-]{3,40}$/.test(username),'아이디는 영문·숫자·점·밑줄·하이픈 3~40자입니다.');
 const role=setup?'admin':raw.role;requireValue(['admin','operator','viewer'].includes(role),'권한을 확인해 주세요.');
 const old=raw.id?db.prepare('SELECT * FROM users WHERE id=?').get(raw.id):null;
 if(raw.id)requireValue(old && old.version===raw.version,'사용자 정보가 바뀌었습니다. 새로고침해 주세요.','VERSION_CONFLICT',409);
 requireValue(old?.username!=='admin','기본 관리자 admin 계정은 고정되어 있습니다.','FORBIDDEN',403);
 const active=raw.active===false?0:1;
 if(old?.role==='admin' && (!active||role!=='admin'))requireValue(db.prepare("SELECT count(*) n FROM users WHERE role='admin' AND active=1 AND id!=?").get(old.id).n>0,'최소 한 명의 활성 관리자가 필요합니다.');
 const password=raw.password?hashPassword(raw.password):old?.password;requireValue(password,'비밀번호를 입력해 주세요.');
 const id=old?.id||randomUUID(),name=string(raw.name,'이름',80),version=(old?.version||0)+1;
 requireValue(!db.prepare('SELECT id FROM users WHERE username=? AND id!=?').get(username,id),'이미 사용 중인 아이디입니다.');
 db.prepare('INSERT INTO users VALUES (?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET username=excluded.username,name=excluded.name,role=excluded.role,password=excluded.password,active=excluded.active,version=excluded.version').run(id,username,name,role,password,active,version);
 if(setup) { // Preserve the old shared draft, associating it with the first local administrator.
   for(const q of db.prepare('SELECT id FROM queries').all())db.prepare('INSERT OR IGNORE INTO query_owner VALUES (?,?)').run(q.id,id);
   for(const r of db.prepare('SELECT id FROM reports').all()) db.prepare("INSERT OR IGNORE INTO report_meta VALUES (?,?,'draft','{}')").run(r.id,id);
 }
 audit(db,actor||{name},'users',setup?'관리자 초기 설정':old?'사용자 변경':'사용자 등록',username,{role,active});return publicUser(db.prepare('SELECT * FROM users WHERE id=?').get(id));
}
export function docMeta(db,id) { const r=db.prepare('SELECT body FROM document_meta WHERE id=?').get(id);return r?parse(r.body):{scope:'all',status:'active',issuer:'',issuedAt:'',revisedAt:'',applicability:'',revision:0}; }
export function canReadDoc(db,user,id) { const m=docMeta(db,id);return m.status!=='deleted' && (isAdmin(user)||m.scope==='all'||(m.scope==='operator'&&user?.role==='operator')); }
export function workspaceDocuments(db,user) {
 return listDocuments(db).filter(d=>canReadDoc(db,user,d.id)).map(d=>{const meta=docMeta(db,d.id);return {...d,meta,currentRevision:!!d.active,active:d.active&&meta.status==='active',hasPdf:!!db.prepare('SELECT 1 FROM document_files WHERE id=?').get(d.id),sections:d.sections.map(s=>({...s,page:db.prepare('SELECT page FROM chunk_pages WHERE id=?').get(s.id)?.page||null}))};});
}
export function allowedDocs(db,user) { return workspaceDocuments(db,user).filter(d=>d.active).map(d=>d.id); }
export function enrichEvidence(db,evidence) {return evidence.map(e=>({...e,page:db.prepare('SELECT page FROM chunk_pages WHERE id=?').get(e.id)?.page||null,meta:docMeta(db,e.document_id)}));}
function validateDocumentPayload(db,p) {
 object(p);const doc=prepareDocument(p.document);const meta=p.meta||{};
 requireValue(['all','operator','admin'].includes(meta.scope||'all'),'문서 열람 권한을 확인해 주세요.');
 requireValue(['active','retired'].includes(meta.status||'active'),'적용 상태를 확인해 주세요.');
 for(const k of ['issuedAt','revisedAt'])if(meta[k])date(meta[k],k==='issuedAt'?'발행일':'개정일');
 const current=db.prepare('SELECT id FROM documents WHERE logical_id=? AND active=1').get(doc.id);
 if(p.expectedId!==undefined)requireValue((current?.id||'')===p.expectedId,'문서가 변경되었습니다. 새로고침 후 다시 등록해 주세요.','VERSION_CONFLICT',409);
 if(p.expectedMetaRevision!==undefined&&current)requireValue(docMeta(db,current.id).revision===p.expectedMetaRevision,'문서 정보가 변경되었습니다. 다시 열어 주세요.','VERSION_CONFLICT',409);
 if(p.file){requireValue(typeof p.file.base64==='string'&&p.file.base64.length<36*1024*1024,'PDF는 25MB 이하만 지원합니다.');const bytes=Buffer.from(p.file.base64,'base64');requireValue(bytes.length<=25*1024*1024 && bytes.subarray(0,5).toString()==='%PDF-','올바른 PDF 파일이 필요합니다.');}
 return {doc,meta:{scope:meta.scope||'all',status:meta.status||'active',issuer:optional(meta.issuer,200),issuedAt:meta.issuedAt||'',revisedAt:meta.revisedAt||'',applicability:optional(meta.applicability),revision:Date.now()}};
}
export function validateShip(p) {object(p);return {id:p.id||randomUUID(),name:string(p.name,'선박명',100),type:string(p.type,'선종',80),dwt:number(p.dwt,'DWT',1,1e7),imo:optional(p.imo,30),from:optional(p.from,100),to:optional(p.to,100),sample:!!p.sample};}
export function ships(db) {return db.prepare('SELECT * FROM ships ORDER BY rowid').all().map(r=>({...parse(r.body),version:r.version}));}
export function operations(db) {return db.prepare('SELECT * FROM operations ORDER BY date,id').all().map(r=>({...parse(r.body),version:r.version}));}
export function validateOperation(db,p,checkPrevious=true) {
 object(p);const ship=string(p.ship,'선박',80);requireValue(db.prepare('SELECT 1 FROM ships WHERE id=?').get(ship),'등록된 선박을 선택해 주세요.');
 const row={id:p.id||randomUUID(),ship,date:date(p.date),fuel:number(p.fuel,'연료(t)',0,1e7),factor:number(p.factor,'배출계수',0.000001,10),distance:number(p.distance,'거리(nm)',0,1e7),speed:number(p.speed,'속력(kn)',0,100),position:optional(p.position,100),voyage:optional(p.voyage,100),fuelType:string(p.fuelType,'연료 종류',80),weather:optional(p.weather,200),draft:p.draft===null||p.draft===undefined||p.draft===''?null:number(p.draft,'흘수(m)',0,40),engineHours:p.engineHours===null||p.engineHours===undefined||p.engineHours===''?null:number(p.engineHours,'기관 운전시간(h)',0,24),note:optional(p.note),sample:!!p.sample};
 const old=db.prepare('SELECT version FROM operations WHERE id=?').get(row.id);
 requireValue((old?.version||0)===(p.version||0),'운항 기록이 변경되었습니다. 다시 열어 주세요.','VERSION_CONFLICT',409);
 requireValue(!db.prepare('SELECT 1 FROM operations WHERE ship=? AND date=? AND id!=?').get(ship,row.date,row.id),'동일 선박·일자의 기록이 이미 있습니다. 해당 기록을 수정해 주세요.');
 const prev=db.prepare('SELECT body FROM operations WHERE ship=? AND date<? ORDER BY date DESC LIMIT 1').get(ship,row.date);
 if(checkPrevious && prev && row.fuel>Math.max(1,parse(prev.body).fuel)*2)requireValue(row.note.length>=5,'이전 기록보다 연료가 2배 이상입니다. 점검 사유를 5자 이상 기록해 주세요.','ANOMALY');
 return {...row,version:old?.version||0};
}
export function validateRows(db,rows) {
 requireValue(Array.isArray(rows)&&rows.length>0&&rows.length<=1000,'1~1,000개의 운항 기록이 필요합니다.');
 const errors=[],seen=new Set();const valid=rows.map((p,i)=>{try{const r=validateOperation(db,p,false);const key=r.ship+':'+r.date;requireValue(!seen.has(key),'파일 안에 선박·일자가 중복되어 있습니다.');seen.add(key);return r;}catch(e){errors.push({row:i+1,message:e.message});return null;}});
 for(let i=0;i<valid.length;i++){const r=valid[i];if(!r)continue;const previous=[...operations(db).filter(p=>!valid.some(x=>x?.id===p.id)),...valid.filter(Boolean)].filter(p=>p.ship===r.ship&&p.date<r.date).sort((a,b)=>b.date.localeCompare(a.date))[0];if(previous&&r.fuel>Math.max(1,previous.fuel)*2&&r.note.length<5)errors.push({row:i+1,message:'이전 기록보다 연료가 2배 이상입니다. 점검 사유를 5자 이상 기록해 주세요.'});}
 return {rows:valid,errors};
}
function assertExpected(row,p) {requireValue(row && row.version===p.version,'대상이 변경되었거나 삭제되었습니다. 새로고침해 주세요.','VERSION_CONFLICT',409);}
function applyChange(db,user,kind,p) {
 if(kind==='document.save') {
  const {doc,meta}=validateDocumentPayload(db,p);importDocuments(db,[p.document]);
  // A document's new visibility applies to all its historical revisions, too.
  for(const old of db.prepare('SELECT id FROM documents WHERE logical_id=?').all(doc.id)){const previous=docMeta(db,old.id);previous.scope=meta.scope;db.prepare('INSERT OR REPLACE INTO document_meta VALUES (?,?)').run(old.id,JSON.stringify(previous));}
  db.prepare('INSERT OR REPLACE INTO document_meta VALUES (?,?)').run(doc.revisionId,JSON.stringify(meta));
  for(const c of doc.chunks)db.prepare('INSERT OR REPLACE INTO chunk_pages VALUES (?,?)').run(c.id,c.page||null);
  if(p.file)db.prepare('INSERT OR REPLACE INTO document_files VALUES (?,?,?)').run(doc.revisionId,optional(p.file.name,200),p.file.base64);
  else if(p.expectedId){const old=db.prepare('SELECT * FROM document_files WHERE id=?').get(p.expectedId);if(old)db.prepare('INSERT OR REPLACE INTO document_files VALUES (?,?,?)').run(doc.revisionId,old.name,old.base64);}
  return {id:doc.revisionId};
 }
 if(kind==='document.delete') {const row=db.prepare('SELECT * FROM documents WHERE id=?').get(p.id);requireValue(row,'문서를 찾을 수 없습니다.');requireValue(row.active===1,'이미 이전 버전이거나 삭제된 문서입니다.','VERSION_CONFLICT',409);for(const d of db.prepare('SELECT id FROM documents WHERE logical_id=?').all(row.logical_id)){const m=docMeta(db,d.id);m.status='deleted';db.prepare('INSERT OR REPLACE INTO document_meta VALUES (?,?)').run(d.id,JSON.stringify(m));}db.prepare('UPDATE documents SET active=0 WHERE logical_id=?').run(row.logical_id);return {id:p.id};}
 if(kind==='ship.save') {const s=validateShip(p),old=db.prepare('SELECT version FROM ships WHERE id=?').get(s.id);requireValue((old?.version||0)===(p.version||0),'선박 정보가 변경되었습니다.','VERSION_CONFLICT',409);db.prepare('INSERT OR REPLACE INTO ships VALUES (?,?,?)').run(s.id,JSON.stringify(s),(old?.version||0)+1);return s;}
 if(kind==='operation.save'||kind==='operation.import') {
  const checked=kind==='operation.save'?{rows:[validateOperation(db,p)],errors:[]}:validateRows(db,p.rows);requireValue(!checked.errors.length,checked.errors.map(e=>e.row+'행: '+e.message).join('\n'));
  for(const r of checked.rows)db.prepare('INSERT OR REPLACE INTO operations VALUES (?,?,?,?,?)').run(r.id,r.ship,r.date,JSON.stringify(r),r.version+1);return {count:checked.rows.length};
 }
 if(kind==='operation.delete') {assertExpected(db.prepare('SELECT version FROM operations WHERE id=?').get(p.id),p);db.prepare('DELETE FROM operations WHERE id=?').run(p.id);return {id:p.id};}
 if(kind==='report.approve') {const r=getReport(db,p.id);assertExpected(r,p);const m=reportMeta(db,p.id);requireValue(m.status==='review','검토 요청된 보고서만 승인할 수 있습니다.');db.prepare("UPDATE report_meta SET status='approved',body=? WHERE id=?").run(JSON.stringify({...m.body,approvedBy:user.name,approvedAt:now()}),p.id);return {id:p.id};}
 requireValue(false,'지원하지 않는 변경 요청입니다.');
}
export function change(db,user,kind,payload) {
 permit(user);requireValue(['document.save','document.delete','ship.save','operation.save','operation.import','operation.delete'].includes(kind),'지원하지 않는 변경입니다.');
 object(payload);
 if(kind.startsWith('document.')){const id=kind==='document.save'?payload.expectedId:payload.id;if(id)requireValue(canReadDoc(db,user,id),'문서 접근 권한이 없습니다.','FORBIDDEN',403);}
 return transaction(db,()=>{
  const id=randomUUID(),at=now(),result=applyChange(db,user,kind,payload);
  db.prepare('INSERT INTO changes VALUES (?,?,?,?,?,?,?,?,?)').run(id,at,user.id,kind,JSON.stringify(payload),'approved',user.id,at,'관리자 직접 반영');
  audit(db,user,'change','변경 즉시 반영',kind,{id,result});return {id,status:'approved',result};
 });
}

export function listChanges(db,user) {permit(user);return db.prepare("SELECT c.*,COALESCE(u.name,CASE WHEN c.actor LIKE 'guest_%' THEN '일반 사용자 · ' || substr(c.actor,7,8) ELSE '이전 사용자' END) actor_name FROM changes c LEFT JOIN users u ON u.id=c.actor ORDER BY at DESC LIMIT 200").all().map(r=>({...r,payload:parse(r.payload)}));}
export function reviewChange(db,user,p) {permit(user);return transaction(db,()=>{const c=db.prepare('SELECT * FROM changes WHERE id=?').get(p.id);requireValue(c?.status==='pending','처리할 승인 요청이 없습니다.','VERSION_CONFLICT',409);requireValue(['approve','reject'].includes(p.decision),'승인 또는 반려를 선택해 주세요.');const payload=parse(c.payload);if(p.decision==='approve')applyChange(db,user,c.kind,payload);else if(c.kind==='report.approve')db.prepare("UPDATE report_meta SET status='draft' WHERE id=?").run(payload.id);db.prepare('UPDATE changes SET status=?,reviewer=?,reviewed_at=?,note=? WHERE id=?').run(p.decision==='approve'?'approved':'rejected',user.id,now(),optional(p.note),p.id);audit(db,user,'change',p.decision==='approve'?'승인':'반려',c.kind,{id:c.id,note:optional(p.note)});return {ok:true};});}
export function reportMeta(db,id) {const r=db.prepare('SELECT * FROM report_meta WHERE id=?').get(id);return r?{...r,body:parse(r.body)}:{owner:'',status:'draft',body:{}};}
function canReadReport(db,u,r) {const m=reportMeta(db,r.id);return (isAdmin(u)||m.owner===u.id||m.status==='approved')&&r.sources.every(id=>canReadDoc(db,u,id));}
export function reportList(db,user) {return db.prepare('SELECT id FROM reports ORDER BY updated_at DESC').all().map(x=>getReport(db,x.id)).filter(r=>canReadReport(db,user,r)).map(r=>({...r,...reportMeta(db,r.id)}));}
export function loadReport(db,user,id) {const r=getReport(db,id);requireValue(r && canReadReport(db,user,r),'보고서를 찾을 수 없거나 열람 권한이 없습니다.','NOT_FOUND',404);return {...r,...reportMeta(db,id)};}
export function storeReport(db,user,p) {
 permit(user,['admin','operator','guest']);object(p);const id=p.id||randomUUID(),old=getReport(db,id),m=reportMeta(db,id);
 if(old){requireValue(isAdmin(user)||m.owner===user.id,'본인의 초안만 수정할 수 있습니다.','FORBIDDEN',403);requireValue(m.status==='draft','검토 중이거나 승인된 보고서는 새 초안으로 복사해 주세요.');}
 requireValue(Array.isArray(p.sources)&&p.sources.every(id=>canReadDoc(db,user,id)),'열람할 수 없는 문서가 근거에 포함되어 있습니다.','FORBIDDEN',403);
 const body=p.body&&typeof p.body==='object'?p.body:{};requireValue(JSON.stringify(body).length<50000,'보고서 추가 정보가 너무 큽니다.');
 return transaction(db,()=>{const report=saveReport(db,{...p,id});db.prepare("INSERT INTO report_meta VALUES (?,?,'draft',?) ON CONFLICT(id) DO UPDATE SET body=excluded.body").run(id,old?m.owner:user.id,JSON.stringify(body));audit(db,user,'report','초안 저장',id,{title:report.title,version:report.version});return {...report,...reportMeta(db,id)};});
}
export function submitReport(db,user,p) {permit(user,['admin','operator','guest']);return transaction(db,()=>{const r=loadReport(db,user,p.id);assertExpected(r,p);requireValue(isAdmin(user)||r.owner===user.id,'본인의 보고서만 검토 요청할 수 있습니다.','FORBIDDEN',403);requireValue(r.status==='draft','이미 검토 요청 또는 승인된 보고서입니다.');const id=randomUUID();db.prepare("UPDATE report_meta SET status='review' WHERE id=?").run(p.id);db.prepare("INSERT INTO changes VALUES (?,?,?,?,?, 'pending',NULL,NULL,'')").run(id,now(),user.id,'report.approve',JSON.stringify({id:p.id,version:p.version,title:r.title}));audit(db,user,'report','보고서 검토 요청',p.id);return {id};});}
export function queryHistory(db,user) {return db.prepare('SELECT q.* FROM queries q JOIN query_owner o ON o.id=q.id WHERE o.owner=? ORDER BY q.created_at DESC LIMIT 100').all(user.id).map(q=>{const answer=parse(q.response);const visible=(answer.evidence||[]).every(e=>canReadDoc(db,user,e.document_id));return {id:q.id,question:q.question,at:q.created_at,answer:visible?answer:null,unavailable:!visible};});}
export function logs(db,user) {permit(user);return db.prepare('SELECT * FROM audit ORDER BY at DESC LIMIT 500').all().map(r=>({...r,detail:parse(r.detail)}));}
const backupTables=['documents','chunks','reports','tool_runs','queries','users','document_meta','document_files','chunk_pages','ships','operations','report_meta','audit','query_owner','changes','settings'];
export function createBackup(db,user,dir,label='수동 백업') {permit(user);mkdirSync(dir,{recursive:true});const content=transaction(db,()=>Object.fromEntries(backupTables.map(t=>[t,db.prepare(`SELECT * FROM ${t}`).all()])));const payload={format:'haedap-workspace',version:2,createdAt:now(),label,tables:content};const json=JSON.stringify(payload),id=randomUUID(),envelope={...payload,checksum:createHash('sha256').update(json).digest('hex')};writeFileSync(join(dir,id+'.tmp'),JSON.stringify(envelope));renameSync(join(dir,id+'.tmp'),join(dir,id+'.json'));audit(db,user,'backup','전체 백업 생성',id,{label});return {id,createdAt:payload.createdAt,version:2,label};}
export function backupList(user,dir) {permit(user);mkdirSync(dir,{recursive:true});return readdirSync(dir).filter(n=>/^[a-f0-9-]+\.json$/.test(n)).map(n=>{try{const p=parse(readFileSync(join(dir,n),'utf8'));return {id:n.slice(0,-5),createdAt:p.createdAt,version:p.version,label:p.label,counts:{documents:p.tables.documents.length,operations:p.tables.operations.length,reports:p.tables.reports.length}};}catch{return null;}}).filter(Boolean).sort((a,b)=>b.createdAt.localeCompare(a.createdAt));}
export function readBackup(user,dir,id) {permit(user);requireValue(/^[a-f0-9-]{36}$/.test(id),'백업 ID를 확인해 주세요.');return parse(readFileSync(join(dir,id+'.json'),'utf8'));}
export function restoreBackup(db,user,dir,p) {
 permit(user);requireValue(p.confirm==='복구','복구 확인 문구를 입력해 주세요.');const snapshot=readBackup(user,dir,p.id),{checksum,...payload}=snapshot;
 requireValue(payload.format==='haedap-workspace'&&payload.version===2&&checksum===createHash('sha256').update(JSON.stringify(payload)).digest('hex'),'백업 형식 또는 무결성 검사에 실패했습니다.');
 requireValue(backupTables.every(t=>Array.isArray(payload.tables?.[t])),'백업에 필수 데이터가 없습니다.');requireValue(payload.tables.users.some(u=>u.role==='admin'&&u.active),'복구할 활성 관리자 계정이 없습니다.');
 const safety=createBackup(db,user,dir,'복구 직전 자동 보관');
 transaction(db,()=>{db.exec('DELETE FROM chunks_fts');for(const t of [...backupTables].reverse())db.exec(`DELETE FROM ${t}`);for(const t of backupTables){const columns=db.prepare(`PRAGMA table_info(${t})`).all().map(c=>c.name);const insert=db.prepare(`INSERT INTO ${t} (${columns.join(',')}) VALUES (${columns.map(()=>'?').join(',')})`);for(const row of payload.tables[t])insert.run(...columns.map(c=>row[c]??null));}
 for(const c of db.prepare('SELECT c.*,d.title,d.reference FROM chunks c JOIN documents d ON d.id=c.document_id').all())db.prepare('INSERT INTO chunks_fts VALUES (?,?)').run(c.id,tokens(`${c.title} ${c.reference} ${c.heading} ${c.text}`).join(' '));
 audit(db,user,'backup','전체 복구',p.id,{safetyBackup:safety.id});});return {ok:true,safetyBackup:safety.id};
}

export function importBackup(db,user,dir,snapshot) {
 permit(user);const {checksum,...payload}=snapshot;
 requireValue(payload.format==='haedap-workspace'&&payload.version===2&&checksum===createHash('sha256').update(JSON.stringify(payload)).digest('hex'),'백업 형식 또는 무결성 검사에 실패했습니다.');
 requireValue(backupTables.every(t=>Array.isArray(payload.tables?.[t])),'필수 백업 데이터가 없습니다.');
 requireValue(payload.tables.users.some(u=>u.role==='admin'&&u.active),'백업에 활성 관리자 계정이 없습니다.');
 mkdirSync(dir,{recursive:true});const id=randomUUID();writeFileSync(join(dir,id+'.tmp'),JSON.stringify(snapshot));renameSync(join(dir,id+'.tmp'),join(dir,id+'.json'));
 audit(db,user,'backup','백업 파일 가져오기',id);return {id,createdAt:payload.createdAt,version:payload.version,label:payload.label};
}

export function automaticBackup(db,dir) {
 if(db.prepare("SELECT value FROM settings WHERE key='autoBackup'").get()?.value!=='daily')return;
 const day=now().slice(0,10);if(db.prepare("SELECT value FROM settings WHERE key='autoBackupDay'").get()?.value===day)return;
 const admin=db.prepare("SELECT * FROM users WHERE role='admin' AND active=1 LIMIT 1").get();if(!admin)return;
 createBackup(db,{...admin,name:'자동 백업'},dir,'정기 자동 백업');
 db.prepare("INSERT OR REPLACE INTO settings VALUES ('autoBackupDay',?)").run(day);
}
