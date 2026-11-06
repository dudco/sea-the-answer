"""Upload boundaries, preview rollback, idempotence and existing CSV compatibility."""
import base64
from copy import deepcopy
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import zipfile

import psycopg
import pytest

from api import operation_uploads as uploads,config
from api.errors import ApiError
from api.store import Workspace
from tools.operation_import import unpack,classify,daily_rows
from test_maritime_load import prepared
from test_maritime_migrations import postgres_dsn,apply_initial,apply_maritime,ROOT
from test_navigation_references import catalog_data


class Fake:
    def permit(self,user):
        if user['role']!='admin':raise ApiError(403,'FORBIDDEN','admin only')


@pytest.fixture(autouse=True)
def cleanup_uploads(monkeypatch):
    monkeypatch.setattr(uploads.security,'current_user',lambda db,request,guest:request)
    yield
    for upload in uploads._uploads.values():upload.temp.cleanup()
    uploads._uploads.clear()


def ctx(body=None,owner='admin-a',role='admin',db=None):
    user={'id':owner,'role':role,'must_change_password':False}
    return SimpleNamespace(body=body or {},user=user,request=user,guest={},db=db or Fake())


def post(context,action,body):
    context.body=body
    return uploads.endpoint(getattr(uploads,action))(context)


def upload(context,files):
    opened=post(context,'start',{'files':[{'name':name,'size':len(data)} for name,data in files]})
    for i,(_,data) in enumerate(files):
        for offset in range(0,len(data),uploads.CHUNK):
            post(context,'chunk',{'id':opened['id'],'index':i,'offset':offset,'data':base64.b64encode(data[offset:offset+uploads.CHUNK]).decode()})
    return opened['id']


def test_owner_sequence_permission_and_extra_fields_are_enforced():
    a=ctx();identifier=upload(a,[('daily.csv',b'abc')])
    with pytest.raises(ApiError) as error:post(ctx(owner='other'),'cancel',{'id':identifier})
    assert error.value.status==404
    with pytest.raises(ApiError):post(ctx(role='operator'),'start',{'files':[{'name':'x.csv','size':1}]})
    with pytest.raises(ApiError):post(a,'chunk',{'id':identifier,'index':0,'offset':0,'data':'YQ=='})
    with pytest.raises(ApiError):post(a,'start',{'files':[{'name':'../secret.csv','size':1}]})
    with pytest.raises(ApiError):post(a,'start',{'files':[{'name':'x.csv','size':True}]})


def test_upload_budgets_and_expired_staging_are_bounded():
    a=ctx()
    with pytest.raises(ApiError):post(a,'start',{'files':[{'name':'x.csv','size':uploads.MAX_INPUT+1}]})
    one=post(a,'start',{'files':[{'name':'x.csv','size':1}]})
    post(a,'start',{'files':[{'name':'y.csv','size':1}]})
    with pytest.raises(ApiError):post(a,'start',{'files':[{'name':'z.csv','size':1}]})
    uploads._uploads[one['id']].touched-=uploads.TTL+1
    with pytest.raises(ApiError):post(a,'cancel',{'id':one['id']})


@pytest.mark.parametrize('name',['../annual_reports.csv','/annual_reports.csv','folder\\file.csv','C:/file.csv'])
def test_zip_paths_are_never_extracted(tmp_path,name):
    path=tmp_path/'bad.zip'
    with zipfile.ZipFile(path,'w') as archive:
        item=zipfile.ZipInfo('safe.csv');item.filename=name
        archive.writestr(item,'payload')
    output=tmp_path/'out';output.mkdir()
    with pytest.raises(ValueError):unpack([('bad.zip',path)],output)
    assert not list(output.iterdir())


def test_unknown_csv_and_invalid_numbers_are_not_guessed(tmp_path):
    path=tmp_path/'unknown.csv';path.write_text('IMO,CO2\n9074729,100',encoding='utf-8')
    with pytest.raises(ValueError):classify([('unknown.csv',path)])
    directory,_=prepared(tmp_path/'prepared')
    path=directory/'summary.json';summary=json.loads(path.read_text());summary['rows']['vessels']=True;path.write_text(json.dumps(summary))
    with pytest.raises(ValueError):classify([('summary.json',path)])
    empty=tmp_path/'daily.csv';empty.write_text('ship,date,fuel,factor,distance,speed,fuelType\n')
    with pytest.raises(ValueError):daily_rows([empty])
    reserved=tmp_path/'reserved.zip'
    with zipfile.ZipFile(reserved,'w') as archive:archive.writestr('CON.csv','bad')
    output=tmp_path/'output';output.mkdir()
    with pytest.raises(ValueError):unpack([('reserved.zip',reserved)],output)


def test_reference_upload_is_owner_bound_and_does_not_need_db_or_execute_archive_files(tmp_path,monkeypatch):
    monkeypatch.setenv('HAEDAP_IMPORT_DIR',str(tmp_path/'installed'));monkeypatch.delenv('MARITIME_PORT_REFERENCES_PATH',raising=False)
    a=ctx();data=json.dumps(catalog_data(),default=str).encode()
    identifier=upload(a,[('catalog.json',data)])
    p=post(a,'preview',{'id':identifier})
    assert p['reference']['ports'] and not p['has_database']
    assert not (tmp_path/'installed').exists()
    with pytest.raises(ApiError):post(a,'reference',{'id':identifier,'preview_hash':'bad'})
    # No DB/user-lock fake: real reference installation is covered below.


@pytest.fixture
def database_context(postgres_dsn,monkeypatch):
    apply_initial(postgres_dsn);apply_maritime(postgres_dsn)
    with psycopg.connect(postgres_dsn) as connection:
        for filename in ('20261013020000_capacity_candidates.sql','20261021000000_user_password_change.sql'):
            connection.execute((ROOT/'migrations'/filename).read_text(encoding='utf-8').split('-- migrate:up',1)[1].split('-- migrate:down',1)[0])
    monkeypatch.setenv('DATABASE_URL',postgres_dsn);monkeypatch.delenv('MARITIME_DATA_DATABASE_URL',raising=False)
    with Workspace(postgres_dsn) as db:
        admin=db.save_user({'id':'fixture','role':'admin'},{'username':'test-import','name':'test','role':'admin','password':'Temporary-test-only-2026'})
        db.run('UPDATE users SET must_change_password=false WHERE id=%s',(admin['id'],))
        yield ctx(owner=admin['id'],db=db)


def test_prepared_preview_rolls_back_commit_is_idempotent_and_preserves_app_identity(database_context,tmp_path):
    a=database_context;directory,counts=prepared(tmp_path/'prepared')
    files=[(p.name,p.read_bytes()) for p in directory.iterdir()]
    identifier=upload(a,files);p=post(a,'preview',{'id':identifier})
    assert a.db.one('SELECT count(*) AS n FROM maritime_data.vessels')['n']==0
    result=post(a,'commit',{'id':identifier,'preview_hash':p['preview_hash'],'map_existing':True})
    assert sum(r['new'] for r in result['datasets'])==2
    assert a.db.one('SELECT count(*) AS n FROM ships')['n']==0
    again=post(a,'commit',{'id':identifier,'preview_hash':p['preview_hash']})
    assert sum(r['new'] for r in again['datasets'])==0
    a.db.run("UPDATE maritime_data.source_files SET filename='changed' WHERE source_id='source-1'")
    with pytest.raises(ApiError):post(a,'commit',{'id':identifier,'preview_hash':p['preview_hash']})
    assert a.db.one('SELECT filename FROM maritime_data.source_files')['filename']=='changed'


def test_late_fk_failure_rolls_back_whole_import(database_context,tmp_path):
    a=database_context;directory,_=prepared(tmp_path/'prepared',dangling_issue=True)
    identifier=upload(a,[(p.name,p.read_bytes()) for p in directory.iterdir()])
    with pytest.raises(ApiError):post(a,'preview',{'id':identifier})
    assert a.db.one('SELECT count(*) AS n FROM maritime_data.source_files')['n']==0
    assert a.db.one('SELECT count(*) AS n FROM maritime_data.vessels')['n']==0


def test_daily_csv_uses_existing_validation_and_same_file_can_be_retried(database_context):
    a=database_context
    a.db.change(a.user,'ship.save',{'id':'ship-a','name':'Test','type':'Bulk carrier','dwt':1000,'version':0})
    content=b'ship,date,fuel,factor,distance,speed,fuelType\nship-a,2025-01-01,10,3.114,100,12,LSFO\n'
    identifier=upload(a,[('daily.csv',content)]);p=post(a,'preview',{'id':identifier})
    assert p['datasets'][0]['kind']=='daily' and a.db.one('SELECT count(*) AS n FROM operations')['n']==0
    post(a,'commit',{'id':identifier,'preview_hash':p['preview_hash']})
    again=post(a,'commit',{'id':identifier,'preview_hash':p['preview_hash']})
    assert again['datasets'][0]['unchanged']==1 and a.db.one('SELECT count(*) AS n FROM operations')['n']==1


def test_reference_install_and_compare_and_swap_preserve_source_time(database_context,tmp_path,monkeypatch):
    a=database_context;monkeypatch.setenv('HAEDAP_IMPORT_DIR',str(tmp_path/'installed'));monkeypatch.delenv('MARITIME_PORT_REFERENCES_PATH',raising=False)
    identifier=upload(a,[('catalog.json',json.dumps(catalog_data(),default=str).encode())]);p=post(a,'preview',{'id':identifier})
    post(a,'reference',{'id':identifier,'preview_hash':p['preview_hash']})
    again=post(a,'reference',{'id':identifier,'preview_hash':p['preview_hash']})
    assert again['status']=='unchanged'
    target=uploads.reference_path();assert json.loads(target.read_text())['generated_at']==catalog_data()['generated_at']
    target.write_text('{}')
    with pytest.raises(ApiError):post(a,'reference',{'id':identifier,'preview_hash':p['preview_hash'],'replace':True})
    assert target.read_text()=='{}'
