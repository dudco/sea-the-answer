"""Source names and inventory requests, separated from definitions and calculations."""
import re
import unicodedata

ALIASES={
    'ais':r'(?<![a-z0-9])ais(?![a-z0-9])|선박\s*자동\s*식별(?:\s*시스템)?',
    'mrv':r'(?<![a-z0-9])mrv(?![a-z0-9])',
    'dwt':r'(?<![a-z0-9])dwt(?![a-z0-9])|재화\s*중량',
    'noon':r'(?<![a-z0-9])(?:synthetic\s+)?noon(?![a-z0-9])|합성\s*운항|가상\s*운항',
    'operations':r'일별\s*운항|운항\s*(?:데이터|자료|기록)|daily\s*(?:operations?|records?)',
    'documents':r'문서|매뉴얼|documents?|manuals?',
    'ports':r'항만|항구|선석|\bports?\b|\bberths?\b',
}
DATASETS=tuple(ALIASES)


def sources(question):
    q=unicodedata.normalize('NFKC',question).casefold()
    return [key for key,pattern in ALIASES.items() if re.search(pattern,q)]


def inventory_request(question):
    if not isinstance(question,str):return []
    q=unicodedata.normalize('NFKC',question).casefold().strip()
    if re.search(r'(?:선택|지정|해당|이|그)\s*(?:한)?\s*문서|selected\s+documents?',q):return []
    # A source mention alone never turns a procedure, device fault, formula or
    # record mutation into an inventory request.
    if re.search(r'정의|뜻|원리|기능|뭐야|무엇인가|어떻게|사용법|방법|절차|규정|계산|등급|산식|구조|수신기|장치|오류|고장|날씨|기상|실시간\s*위치|없으면|있으면|예측|원인|what\s+is|how\s+to|definition|receiver|fault|regulation|formula|weather|forecast',q):return []
    if re.search(r'(?:등록|삭제|수정|저장|계산|추적)\s*(?:해|해줘|해주)|\b(?:delete|update|insert|track|calculate)\b|아니라|말고|\bnot\b',q):return []
    found=sources(q)
    if 'noon' in found and 'operations' in found:found.remove('operations')
    status=bool(re.search(r'있|없|등록|보유|확보|연결|현황|출처|수집|언제|몇|얼마나|종류|목록|실시간|최신|available|loaded|status|source|when|how many|\bhave\b|is there',q))
    resource=bool(found or re.search(r'자료|데이터|data|information',q))
    if status and resource:
        if found:return found
        # An unknown topic such as weather is not a request for every dataset.
        korean_generic=r'(?:현재|지금|서버|시스템|앱|여기|우리|해사|에|서|에서|어떤|어느|무슨|사용할|사용|가능한|가능|쓸|볼|수|있는지|있는|자료|데이터|들|등록된|등록|되어|돼|보유한|보유|확보한|수집한|전체|종류|목록|뭐|무엇|이|가|는|을|를|도|좀|있어|있나요|있나|없어|궁금해|알려줘|보여줘|확인해줘|[\s?.!])+'
        english_words=set(re.sub(r'[^a-z ]',' ',q).split())
        english_generic=english_words and english_words <= {'what','which','data','datasets','information','do','we','have','is','there','any','available','loaded','on','the','server','show','me','please','all','list','sources','of'}
        if re.fullmatch(korean_generic,q) or english_generic:return list(DATASETS)
        return []
    # Broad information requests are bounded to a source + resource + read verb;
    # extra topics (e.g. "AIS receiver fault information") are not discarded.
    alias='(?:'+ '|'.join(ALIASES[k] for k in DATASETS if k!='documents')+')'
    noun=r'(?:데이터|자료|정보|data|information|snapshot)'
    read=r'(?:(?:알려|보여)\s*(?:줘|주세요|줄래)|(?:조회|확인|정리|설명)해\s*(?:줘|주세요))'
    korean=rf'{alias}\s*(?:관련(?:된)?|에\s*대한)?\s*{noun}(?:를|을|도|는|은)?\s*(?:(?:좀|간단히|한\s*번)\s*)*{read}[.!?]*'
    english=rf'(?:please\s+)?(?:show|give|tell)(?:\s+me)?\s+(?:(?:about|the)\s+)?{alias}\s+(?:related\s+)?{noun}(?:\s+please)?[.!?]*'
    inverse=rf'(?:please\s+)?(?:show|give|tell)(?:\s+me)?\s+{noun}\s+(?:about|on)\s+{alias}[.!?]*'
    return found if found and any(re.fullmatch(p,q) for p in (korean,english,inverse)) else []
