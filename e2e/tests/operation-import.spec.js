import {test,expect} from '@playwright/test';

async function setup(page,failReference=false){
 const state={calls:[],errors:[],referenceFailures:failReference?1:0};
 page.on('pageerror',e=>state.errors.push(e.message));
 await page.route('**/api/**',route=>{
  const req=route.request(),path=new URL(req.url()).pathname,body=req.method()==='POST'?req.postDataJSON():null;
  state.calls.push({path,body});
  const send=(data,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)});
  if(path==='/api/health')return send({csrfToken:'csv-csrf',authenticated:true,user:{id:'admin',name:'검증 관리자',role:'admin'},publicAccess:false});
  if(path==='/api/operations')return send({ships:[],records:[]});
  if(path==='/api/documents')return send({documents:[]});
  if(path==='/api/operations/import/start')return send({id:'upload-a',chunk_bytes:4096});
  if(path==='/api/operations/import/chunk')return send({received:body.offset+Buffer.from(body.data,'base64').length});
  if(path==='/api/operations/import/preview')return send({preview_hash:'verified',has_database:true,datasets:[{kind:'annual_reports',rows:80552,new:80552,unchanged:0,storage:'maritime_data.annual_reports'}],reference:{ports:[{},{}]},reference_previous_sha256:null,existing_ship_links:0,ignored_files:1,notice:'미리보기이며 아직 등록되지 않았습니다.'});
  if(path==='/api/operations/import/commit')return send({status:'completed',datasets:[{new:80552}],linked_ships:0});
  if(path==='/api/operations/import/reference'){
   if(state.referenceFailures-->0)return send({error:{code:'IMPORT_UNAVAILABLE',message:'참조 저장 실패'}},503);
   return send({status:'completed'});
  }
  return send({reports:[],skills:[],history:[],cancelled:true});
 });
 await page.goto('/operations');await page.locator('[data-action=importOperations]').click();
 return state;
}

test('existing CSV button uploads chunks, previews annual storage and registers sources separately',async({page})=>{
 const state=await setup(page);
 const payload=Buffer.alloc(10000,65);
 await page.getByLabel('운항 자료 파일').setInputFiles({name:'prepared.zip',mimeType:'application/zip',buffer:payload});
 await page.getByRole('button',{name:'파일 검증',exact:true}).click();
 await expect(page.locator('[data-import-preview]')).toContainText('MRV 보고기간 자료');
 await expect(page.locator('[data-import-preview]')).toContainText('80552');
 const chunks=state.calls.filter(c=>c.path.endsWith('/chunk'));expect(chunks).toHaveLength(3);
 expect(Buffer.concat(chunks.map(c=>Buffer.from(c.body.data,'base64')))).toEqual(payload);
 expect(chunks.map(c=>c.body.offset)).toEqual([0,4096,8192]);
 await page.locator('[data-action=commitCsv]').click();
 await expect(page.locator('[data-import-database]')).toContainText('80552');
 await expect(page.locator('[data-import-reference]')).toContainText('연결 완료');
 expect(state.calls.find(c=>c.path.endsWith('/commit')).body).toEqual({id:'upload-a',preview_hash:'verified',map_existing:true});
 expect(state.errors).toEqual([]);
});

test('reference failure keeps successful database result and retry does not submit database twice',async({page})=>{
 const state=await setup(page,true);
 await page.getByLabel('운항 자료 파일').setInputFiles({name:'prepared.zip',mimeType:'application/zip',buffer:Buffer.from('fixture')});
 await page.getByRole('button',{name:'파일 검증',exact:true}).click();await expect(page.locator('[data-import-preview]')).toBeVisible();
 await page.locator('[data-action=commitCsv]').click();
 await expect(page.locator('#csvForm [role=alert]')).toContainText('DB 등록은 완료됐습니다');
 await expect(page.locator('[data-import-database]')).toBeVisible();
 await page.locator('[data-action=commitCsv]').click();await expect(page.locator('[data-import-reference]')).toBeVisible();
 expect(state.calls.filter(c=>c.path.endsWith('/commit'))).toHaveLength(1);
 expect(state.calls.filter(c=>c.path.endsWith('/reference'))).toHaveLength(2);
 expect(state.errors).toEqual([]);
});
