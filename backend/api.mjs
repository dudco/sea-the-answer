import { randomBytes, createHash } from 'node:crypto';
import { dirname, resolve } from 'node:path';
import { databasePath } from './paths.mjs';
import { AppError, requireValue } from './validation.mjs';
import { retrieve } from './db.mjs';
import { modelConfigured } from './rag.mjs';
import { runTool, toolDefinitions } from './tools.mjs';
import * as w from './workspace.mjs';
import { integratedAnswer, generateReport } from './analysis.mjs';
import { sampleData } from './sample-data.mjs';
function json(res,status,body){res.writeHead(status,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'});res.end(JSON.stringify(body));}
function readJson(req,limit=1048576){requireValue(req.headers['content-type']?.split(';')[0].trim()==='application/json','application/json 요청이 필요합니다.','CONTENT_TYPE',415);return new Promise((resolve,reject)=>{let size=0,chunks=[],tooLarge=false;req.on('data',data=>{size+=data.length;if(size>limit){tooLarge=true;chunks=[];}else if(!tooLarge)chunks.push(data);});req.on('error',reject);req.on('end',()=>{if(tooLarge)return reject(new AppError(413,'BODY_TOO_LARGE','파일 또는 요청이 너무 큽니다.'));try{resolve(JSON.parse(Buffer.concat(chunks).toString('utf8')));}catch{reject(new AppError(400,'INVALID_JSON','올바른 JSON이 필요합니다.'));}});});}
export function createApi(db,options={}) {
 w.initializeWorkspace(db);
 w.initializePublicAccess(db);
 const token=randomBytes(32).toString('hex'),sessions=new Map(),attempts=new Map();let active=0;
 const backupDir=options.backupDir||resolve(dirname(databasePath()),'backups');
 const digest=s=>createHash('sha256').update(s).digest('hex');
 const sessionFor=req=>{const id=(req.headers.cookie||'').split(';').map(s=>s.trim()).find(s=>s.startsWith('haedap_session='))?.slice(15);const session=id?sessions.get(digest(id)):null;if(!session||session.expires<Date.now())return null;const u=db.prepare('SELECT * FROM users WHERE id=? AND active=1').get(session.userId);return u&&u.version===session.version?w.publicUser(u):null;};
 const cookieValue=(req,name)=>(req.headers.cookie||'').split(';').map(s=>s.trim()).find(s=>s.startsWith(name+'='))?.slice(name.length+1);
 const setCookie=(res,value)=>res.setHeader('Set-Cookie',[...(res.getHeader('Set-Cookie')||[]),value]);
 const guestFor=(req,res)=>{let value=cookieValue(req,'haedap_guest');if(!/^[a-f0-9]{64}$/.test(value||'')){value=randomBytes(32).toString('hex');setCookie(res,`haedap_guest=${value}; HttpOnly; SameSite=Strict; Path=/; Max-Age=31536000`);}const id='guest_'+digest(value);return {id,username:'',name:'일반 사용자 · '+id.slice(6,14),role:'guest',active:1,version:1};};
 const issue=(res,user)=>{const value=randomBytes(32).toString('hex');sessions.set(digest(value),{userId:user.id,version:user.version,expires:Date.now()+12*3600000});setCookie(res,`haedap_session=${value}; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200`);};
 return async(req,res,path)=>{let user=null;
  try {
   const host=req.headers.host,allowed=options.allowRequest?options.allowRequest(req):/^(127\.0\.0\.1|localhost)(:\d+)?$/.test(host||'');
   requireValue(allowed,'실행 창에 표시된 서버 주소로 접속해 주세요.','HOST_DENIED',403);
   requireValue(!req.headers.origin||req.headers.origin===`http://${host}`,'동일 출처 요청만 허용합니다.','ORIGIN_DENIED',403);
   requireValue(!['cross-site','same-site'].includes(req.headers['sec-fetch-site']),'동일 출처 요청만 허용합니다.','ORIGIN_DENIED',403);
   const guest=guestFor(req,res);user=sessionFor(req)||guest;const setupRequired=false;
   if(req.method==='GET'&&path==='/api/health')return json(res,200,{ok:true,storage:'sqlite',retrieval:'fts5-bm25-ko-bigram',llmConfigured:modelConfigured(options.env),csrfToken:token,user,setupRequired,documents:user?w.workspaceDocuments(db,user).filter(d=>d.active).length:0,version:'1.3.1',authenticated:w.isAdmin(user),publicAccess:true});
   if(path!=='/api/health'&&!path.startsWith('/api/auth/')&&req.headers['x-haedap-identity'])requireValue(req.headers['x-haedap-identity']===user.id,'사용자 상태가 바뀌었습니다. 다시 연결해 주세요.','AUTH_REQUIRED',401);
   if(req.method==='GET') {
    requireValue(user,'로그인이 필요합니다.','AUTH_REQUIRED',401);
    if(path==='/api/documents')return json(res,200,{documents:w.workspaceDocuments(db,user)});
    if(path.startsWith('/api/documents/')&&path.endsWith('/pdf')){const id=decodeURIComponent(path.slice(15,-4));requireValue(w.canReadDoc(db,user,id),'문서 열람 권한이 없습니다.','FORBIDDEN',403);const f=db.prepare('SELECT * FROM document_files WHERE id=?').get(id);requireValue(f,'저장된 PDF가 없습니다.','NOT_FOUND',404);const bytes=Buffer.from(f.base64,'base64');res.writeHead(200,{'Content-Type':'application/pdf','Content-Length':bytes.length,'Content-Disposition':`inline; filename="document.pdf"; filename*=UTF-8''${encodeURIComponent(f.name)}`,'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'});return res.end(bytes);}
    if(path==='/api/operations')return json(res,200,{ships:w.ships(db),records:w.operations(db)});
    if(path==='/api/reports')return json(res,200,{reports:w.reportList(db,user)});
    if(path.startsWith('/api/reports/')){const id=decodeURIComponent(path.slice(13));if(id==='current'&&!db.prepare("SELECT 1 FROM reports WHERE id='current'").get())return json(res,200,{report:null});return json(res,200,{report:w.loadReport(db,user,id)});}
    if(path==='/api/history')return json(res,200,{history:w.queryHistory(db,user)});
    if(path==='/api/users'){w.permit(user);return json(res,200,{users:db.prepare('SELECT * FROM users ORDER BY username').all().map(w.publicUser)});}
    if(path==='/api/logs')return json(res,200,{logs:w.logs(db,user)});
    if(path==='/api/changes')return json(res,200,{changes:w.listChanges(db,user)});
    if(path==='/api/backups')return json(res,200,{backups:w.backupList(user,backupDir),autoBackup:db.prepare("SELECT value FROM settings WHERE key='autoBackup'").get()?.value||'off'});
    if(path.startsWith('/api/backups/'))return json(res,200,w.readBackup(user,backupDir,path.slice(13)));
    if(path==='/api/tools')return json(res,200,{tools:toolDefinitions});
    throw new AppError(404,'NOT_FOUND','API 경로를 찾을 수 없습니다.');
   }
   requireValue(req.method==='POST','API 경로를 찾을 수 없습니다.','NOT_FOUND',404);
   requireValue(req.headers['x-haedap-token']===token,'연결을 새로고침한 뒤 다시 시도하세요.','SESSION_EXPIRED',403);
   requireValue(active<4,'처리 중인 요청이 많습니다. 잠시 후 다시 시도하세요.','BUSY',429);
   active++;try{
    const body=await readJson(req,path==='/api/changes'?38*1024*1024:path==='/api/backups/import'?100*1024*1024:1048576);requireValue(body&&typeof body==='object'&&!Array.isArray(body),'JSON 객체가 필요합니다.');
    if(path==='/api/auth/setup')throw new AppError(410,'SETUP_DISABLED','초기 설정은 필요하지 않습니다. 관리자 로그인은 admin / 1234입니다.');
    if(path==='/api/auth/login') {const key=req.socket.remoteAddress,tries=attempts.get(key)||{count:0,until:0};if(tries.until<Date.now()){tries.count=0;tries.until=Date.now()+60000;}requireValue(tries.count<10,'로그인 시도가 많습니다. 1분 뒤 다시 시도해 주세요.','LOGIN_LIMIT',429);tries.count++;attempts.set(key,tries);const u=w.authenticate(db,body.username,body.password);requireValue(w.isAdmin(u),'관리자 계정으로 로그인해 주세요.','FORBIDDEN',403);attempts.delete(key);const previous=cookieValue(req,'haedap_session');if(previous)sessions.delete(digest(previous));issue(res,u);return json(res,200,{user:u});}
    requireValue(user,'로그인이 필요합니다.','AUTH_REQUIRED',401);
    if(path==='/api/auth/logout'){const value=(req.headers.cookie||'').split(';').map(s=>s.trim()).find(s=>s.startsWith('haedap_session='))?.slice(15);if(value)sessions.delete(digest(value));setCookie(res,'haedap_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0');if(w.isAdmin(user))w.audit(db,user,'auth','로그아웃',user.username);return json(res,200,{ok:true,user:guest});}
    if(path==='/api/ask'){const answer=await integratedAnswer(db,user,body,options);requireValue((sessionFor(req)||guest).id===user.id,'사용자 상태가 바뀌었습니다. 다시 연결해 주세요.','AUTH_REQUIRED',401);requireValue(answer.evidence.every(e=>w.canReadDoc(db,user,e.document_id)),'문서 권한이 변경되었습니다. 다시 질문해 주세요.','FORBIDDEN',403);w.audit(db,user,'query','질의',answer.id,{question:answer.question,task:answer.task});return json(res,200,answer);}
    if(path==='/api/search')return json(res,200,{evidence:w.enrichEvidence(db,retrieve(db,body.question,{kind:body.filter||'all',allowedIds:w.allowedDocs(db,user)}))});
    if(path==='/api/users')return json(res,200,{user:w.saveUser(db,user,body)});
    if(path==='/api/changes')return json(res,200,w.change(db,user,body.kind,body.payload));
    if(path==='/api/changes/review')return json(res,200,w.reviewChange(db,user,body));
    if(path==='/api/operations/validate'){w.permit(user);const check=w.validateRows(db,body.rows);return json(res,200,{valid:!check.errors.length,errors:check.errors,count:body.rows.length});}
    if(path==='/api/operations/example'){w.permit(user);requireValue(!w.ships(db).length&&!w.operations(db).length,'기록이 없는 새 작업공간에서만 예시를 넣을 수 있습니다.');w.transaction(db,()=>{for(const s of sampleData.ships)w.change(db,user,'ship.save',{...s,sample:true});w.change(db,user,'operation.import',{rows:sampleData.records.map(r=>({...r,factor:3.114,fuelType:'예시 연료',sample:true,note:'가상 예시 기록',version:0}))});});return json(res,200,{ok:true});}
    if(path==='/api/reports'||path==='/api/reports/current')return json(res,200,{report:w.storeReport(db,user,path.endsWith('/current')?{...body,id:'current'}:body)});
    if(path==='/api/reports/generate')return json(res,200,{report:generateReport(db,user,body)});
    if(path==='/api/reports/submit')return json(res,200,w.submitReport(db,user,body));
    if(path==='/api/backups')return json(res,200,{backup:w.createBackup(db,user,backupDir)});
    if(path==='/api/backups/settings'){w.permit(user);requireValue(['daily','off'].includes(body.autoBackup),'자동 백업 설정을 확인해 주세요.');db.prepare("INSERT OR REPLACE INTO settings VALUES ('autoBackup',?)").run(body.autoBackup);w.audit(db,user,'backup','자동 백업 설정',body.autoBackup);return json(res,200,{ok:true});}
    if(path==='/api/backups/import')return json(res,200,{backup:w.importBackup(db,user,backupDir,body)});
    if(path==='/api/backups/restore'){requireValue(active===1,'진행 중인 요청이 있습니다. 잠시 뒤 복구해 주세요.','BUSY',409);const result=w.restoreBackup(db,user,backupDir,body);w.initializePublicAccess(db);sessions.clear();return json(res,200,result);}
    if(path.startsWith('/api/tools/')){const name=path.slice(11),result=runTool(db,name,body);w.audit(db,user,'tool','계산 실행',name,{id:result.id,inputs:body});return json(res,200,{result});}
    throw new AppError(404,'NOT_FOUND','API 경로를 찾을 수 없습니다.');
   } finally {active--;}
  } catch(error){if(user){try{w.audit(db,user,'error','요청 실패',path,{code:error.code||'INTERNAL_ERROR',message:error instanceof AppError?error.message:'내부 처리 오류'});}catch{}}
   if(error instanceof AppError)json(res,error.status,{error:{code:error.code,message:error.message}});
   else {console.error('API failure:',error.code||error.name,error.message);json(res,500,{error:{code:'INTERNAL_ERROR',message:'처리에 실패했습니다. 입력 내용은 유지됩니다. 관리 로그와 서버 실행 창을 확인해 주세요.'}});}
  }
 };
}
