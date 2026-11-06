"""Explicit bounded collection, semantic review and offline guidance installation preparation."""
import argparse
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import subprocess

from backend.tools.navigation_guidance import DOCUMENTS, PortGuidance
from backend.tools.navigation_references import NavigationCatalog
from scripts.prepare_navigation_quality import download
from scripts.prepare_navigation_references import digest, dump
from scripts.navigation_bundle import read_bounded

LIMIT = 8*1024*1024


class MainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_main = False
        self.mains = 0
        self.skip = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == 'main':
            self.mains += 1
            self.in_main = True
        if self.in_main and tag in ('script','style','svg','nav'):
            self.skip += 1

    def handle_endtag(self, tag):
        if self.in_main and tag in ('script','style','svg','nav'):
            self.skip = max(0,self.skip-1)
        if tag == 'main':
            self.in_main = False

    def handle_data(self, value):
        if self.in_main and not self.skip:
            self.parts.append(value)


def main_text(data, key):
    parser=MainText();parser.feed(data.decode('utf-8-sig'))
    if parser.mains != 1:
        raise ValueError('Official page main section changed; review parser: '+key)
    text=' '.join(' '.join(parser.parts).split())
    title=DOCUMENTS[key][2]
    if title not in text:
        raise ValueError('Official page title changed: '+key)
    text=text[text.index(title):]
    # Keep the document and its displayed revision; exclude contact/footer chrome.
    for marker in ('Contact us','Other related content','Contact information'):
        if marker in text:
            text=text[:text.index(marker)]
    if not 50 <= len(text) <= 50000:
        raise ValueError('Unexpected official document size: '+key)
    return text.strip()


def fetch(base, directory):
    baseline=read_bounded(base)
    catalog=NavigationCatalog.model_validate_json(baseline)
    if catalog.version not in ('NAVIGATION-REFERENCES-1.3','NAVIGATION-REFERENCES-1.4'):
        raise ValueError('Use a preserved 1.3/1.4 baseline')
    directory.mkdir(parents=True,exist_ok=False)
    old={d.id:d for d in catalog.port_guidance}
    manifest={'base_sha256':digest(baseline),'sources':{}}
    urls=[row[1] for row in DOCUMENTS.values()]
    for key,(_,url,_,_) in DOCUMENTS.items():
        row={'url':url,'filename':key+'.html'}
        try:
            download(url,directory/row['filename'],allowed_urls=urls)
            data=(directory/row['filename']).read_bytes(); text=main_text(data,key)
            content_sha=digest(text.encode('utf-8'))
            row.update(status='captured',sha256=digest(data),bytes=len(data),content_sha256=content_sha,
                retrieved_at=datetime.now(timezone.utc).isoformat(),
                previous_content_sha256=old[key].content_sha256 if key in old else None,
                change='new_source' if key not in old else 'unchanged' if old[key].content_sha256==content_sha else 'content_changed')
            (directory/(key+'.txt')).write_text(text,encoding='utf-8')
        except (OSError,ValueError,subprocess.SubprocessError):
            row.update(status='failed',reason='Official source unavailable, parser changed, or size/time budget; TLS validation retained')
        manifest['sources'][key]=row
        dump(directory/'manifest.json',manifest)
    if any(r['status']!='captured' for r in manifest['sources'].values()):
        raise ValueError('Source capture incomplete; inspect manifest. Existing catalog preserved.')
    return manifest


def extract(key, text):
    facts=[]
    def fact(identifier,title,summary,scope,pattern,labels=(),units=(),berths=(),qualifiers=()):
        matches=list(re.finditer(pattern,text,re.I))
        if not matches or len({m[0] for m in matches})!=1:
            raise ValueError('Reviewed guidance pattern changed/ambiguous: '+key+'/'+identifier)
        match=matches[0]
        if any(not re.search(pattern,match[0],re.I) for pattern in qualifiers):
            raise ValueError('Guidance applicability qualifier changed: '+key+'/'+identifier)
        values=[{'label':label,'value':match.group(i+1).replace(',','.'),'unit':unit}
                for i,(label,unit) in enumerate(zip(labels,units))]
        facts.append({'id':identifier,'title':title,'summary':summary,'scope':scope,'values':values,
            'berth_ids':[DOCUMENTS[key][0]+':BERTH:'+b for b in berths],
            'evidence_text':match[0], 'locator':f'normalized-main-text:{match.start()}-{match.end()}'})
    number=r'([0-9]+(?:[.,][0-9]+)?)'
    if key=='gothenburg_draught':
        if 'mean sea level (MW)' not in text or 'density variations' not in text:
            raise ValueError('Fairway water-level/density qualification changed')
        routes=[('tor-north','Tor Harbour via the North Channel',r'Tor Harbour via the North Channel\s*\*?\)?\s*',()),
            ('tor-bay','Tor Bay',r'Tor Bay\s*',()),('arendal','Arendal Harbour',r'Arendal Harbour\s*',()),
            ('skandia','Skandia Harbour',r'Skandia Harbour\s*',()),
            ('skarvik','Skarvik Harbour · 510/519 수로',r'Skarvik Harbour\s*\(berths 510 and 519\)\s*',('510','519')),
            ('skarvik-rya','Skarvik–Rya 수로',r'Fairway Skarvik\s*[–-]\s*Rya\s*',()),
            ('rya-lindholmen','Rya–Lindholmen 수로',r'Fairway Rya\s*[–-]\s*Lindholmen\s*',()),
            ('lindholmen-freeport','Lindholmen–Free Port 수로',r'Fairway Lindholmen\s*[–-]\s*Free Port\s*',())]
        for identifier,title,pattern,berths in routes:
            fact(identifier,title,'평균해수면(MW) 기준의 게시 최대 흘수입니다. 선석 허용 흘수와 구분합니다.',
                '이름이 명시된 접근 수로에 한함. 실제 경로·현 수위·수밀도·선석 제한을 별도 확인해야 합니다.',
                pattern+number+r'\s*m\b',('수로 게시 최대 흘수',),('m',),berths)
        fact('fairway-berth-ukc','수로·선석 선저 여유 지침','수로와 선석의 게시 최소 UKC를 구분해 확인합니다.',
            '공식 페이지 표시 개정일 기준 지침. 선석별 더 구체적인 조건·회사 정책·동적 UKC를 대체하지 않습니다.',
            r'Minimum UKC in fairways are '+number+r'\s*m and at berths '+number+r'\s*m',
            ('수로 게시 최소 UKC','선석 게시 최소 UKC'),('m','m'))
    elif key=='gothenburg_tugs':
        fact('escort-tankers','유조선 호송 예선 조건','적재 유조선 및 특정 비가스프리 공선 유조선의 호송 예선 조건을 확인합니다.',
            'DWT 문턱·적재 상태·잔류물 인화점·가스프리 조건이 함께 필요합니다. DWT 후보만으로 적용하지 않습니다. 불활성 탱크를 가스프리로 취급하지 않습니다.',
            r'All loaded tankers over '+number+r'\s*000 dwt Tankers in ballast condition over '+number+r'\s*000 dwt with empty but not gasfree tanks \(residues with flashpoint below '+number+r'\s*degrees C\).*?Inerted tanks are not to be considered as [“"]gasfree[”"] tanks\.',
            ('적재 유조선 DWT 초과 문턱 · 천 DWT 단위','공선 유조선 DWT 초과 문턱 · 천 DWT 단위','잔류물 인화점 미만 기준'),('DWT','DWT','°C'))
        for value in facts[-1]['values'][:2]:
            value['value']=str(int(value['value'])*1000)
            value['label']=value['label'].replace(' · 천 DWT 단위','')
        fact('tug-booking','예선 사전 요청','선장 또는 대리인이 예선을 사전에 요청하는 절차를 확인합니다.',
            '게시 안내이며 예약·배정 확인서가 아닙니다.',r'Tug is ordered by master or agent in advance\.')
    elif key=='gothenburg_weather':
        fact('tanker-230-290','전장 230–290m 유조선 기상 조건','원문 지정 지점의 평균 풍속과 적재/공선별 시정을 확인합니다.',
            '해당 전장 구간 유조선. 풍속 지점 Måvholmsbådan. 범위 경계·실제 선종/적재 상태는 확인 대상입니다.',
            r'Tankers with LOA 230 m\s*[–-]\s*290 m Max wind:\s*'+number+r'\s*m/s.*?Min visibility loaded:\s*>\s*'+number+r'\s*NM Min visibility ballast:\s*>\s*'+number+r'\s*NM',
            ('게시 최대 평균풍속','적재 시 초과해야 하는 시정','공선 시 초과해야 하는 시정'),('m/s','NM','NM'),
            qualifiers=(r'average wind force at Måvholmsbådan',))
        fact('vlcc-daylight','전장 290m 이상 유조선 주간·기상 조건','입출항 주간 조건과 원문 지정 지점의 풍속·시정을 함께 확인합니다.',
            'VLCC에 한함. 예외 출항은 원문에 명시된 관계자 협의가 필요하며 자동 허용하지 않습니다.',
            r'Tankers with LOA equal to or exceeding 290 m.*?Arrival shall be done in daylight\..*?Max wind:\s*'+number+r'\s*m/s.*?Min visibility:\s*>\s*'+number+r'\s*NM',
            ('게시 최대 평균풍속','초과해야 하는 시정'),('m/s','NM'),
            qualifiers=(r'average wind force at Måvholmsbådan',r'only subject to consultation',r'Pilot/Captain',r'Port Captain and Pilot Area Manager'))
        fact('car-carrier-601','601번 자동차운반선 풍속 조건','입항·출항 풍속 기준과 예외 협의 조건을 구분해 확인합니다.',
            '601번, 전장 190m 초과 자동차운반선 또는 유사 풍압 면적 선박. 풍속 지점 Karet. 예외 출항 협의는 별도입니다.',
            r'Car carriers\s*[–-]\s*Berth 601.*?Arrival:\s*Max wind:\s*'+number+r'\s*m/s.*?Departure:\s*Max wind:\s*'+number+r'\s*m/s.*?Pilot Area Manager\.',
            ('입항 게시 최대 평균풍속','출항 게시 최대 평균풍속'),('m/s','m/s'),('601',),
            qualifiers=(r'LOA\s*>\s*190\s*m',r'average wind force at ["“]?Karet',r'only if consultation',r'Pilot/Master',r'Port Captain and Pilot Area Manager'))
    elif key=='gothenburg_control':
        fact('arrival-notification','입항 사전 신고','게시된 입항 사전 신고 시간을 확인합니다. 신고 완료를 승인으로 보지 않습니다.',
            'Gothenburg 입항 선박. 개별 예외·실제 신고 접수/승인은 항만 확인 대상입니다.',
            r'All vessels that are due to call at the Port of Gothenburg must issue notification at least '+number+r'\s*hours before arrival\.',('사전 신고 시간',),('h',))
        fact('works-confirmation','항만 공사·운영 상태 확인','항만 내 작업·공사의 현재 상태는 Port Control 확인이 필요합니다.',
            '현재 작업 여부나 운항 중단 공고를 이 문서에서 확보한 것은 아닙니다.',
            r'Do you need to know what kinds of work are under way in the port area\? Contact Port Control, which is best placed to answer such questions\.')
    elif key=='helsinki_regulations':
        fact('assigned-location','선석 배정·이동 허가','항만이 지정한 장소에 계류/정박하고 다른 장소로 이동할 때 허가 조건을 확인합니다.',
            'Helsinki 항만 규정. 실제 배정·허가 문서가 필요합니다.',
            r'The vessel shall be moored or anchored in the location indicated by the Port of Helsinki, and it may not be moved to another location without the Port[’\']s permission\.')
        fact('current-depth','현 위치의 수심 확인','선장이 선박 위치의 현재 수심을 확인해야 한다는 규정입니다.',
            '게시 수심이나 과거 측심을 현재 수심 확인으로 대체하지 않습니다.',
            r'The master of the vessel shall verify the current depth at the vessel[’\']s location\.')
        fact('ordered-assistance','도선·예선 추가 지시','필요한 예선 지원과 항만의 별도 예선/도선 지시 가능성을 확인합니다.',
            '크루즈 일반 안내의 예선 이용 가능 여부만으로 개별 지시를 생략하지 않습니다.',
            r'Tug assistance shall be used when mooring and unmooring the vessel, if necessary\. The Port of Helsinki may also order the vessel to use tug assistance and/or a pilot\.')
    elif key=='helsinki_cruise_navigation':
        fact('cruise-draft','크루즈 항만 구역별 게시 최대 흘수','West/South/Katajanokka의 게시 값을 구분해 확인합니다.',
            '크루즈 안내 범위. 접근 수로·현재 수심·개별 선석 제한/승인과 구분합니다.',
            r'Maximum Vessel[’\']s Draft\s*West Harbour\s*'+number+r'\s*m South Harbour\s*'+number+r'\s*m Katajanokka Harbour\s*'+number+r'\s*m',
            ('West Harbour 게시 최대 흘수','South Harbour 게시 최대 흘수','Katajanokka 게시 최대 흘수'),('m','m','m'))
        fact('cruise-pilot-notice','크루즈 도선·사전 통지 안내','도선 의무 전장 조건과 입출항 통지 시간을 함께 확인합니다.',
            '해당 크루즈 안내의 적용성·현행 도선 규정·실제 예약/배정을 별도 확인합니다.',
            r'Pilotage Advance Notice\s*Compulsory for vesels Loa\. over '+number+r'\s*m Arrival min\.?\s*'+number+r'\s*h\s*/\s*Departure min\.?\s*'+number+r'\s*h',
            ('전장 초과 문턱','입항 최소 사전 통지','출항 최소 사전 통지'),('m','h','h'))
    else:
        raise ValueError('Unknown official guidance')
    return facts


def candidate(base, raw):
    baseline=read_bounded(base); catalog=NavigationCatalog.model_validate_json(baseline)
    manifest_data=read_bounded(raw/'manifest.json',128*1024)
    manifest=json.loads(manifest_data)
    if manifest['base_sha256']!=digest(baseline) or set(manifest['sources'])!=set(DOCUMENTS):
        raise ValueError('Capture baseline/source list differs')
    docs=[]
    for key,(port,url,title,owner) in DOCUMENTS.items():
        row=manifest['sources'][key];path=raw/(key+'.html')
        if row.get('status')!='captured' or row['url']!=url or row['filename']!=key+'.html' or path.is_symlink() or path.stat().st_size>LIMIT:
            raise ValueError('Unsupported source identity/size')
        data=read_bounded(path);text=main_text(data,key)
        if digest(data)!=row['sha256'] or len(data)!=row['bytes'] or digest(text.encode('utf-8'))!=row['content_sha256']:
            raise ValueError('Source hash/size differs')
        displayed=re.search(r'Last updated\s+(\d{4}-\d{2}-\d{2})',text)
        effective=re.search(r'entered into force\s+(\d{1,2})\.(\d{1,2})\.(\d{4})',text)
        docs.append(PortGuidance(id=key,port_id=port,url=url,title=title,attribution=owner,raw_sha256=row['sha256'],
            content_sha256=row['content_sha256'],retrieved_at=row['retrieved_at'],
            displayed_updated_on=displayed[1] if displayed else None,
            effective_on=f'{effective[3]}-{int(effective[2]):02d}-{int(effective[1]):02d}' if effective else None,
            facts=extract(key,text)).model_dump(mode='json'))
    old={d.id:d.model_dump(mode='json') for d in catalog.port_guidance}
    changes=[]
    for doc in docs:
        previous=old.get(doc['id'])
        state='new_source' if not previous else 'content_changed' if doc['content_sha256']!=previous['content_sha256'] else 'unchanged'
        changes.append({'id':doc['id'],'change':state,'raw_changed':bool(previous and previous['raw_sha256']!=doc['raw_sha256']),
            'previous_content_sha256':previous['content_sha256'] if previous else None,
            'content_sha256':doc['content_sha256'],'facts_changed':bool(previous and previous['facts']!=doc['facts']),
            'previous_published_values':{f['id']:f['values'] for f in previous['facts']} if previous else None,
            'published_values':{f['id']:f['values'] for f in doc['facts']},
            'previous_displayed_updated_on':previous['displayed_updated_on'] if previous else None,
            'displayed_updated_on':doc['displayed_updated_on']})
    return {'base_sha256':digest(baseline),'manifest_sha256':digest(manifest_data),
        'review_required':True,'changes':changes,'documents':docs,
        'notice':'Review source scope, dates, values and qualifiers before preparing. Capture does not prove current applicability or approval.'}


def review(base, raw, output):
    if output.exists():
        raise ValueError('Use a new review output')
    output.parent.mkdir(parents=True,exist_ok=True)
    dump(output,candidate(base,raw))
    return {'review_file':str(output),'review_sha256':digest(output.read_bytes())}


def prepare(base, raw, reviewed, expected_sha, output):
    if output.exists() or output.is_symlink():
        raise ValueError('Use a new output and bounded regular review file')
    baseline=read_bounded(base)
    reviewed_data=read_bounded(reviewed)
    report=candidate(base,raw)
    if digest(baseline)!=report['base_sha256'] or digest(reviewed_data)!=expected_sha or json.loads(reviewed_data)!=report:
        raise ValueError('Exact review/inputs changed; repeat review before preparing')
    payload=NavigationCatalog.model_validate_json(baseline).model_dump(mode='json')
    payload.update(version='NAVIGATION-REFERENCES-1.4',generated_at=datetime.now(timezone.utc).isoformat(),
        port_guidance=report['documents'],guidance_review_sha256=expected_sha)
    result=NavigationCatalog.model_validate(payload)
    output.parent.mkdir(parents=True,exist_ok=True);dump(output,result.model_dump(mode='json'))
    return {'catalog_sha256':digest(output.read_bytes()),'documents':len(result.port_guidance),
        'facts':sum(len(d.facts) for d in result.port_guidance),'admission':'not_assessed'}


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    for name in ('fetch','review','prepare'):
        cmd=sub.add_parser(name);cmd.add_argument('--base',type=Path,required=True);cmd.add_argument('--raw-dir',type=Path,required=True)
        if name!='fetch':cmd.add_argument('--output',type=Path,required=True)
        if name=='prepare':
            cmd.add_argument('--review',type=Path,required=True);cmd.add_argument('--review-sha256',required=True)
    args=parser.parse_args()
    if args.command=='fetch':result=fetch(args.base,args.raw_dir)
    elif args.command=='review':result=review(args.base,args.raw_dir,args.output)
    else:result=prepare(args.base,args.raw_dir,args.review,args.review_sha256,args.output)
    print(json.dumps(result,ensure_ascii=True,indent=2))


if __name__=='__main__':main()
