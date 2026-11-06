"""Typed CSV staging and append-only imports into the existing operation schemas."""
import csv
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
from pathlib import Path
import stat
import zipfile

from psycopg import sql
from psycopg.types.json import Jsonb

from .capacity_data import HEADERS, prepared_references
from .data_contract import FIELDS
from .navigation_references import NavigationCatalog
from .port_reference import valid_imo

ORDER=('source_files','vessels','synthetic_voyages','annual_reports','synthetic_noon','quality_issues','capacity_candidates')
KEYS={name:fields[0][0] for name,fields in FIELDS.items()}
KEYS['capacity_candidates']='vessel_id'
CAPACITY_COLUMNS=('vessel_id','imo_number','candidate_dwt_t','capacity_status','source_file_sha256','source_filename','source_row','source_json')
DAILY_REQUIRED={'ship','date','fuel','factor','distance','speed','fuelType'}
DAILY_COLUMNS=DAILY_REQUIRED|{'position','voyage','draft','weather','engineHours','note','sample','id','version'}
MAX_EXPANDED=160*1024*1024


class ImportConflict(ValueError):
    pass


def csv_type(path):
    with path.open(encoding='utf-8-sig',newline='') as stream:
        fields=next(csv.reader(stream),[])
    normalized=[v.strip() for v in fields]
    if not fields or len(set(normalized))!=len(fields):raise ValueError('CSV의 빈 헤더·중복 열 이름을 확인해 주세요.')
    if DAILY_REQUIRED.issubset(normalized):
        if set(normalized)-DAILY_COLUMNS:raise ValueError('일별 서식에 알 수 없는 열이 있습니다. MRV 보고연도·연간 합계와 혼합할 수 없습니다.')
        return 'daily',normalized
    if fields==HEADERS:return 'capacity_candidates',fields
    for name,contract in FIELDS.items():
        if fields==[f[0] for f in contract]:return name,fields
    raise ValueError('지원하지 않는 CSV 서식입니다. 일별 운항 서식 또는 준비된 MRV/Noon CSV 묶음을 선택해 주세요. 원시 MRV 열·단위는 자동 추측하지 않습니다.')


def unpack(upload_files,directory):
    """Read selected entries only. Never extract/execute arbitrary archive paths."""
    extracted=[];total=0;ignored=0
    def write(name,data):
        nonlocal total
        stem=Path(name).name.split('.')[0].rstrip(' .').upper()
        if stem in {'CON','PRN','AUX','NUL','CONIN$','CONOUT$',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]} or any(ord(c)<32 for c in name):
            raise ValueError('서버에서 안전하게 저장할 수 없는 파일 이름입니다.')
        total+=len(data)
        if total>MAX_EXPANDED:raise ValueError('해제한 자료가 160MiB를 넘습니다.')
        folder=directory/str(len(extracted));folder.mkdir()
        target=folder/Path(name).name
        target.write_bytes(data);extracted.append((name,target))
    for name,path in upload_files:
        if name.lower().endswith('.zip'):
            with zipfile.ZipFile(path) as archive:
                entries=archive.infolist()
                if len(entries)>64:raise ValueError('ZIP은 최대 64개 항목까지 지원합니다.')
                names=set();declared=0
                for item in entries:
                    parts=item.filename.split('/')
                    if item.filename.startswith('/') or '\\' in item.orig_filename or ':' in item.filename or '..' in parts or len(item.filename)>240:
                        raise ValueError('ZIP 경로에 허용되지 않는 항목이 있습니다.')
                    if item.filename in names or '\x00' in item.orig_filename or stat.S_ISLNK(item.external_attr>>16) or item.flag_bits&1:
                        raise ValueError('중복·심볼릭 링크·암호화 ZIP은 지원하지 않습니다.')
                    if item.compress_type not in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED):raise ValueError('표준 ZIP 압축 방식을 사용해 주세요.')
                    names.add(item.filename);declared+=item.file_size
                    if declared>MAX_EXPANDED:raise ValueError('ZIP 해제 크기가 160MiB를 넘습니다.')
                    if item.file_size>1024*1024 and item.file_size>max(1,item.compress_size)*250:raise ValueError('ZIP 압축률이 제한을 초과합니다.')
                    if item.is_dir():continue
                    base=parts[-1]
                    if base.lower().endswith('.csv') or base in ('catalog.json','summary.json'):
                        with archive.open(item) as stream:data=stream.read(MAX_EXPANDED-total+1)
                        write(base,data)
                    else:ignored+=1
        elif name.lower().endswith(('.csv','.json')):write(name,path.read_bytes())
        else:raise ValueError('CSV·JSON·ZIP 파일을 선택해 주세요.')
    if not extracted:raise ValueError('등록할 운항 자료가 없습니다.')
    return extracted,ignored


def classify(files):
    tables={};daily=[];catalog=None;summary=None
    for name,path in files:
        if path.suffix.lower()=='.csv':
            kind,fields=csv_type(path)
            if kind=='daily':daily.append(path);continue
            if kind in tables:raise ValueError('같은 종류의 준비 CSV는 한 번에 하나만 선택해 주세요: '+kind)
            tables[kind]=path
            if kind=='capacity_candidates':prepared_references(path)
            else:
                numeric={i for i,f in enumerate(FIELDS[kind]) if f[1]=='numeric'}
                with path.open(encoding='utf-8-sig',newline='') as stream:
                    reader=csv.reader(stream);next(reader)
                    for number,row in enumerate(reader,2):
                        if number>250002 or len(row)!=len(fields):raise ValueError(f'{name}: {number}행의 열 수·행 제한을 확인해 주세요.')
                        if kind=='vessels':
                            vessel=dict(zip(fields,row))
                            if vessel['data_origin']=='REAL' and (not valid_imo(vessel['imo_number']) or vessel['vessel_id']!='REAL:IMO:'+vessel['imo_number']):
                                raise ValueError('실제 선박의 IMO·식별자가 올바르지 않습니다.')
                            if vessel['data_origin']=='SYNTHETIC' and not vessel['vessel_id'].startswith('SYN:'):raise ValueError('가상 선박은 SYN 식별자가 필요합니다.')
                        for i in numeric:
                            try:valid=not row[i] or (Decimal(row[i]).is_finite() and Decimal(row[i])>=0)
                            except InvalidOperation:valid=False
                            if not valid:raise ValueError(f'{name}: 수량은 음수가 아닌 유한한 숫자 또는 결측값이어야 합니다.')
        else:
            if path.stat().st_size>8*1024*1024:raise ValueError('JSON 파일은 8MiB 이하여야 합니다.')
            data=json.loads(path.read_text(encoding='utf-8-sig'))
            if isinstance(data,dict) and str(data.get('version','')).startswith('NAVIGATION-REFERENCES-'):
                if catalog is not None:raise ValueError('참조 카탈로그는 하나만 선택해 주세요.')
                if path.stat().st_size>8*1024*1024:raise ValueError('참조 파일은 8MiB 이하여야 합니다.')
                NavigationCatalog.model_validate(data);catalog=path
            elif name=='summary.json' and isinstance(data,dict) and isinstance(data.get('rows'),dict):
                summary=data['rows']
                if set(summary)!=set(FIELDS) or any(type(v) is not int or v<0 for v in summary.values()):raise ValueError('준비 summary.json의 테이블·행 수를 확인해 주세요.')
            else:raise ValueError('지원하는 JSON은 항만 참조 catalog.json 또는 준비 summary.json입니다.')
    if not tables and not daily and catalog is None:raise ValueError('등록할 운항 자료가 없습니다.')
    return {'tables':tables,'daily':daily,'catalog':catalog,'expected':summary}


def stage_tables(connection,plan):
    summaries=[];stages={}
    for name in ORDER:
        if name not in plan['tables']:continue
        path=plan['tables'][name]
        columns=list(CAPACITY_COLUMNS) if name=='capacity_candidates' else [f[0] for f in FIELDS[name]]
        stage='import_'+name
        if connection.execute('SELECT to_regclass(%s)',('maritime_data.'+name,)).fetchone()['to_regclass'] is None:
            raise ValueError('서버의 해사 DB migration을 먼저 적용해 주세요.')
        connection.execute(sql.SQL('CREATE TEMP TABLE {} (LIKE maritime_data.{} INCLUDING ALL) ON COMMIT DROP').format(sql.Identifier(stage),sql.Identifier(name)))
        cols=sql.SQL(',').join(map(sql.Identifier,columns))
        if name=='capacity_candidates':
            rows,digest=prepared_references(path)
            with connection.cursor().copy(sql.SQL('COPY {} ({}) FROM STDIN').format(sql.Identifier(stage),cols)) as copy:
                for row in rows:copy.write_row(tuple(Jsonb(row[c]) if c=='source_json' else row[c] for c in columns))
        else:
            with connection.cursor().copy(sql.SQL("COPY {} ({}) FROM STDIN WITH (FORMAT CSV,HEADER TRUE,NULL '')").format(sql.Identifier(stage),cols)) as copy:
                with path.open('rb') as stream:
                    while block:=stream.read(1024*1024):copy.write(block)
        count=connection.execute(sql.SQL('SELECT count(*) AS n FROM {}').format(sql.Identifier(stage))).fetchone()['n']
        if plan['expected'] is not None and name!='capacity_candidates' and plan['expected'].get(name)!=count:
            raise ValueError('summary.json과 CSV의 행 수가 다릅니다: '+name)
        key=KEYS[name]
        values=lambda alias:sql.SQL(',').join(sql.SQL('{}.{}').format(sql.Identifier(alias),sql.Identifier(c)) for c in columns)
        conflict=connection.execute(sql.SQL('SELECT 1 FROM {} s JOIN maritime_data.{} d USING({}) WHERE ROW({}) IS DISTINCT FROM ROW({}) LIMIT 1').format(
            sql.Identifier(stage),sql.Identifier(name),sql.Identifier(key),values('s'),values('d'))).fetchone()
        if conflict:raise ImportConflict('기존 식별자와 내용이 다른 행이 있습니다. 덮어쓰지 않았습니다: '+name)
        existing=connection.execute(sql.SQL('SELECT count(*) AS n FROM {} s JOIN maritime_data.{} d USING({})').format(sql.Identifier(stage),sql.Identifier(name),sql.Identifier(key))).fetchone()['n']
        summaries.append({'kind':name,'rows':count,'new':count-existing,'unchanged':existing,'storage':'maritime_data.'+name})
        stages[name]=(stage,columns)
    return stages,summaries


def apply_tables(connection,stages):
    # Validate FK/origin consistency using the same INSERT constraints during
    # preview (rolled back) and commit. There are no user-controlled SQL names.
    for name,(stage,columns) in stages.items():
        cols=sql.SQL(',').join(map(sql.Identifier,columns))
        connection.execute(sql.SQL('INSERT INTO maritime_data.{} ({}) SELECT {} FROM {} ON CONFLICT ({}) DO NOTHING').format(
            sql.Identifier(name),cols,cols,sql.Identifier(stage),sql.Identifier(KEYS[name])))
    if stages:
        bad=connection.execute("""SELECT EXISTS(SELECT FROM maritime_data.annual_reports a JOIN maritime_data.vessels v USING(vessel_id)
            JOIN maritime_data.source_files s USING(source_id) WHERE v.data_origin<>'REAL' OR s.data_origin<>'REAL') OR
            EXISTS(SELECT FROM maritime_data.synthetic_noon n JOIN maritime_data.vessels v USING(vessel_id)
            JOIN maritime_data.source_files s USING(source_id) WHERE v.data_origin<>'SYNTHETIC' OR s.data_origin<>'SYNTHETIC') OR
            EXISTS(SELECT FROM maritime_data.synthetic_noon n JOIN maritime_data.synthetic_voyages v USING(voyage_id) WHERE n.vessel_id<>v.vessel_id) OR
            EXISTS(SELECT FROM maritime_data.quality_issues q WHERE q.record_id IS NOT NULL AND NOT EXISTS(SELECT FROM maritime_data.annual_reports a WHERE a.record_id=q.record_id)
                AND NOT EXISTS(SELECT FROM maritime_data.synthetic_noon n WHERE n.record_id=q.record_id)) OR
            EXISTS(SELECT FROM maritime_data.capacity_candidates c JOIN maritime_data.vessels v USING(vessel_id) WHERE v.data_origin<>'REAL' OR c.imo_number<>v.imo_number) AS bad""").fetchone()['bad']
        if bad:raise ValueError('실제/가상·출처·항차의 연결이 일치하지 않습니다.')


def daily_rows(paths):
    result=[];seen=set()
    for path in paths:
        with path.open(encoding='utf-8-sig',newline='') as stream:
            reader=csv.DictReader(stream);reader.fieldnames=[v.strip() for v in reader.fieldnames or []]
            for i,row in enumerate(reader,1):
                if i>1000 or None in row or any(v is None for v in row.values()):raise ValueError('일별 CSV는 파일당 1,000행·일정한 열 수가 필요합니다.')
                row={k:v.strip() for k,v in row.items()}
                for key in ('fuel','factor','distance','speed','draft','engineHours'):
                    value=row.get(key,'').strip();row[key]=float(value) if value else None
                if 'version' in row:row['version']=int(row['version'])
                if 'sample' in row:
                    if row['sample'].lower() not in ('true','false','1','0',''):raise ValueError('sample은 true/false로 지정해 주세요.')
                    row['sample']=row['sample'].lower() in ('true','1')
                key=(row.get('ship'),row.get('date'))
                if key in seen:raise ValueError('파일에 동일 선박·일자의 일별 기록이 중복됩니다.')
                seen.add(key);result.append(row)
    if paths and not result:raise ValueError('일별 CSV에 등록할 기록이 없습니다.')
    return sorted(result,key=lambda r:(r.get('ship',''),r.get('date','')))
