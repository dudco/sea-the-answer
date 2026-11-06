"""Owner-bound, bounded temporary uploads. No client-selected server paths."""
import base64
import csv
from dataclasses import dataclass,field
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import time
from uuid import uuid4
import zipfile

import psycopg
from fastapi import HTTPException
from pydantic import ValidationError
from psycopg import sql

from . import config
from .errors import ApiError,require
from .web import security
from tools.operation_import import unpack,classify,stage_tables,apply_tables,daily_rows,ORDER,MAX_EXPANDED
from tools.operation_import import ImportConflict
from tools.navigation_references import catalog_summary,load_catalog
from tools.port_reference import valid_imo

CHUNK=384*1024
MAX_INPUT=128*1024*1024
TTL=20*60
_uploads={};_guard=threading.RLock()


@dataclass
class Upload:
    owner:str
    files:list
    temp:object
    touched:float=field(default_factory=time.monotonic)
    lock:object=field(default_factory=threading.RLock)
    parsed:object=None
    plan:object=None
    preview:object=None


def import_directory():
    value=os.getenv('HAEDAP_IMPORT_DIR')
    return Path(value).resolve() if value else config.BACKEND_DIR/'data/imports'


def reference_path():
    return Path(os.getenv('MARITIME_PORT_REFERENCES_PATH') or import_directory()/'navigation/catalog.json')


def current(ctx,lock=False):
    ctx.db.permit(ctx.user)
    if lock:
        row=ctx.db.one('SELECT role,active,must_change_password FROM users WHERE id=%s FOR SHARE',(ctx.user['id'],))
        require(row and row['active'] and row['role']=='admin' and not row['must_change_password'],'사용자 상태가 변경되었습니다.','AUTH_REQUIRED',401)
    user=security.current_user(ctx.db,ctx.request,ctx.guest)
    require(user['id']==ctx.user['id'] and user['role']=='admin' and not user.get('must_change_password'),'관리자 로그인을 확인해 주세요.','AUTH_REQUIRED',401)


def prune():
    for identifier,upload in list(_uploads.items()):
        if time.monotonic()-upload.touched>TTL and upload.lock.acquire(blocking=False):
            try:
                upload.temp.cleanup();_uploads.pop(identifier,None)
            finally:upload.lock.release()


def start(ctx):
    current(ctx);files=ctx.body.get('files')
    require(set(ctx.body)=={'files'} and isinstance(files,list) and 1<=len(files)<=16,'파일은 1~16개로 선택해 주세요.')
    total=0;items=[]
    for record in files:
        require(isinstance(record,dict) and set(record)=={'name','size'},'파일 이름·크기를 확인해 주세요.')
        name,size=record['name'],record['size']
        require(isinstance(name,str) and 0<len(name)<=150 and not any(c in name for c in '/\\\x00:') and name.lower().endswith(('.csv','.zip','.json')),'CSV·ZIP·JSON 파일 이름을 확인해 주세요.')
        require(type(size) is int and 0<size<=MAX_INPUT,'빈 파일 또는 128MiB 초과 파일은 지원하지 않습니다.')
        total+=size;items.append({'name':name,'size':size,'offset':0})
    require(total<=MAX_INPUT,'전체 파일은 128MiB 이하여야 합니다.','BODY_TOO_LARGE',413)
    with _guard:
        prune()
        require(sum(u.owner==ctx.user['id'] for u in _uploads.values())<2,'진행 중인 가져오기를 마치거나 잠시 후 다시 시도해 주세요.','BUSY',429)
        reserved=sum(sum(f['size'] for f in u.files)+MAX_EXPANDED for u in _uploads.values())
        require(reserved+total+MAX_EXPANDED<=512*1024*1024,'서버의 임시 업로드 용량이 사용 중입니다.','BUSY',429)
        identifier=str(uuid4());temp=tempfile.TemporaryDirectory(prefix='haedap-import-')
        for i,item in enumerate(items):item['path']=Path(temp.name)/f'upload-{i}'
        _uploads[identifier]=Upload(ctx.user['id'],items,temp)
    return {'id':identifier,'chunk_bytes':CHUNK,'expires_in':TTL}


def owned(ctx):
    current(ctx);identifier=ctx.body.get('id')
    require(isinstance(identifier,str),'업로드 ID를 확인해 주세요.')
    with _guard:
        prune();upload=_uploads.get(identifier)
        require(upload and upload.owner==ctx.user['id'],'본인의 유효한 업로드를 다시 선택해 주세요.','NOT_FOUND',404)
        upload.touched=time.monotonic()
    return upload


def chunk(ctx):
    upload=owned(ctx)
    require(set(ctx.body)=={'id','index','offset','data'},'업로드 블록 필드를 확인해 주세요.')
    i,offset,data=(ctx.body.get(k) for k in ('index','offset','data'))
    require(type(i) is int and 0<=i<len(upload.files) and type(offset) is int and isinstance(data,str) and len(data)<=CHUNK*4//3+4,'업로드 블록 크기를 확인해 주세요.')
    try:raw=base64.b64decode(data,validate=True)
    except ValueError:raise ApiError(400,'INVALID_INPUT','올바른 base64 블록이 필요합니다.') from None
    require(0<len(raw)<=CHUNK,'빈 블록 또는 크기 초과입니다.')
    with upload.lock:
        require(upload.preview is None,'검증 후에는 파일을 변경할 수 없습니다.')
        record=upload.files[i]
        require(offset==record['offset'] and offset+len(raw)<=record['size'],'업로드 순서·크기가 다릅니다. 다시 선택해 주세요.','VERSION_CONFLICT',409)
        with record['path'].open('ab') as stream:stream.write(raw)
        record['offset']+=len(raw)
    return {'received':record['offset']}


def database(ctx,plan,apply=False,map_existing=False):
    target=os.getenv('MARITIME_DATA_DATABASE_URL') or config.database_url()
    require(target.replace('postgresql+psycopg://','postgresql://',1)==config.database_url().replace('postgresql+psycopg://','postgresql://',1),
        '웹 적재는 현재 앱과 같은 DB를 지원합니다. 별도 해사 DB는 관리자의 기존 적재 경로를 이용해 주세요.')
    connection=ctx.db.db
    with connection.transaction(force_rollback=not apply):
        connection.execute("SET LOCAL lock_timeout='5s'")
        connection.execute("SET LOCAL statement_timeout='45s'")
        if plan['tables']:
            require(all(connection.execute('SELECT to_regclass(%s) AS name',('maritime_data.'+n,)).fetchone()['name'] for n in ORDER),
                '서버의 해사 DB migration을 먼저 적용해 주세요.','SCHEMA_NOT_READY',503)
            connection.execute(sql.SQL('LOCK TABLE {} IN SHARE ROW EXCLUSIVE MODE').format(sql.SQL(',').join(sql.Identifier('maritime_data',n) for n in ORDER)))
        stages,summaries=stage_tables(connection,plan)
        apply_tables(connection,stages)
        rows=daily_rows(plan['daily']);new=0;unchanged=0
        for raw in rows:
            old=ctx.db.one('SELECT id,body,version FROM operations WHERE ship=%s AND date=%s',(raw.get('ship'),raw.get('date')))
            if old:raw={**raw,'id':old['id'],'version':old['version']}
            checked=ctx.db.validate_operation(raw)
            if old:
                normalized=ctx.db.validate_operation({**old['body'],'version':old['version']})
                require({k:v for k,v in checked.items() if k not in ('id','version')}=={k:v for k,v in normalized.items() if k not in ('id','version')},
                    '기존 날짜의 운항 기록과 내용이 다릅니다. 원본을 덮어쓰지 않았습니다.','VERSION_CONFLICT',409)
                unchanged+=1
            else:ctx.db.apply_change('operation.save',raw);new+=1
        if plan['daily']:summaries.append({'kind':'daily','rows':len(rows),'new':new,'unchanged':unchanged,'storage':'operations'})
        linked=0
        if map_existing and stages:
            for row in ctx.db.all("""SELECT v.vessel_id,v.imo_number,s.id FROM maritime_data.vessels v JOIN ships s
                ON regexp_replace(coalesce(s.body->>'imo',''),'^IMO\\s*','','i')=v.imo_number
                WHERE v.data_origin='REAL' AND v.ship_id IS NULL AND coalesce((s.body->>'sample')::boolean,false)=false
                AND NOT EXISTS(SELECT FROM maritime_data.vessels x WHERE x.ship_id=s.id)
                AND (SELECT count(*) FROM ships p WHERE regexp_replace(coalesce(p.body->>'imo',''),'^IMO\\s*','','i')=v.imo_number)=1"""):
                if valid_imo(row['imo_number']):
                    ctx.db.run('UPDATE maritime_data.vessels SET ship_id=%s WHERE vessel_id=%s AND ship_id IS NULL',(row['id'],row['vessel_id']));linked+=1
        for stage,_columns in stages.values():connection.execute(sql.SQL('DROP TABLE {}').format(sql.Identifier(stage)))
        return summaries,linked


def digest(upload):
    h=hashlib.sha256()
    for f in upload.files:
        require(f['offset']==f['size'],'파일 전송을 먼저 완료해 주세요.')
        h.update(f['name'].encode());h.update(str(f['size']).encode())
        with f['path'].open('rb') as stream:
            while block:=stream.read(1024*1024):h.update(block)
    return h.hexdigest()


def preview(ctx):
    upload=owned(ctx)
    require(set(ctx.body)=={'id'},'미리보기 입력을 확인해 주세요.')
    with upload.lock:
        checksum=digest(upload)
        upload.preview=None
        if upload.parsed:upload.parsed.cleanup()
        upload.parsed=tempfile.TemporaryDirectory(prefix='parsed-',dir=upload.temp.name)
        files,ignored=unpack([(f['name'],f['path']) for f in upload.files],Path(upload.parsed.name))
        upload.plan=classify(files)
        summaries,linked=database(ctx,upload.plan,False,True) if upload.plan['tables'] or upload.plan['daily'] else ([],0)
        target=reference_path();old=hashlib.sha256(target.read_bytes()).hexdigest() if target.is_file() else None
        catalog=None
        if upload.plan['catalog']:
            data,sha=load_catalog(upload.plan['catalog']);catalog=catalog_summary(data,sha)
        current(ctx)
        result={'preview_hash':checksum,'datasets':summaries,'reference':catalog,'reference_previous_sha256':old,
            'existing_ship_links':linked,'ignored_files':ignored,'has_database':bool(summaries),
            'notice':'미리보기는 저장되지 않았습니다. 실제/가상·단위·출처와 등록 대상을 확인하세요. 앱 선박은 대량 생성하지 않습니다.'}
        upload.preview=result
        return result


def checked(ctx,upload):
    require(upload.preview and ctx.body.get('preview_hash')==upload.preview['preview_hash'] and digest(upload)==upload.preview['preview_hash'],
        '검증한 파일과 현재 업로드가 다릅니다. 다시 선택해 주세요.','VERSION_CONFLICT',409)


def commit(ctx):
    upload=owned(ctx)
    require(set(ctx.body)<={'id','preview_hash','map_existing'} and type(ctx.body.get('map_existing',False)) is bool,'등록 조건을 확인해 주세요.')
    with upload.lock:
        checked(ctx,upload);current(ctx,True)
        summaries,linked=database(ctx,upload.plan,True,ctx.body.get('map_existing',False))
        current(ctx)
        ctx.db.audit(ctx.user,'change','운항 자료 가져오기',ctx.body['id'],{'sha256':upload.preview['preview_hash'],'datasets':summaries,'linked':linked})
        return {'status':'completed','datasets':summaries,'linked_ships':linked,'notice':'DB 등록을 완료했습니다. 이미 같은 행은 보존했습니다. MRV는 연간 자료이며 공식 CII 입력 완비를 뜻하지 않습니다.'}


_reference_lock=threading.Lock()
def reference(ctx):
    upload=owned(ctx)
    require(set(ctx.body)<={'id','preview_hash','replace'} and type(ctx.body.get('replace',False)) is bool,'참조 연결 입력을 확인해 주세요.')
    with upload.lock,_reference_lock:
        checked(ctx,upload);current(ctx,True)
        require(upload.plan['catalog'] is not None,'검증한 참조 JSON이 없습니다.')
        target=reference_path();previous=hashlib.sha256(target.read_bytes()).hexdigest() if target.is_file() else None
        data,sha=load_catalog(upload.plan['catalog']);payload=upload.plan['catalog'].read_bytes()
        if previous==sha:
            return {'status':'unchanged','sha256':sha,'reference':catalog_summary(data,sha),'notice':'이미 같은 참조 파일이 연결되어 있습니다. 원본과 시각을 유지했습니다.'}
        require(previous==upload.preview['reference_previous_sha256'],'참조 파일이 바뀌었습니다. 다시 검증해 주세요.','VERSION_CONFLICT',409)
        require(previous is None or ctx.body.get('replace'),'기존 참조 파일 교체에 명시적으로 동의해 주세요.')
        # Imported files are managed in the persistent import directory only.
        # An administrator-specified external mount remains authoritative.
        managed=import_directory()/'navigation/catalog.json'
        require(target.resolve()==managed.resolve(),'서버가 외부 참조 경로를 사용 중입니다. 기존 마운트의 파일 교체는 서버 관리자 경로에서 처리해 주세요.')
        managed.parent.mkdir(parents=True,exist_ok=True)
        require(not managed.is_symlink(),'심볼릭 링크 경로에는 설치할 수 없습니다.')
        if previous and previous!=sha:
            backup=managed.with_name('catalog.previous.'+previous+'.json')
            if not backup.exists():backup.write_bytes(managed.read_bytes())
        temp=managed.with_name('catalog.'+str(uuid4())+'.tmp')
        try:temp.write_bytes(payload);os.replace(temp,managed)
        finally:
            if temp.exists():temp.unlink()
        ctx.db.audit(ctx.user,'change','항만 참조 가져오기',ctx.body['id'],{'sha256':sha,'previous_sha256':previous})
        return {'status':'completed','sha256':sha,'reference':catalog_summary(data,sha),'notice':'참조 파일을 연결했습니다. 원래 수집·수신 시각은 유지되며 실시간 수집·입항 승인을 뜻하지 않습니다.'}


def cancel(ctx):
    upload=owned(ctx)
    require(set(ctx.body)=={'id'},'취소 입력을 확인해 주세요.')
    with _guard,upload.lock:upload.temp.cleanup();_uploads.pop(ctx.body['id'],None)
    return {'cancelled':True}


def endpoint(action):
    def handle(ctx):
        try:return action(ctx)
        except ApiError:raise
        except ImportConflict as exc:
            raise ApiError(409,'VERSION_CONFLICT',str(exc)) from None
        except psycopg.errors.ForeignKeyViolation:
            raise ApiError(400,'MISSING_REFERENCE','연결할 출처·선박·항차 자료가 없습니다. 준비된 source_files.csv·vessels.csv·synthetic_voyages.csv를 함께 선택하거나 반입 ZIP을 사용해 주세요. 전체 DB 등록은 롤백되었습니다.') from None
        except ValidationError:
            raise ApiError(400,'INVALID_INPUT','참조 JSON의 형식·식별자·출처·시각을 확인해 주세요.') from None
        except HTTPException as exc:
            raise ApiError(exc.status_code,'IMPORT_REJECTED',str(exc.detail)) from None
        except (ValueError,UnicodeError,zipfile.BadZipFile,csv.Error) as exc:
            raise ApiError(400,'INVALID_INPUT',str(exc)[:300]) from None
        except psycopg.Error:
            raise ApiError(409,'IMPORT_REJECTED','행 중복·필수값·자료 형식·출처/선박 참조를 확인해 주세요. DB 등록은 전체 롤백되었습니다.') from None
        except OSError:
            raise ApiError(503,'IMPORT_UNAVAILABLE','서버 임시/참조 저장 공간과 접근 권한을 확인해 주세요.') from None
    return handle
