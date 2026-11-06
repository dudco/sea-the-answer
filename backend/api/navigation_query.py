"""Narrow question-to-reference route. No model-generated identities or entry decisions."""
import re
import unicodedata
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from tools.port_reference import valid_imo
from . import navigation_service as service
from .navigation_intent import LIMIT, parse_conditions, select_results, describe
from .errors import ApiError, require
from .validation import text, utc_now

ALIASES = {
    "SEGOT": ("Gothenburg", "Göteborg", "Goteborg", "예테보리", "괴테보리", "고텐버그", "SEGOT"),
    "FIHEL": ("Helsinki", "헬싱키", "FIHEL"),
    "DKAAL": ("Aalborg", "Alborg", "올보르", "올보르그", "알보르", "DKAAL"),
}
OTHER_PORT_NAMES = ("부산", "울산", "인천", "광양", "상하이", "싱가포르", "로테르담", "함부르크",
                    "Busan", "Ulsan", "Incheon", "Shanghai", "Singapore", "Rotterdam", "Hamburg", "Turku", "투르쿠")


def norm(value):
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def mentions(question, label):
    return bool(re.search(r"(?<![0-9a-z])" + re.escape(norm(label)) + r"(?![0-9a-z])", norm(question)))


def document_question(question):
    return bool(re.search(r"문서만|문서\s*기반|규정|매뉴얼|정의|뜻|번역|절차|방법|하는\s*법|어떻게|서류|제출|준비물|체크리스트|보고할|보고\s*(?:사항|내용|대상|방법)|translate|definition|regulation|manual|what\s+is|how\s+to|documents?\s+(?:required|needed)|report\s+before", question, re.I))


def is_navigation_question(question):
    if not isinstance(question, str):
        return False
    if document_question(question):
        return False
    entry = re.search(r"입항|접안|정박|들어가|들어갈|들어오|들어올|enter|berth|dock", question, re.I)
    if re.search(r"항구|항만|선석|\bports?\b|\bberths?\b", question, re.I):
        entry = entry or re.search(r"이용|받아줄|수용|갈\s*수|accommodate|use|fit|공개\s*(?:수치|제한)|자료\s*부족|" + LIMIT, question, re.I)
    request = re.search(r"가능|수\s*있|어디|어느\s*(?:항구|항만|선석)|(?:무엇|뭘|어떤|확인할).*?(?:조건|확인)|확인해야|\bcan\b|\bcould\b|\bwhich\s+(?:ports?|berths?)\b|what.*(?:check|conditions)", question, re.I)
    return bool(entry and (request or re.search(r"알려|보여|조회|비교|list|show|only", question, re.I)))


def is_followup(question):
    if not isinstance(question, str) or len(question) > 160 or document_question(question):
        return False
    if is_navigation_question(question) and re.search(r"우리|선박|입항|접안|정박|들어|\b(?:ship|vessel|imo|enter|dock)\b", question, re.I):
        return False
    # Only bounded target/condition followups; unrelated conversation still uses RAG.
    target = any(mentions(question, a) for names in ALIASES.values() for a in names) or any(mentions(question, a) for a in OTHER_PORT_NAMES)
    target = target or bool(re.search(r"\b(?:LHB|LHC|LHD|ERA|EKL|EPL|EMA|EO1)\b|(?:선석|berth)\s+[a-z0-9-]+", question, re.I))
    condition = bool(re.search(LIMIT + r"|공개\s*(?:수치|제한)|자료\s*부족", question, re.I))
    return bool((target or condition) and re.search(r"^(?:그럼|그러면|그중|그 중|그렇다면|then|what about)\b|^(?:그럼|그러면|그중|그렇다면)", question, re.I))


def previous_navigation(db, owner, context, ship):
    value = context.get("previousQueryId")
    try:
        if not isinstance(value, str) or str(UUID(value)) != value.lower():
            return None
    except ValueError:
        return None
    row = db.one("""SELECT q.response FROM queries q JOIN query_owner o ON o.id=q.id
        WHERE q.id=%s AND o.owner=%s""", (value, owner))
    answer = row["response"] if row else None
    nav = answer.get("navigation", {}) if isinstance(answer, dict) else {}
    prior = nav.get("context", {})
    if not (answer and answer.get("task") == "navigation" and nav.get("kind") == "port-reference"
            and nav.get("status") in ("reference_only", "no_reference_matches")
            and prior.get("ship") == ship["id"] == context.get("ship")
            and prior.get("ship_version") == ship.get("version") and prior.get("imo_number") == imo_of(ship)
            and isinstance(nav.get("selection", {}).get("port_ids"), list)):
        return None
    return nav


def imo_of(ship):
    return re.sub(r"^IMO\s*", "", str(ship.get("imo", "")).strip(), flags=re.I)


def select_ship(question, ships, context):
    ids = list(dict.fromkeys(re.findall(r"(?<!\d)\d{7}(?!\d)", question)))
    names = [s for s in ships if len(s.get("name", "")) >= 3 and mentions(question, s["name"])]
    if ids:
        if len(ids) != 1 or not valid_imo(ids[0]):
            return None
        candidates = [s for s in ships if imo_of(s) == ids[0]]
        if len(candidates) > 1:
            candidates = [s for s in candidates if s in names]
        return candidates[0] if len(candidates) == 1 else None
    if names:
        return names[0] if len(names) == 1 else None
    if re.search(r"(?<![0-9a-z])imo(?![a-z])", question, re.I):
        return None
    # An explicitly named but unknown ship must not fall back to a different selected ship.
    named = re.search(r"([가-힣a-z0-9_-]{2,30}호)\s*(?:가|는|의|이|선박)?", question, re.I)
    if named and named[1] not in ("우리호", "해당호"):
        return None
    named_en = re.search(r"\b(?:ship|vessel)\s+(?:named\s+)?([a-z][a-z0-9_-]{1,30})", question, re.I)
    if named_en and named_en[1].casefold() not in {"can","could","may","will","should","is","has","with","enter","berth","dock","fit","use","be","to","at"}:
        return None
    subject_en = re.search(r"\b(?:can|could|may)\s+(.{1,80}?)\s+(?:enter|berth|dock|use|fit)\b", question, re.I)
    if subject_en and norm(subject_en[1]) not in {"our ship", "our vessel", "my ship", "my vessel", "the ship", "the vessel", "this ship", "this vessel", "we", "it"}:
        return None
    subject_ko = re.search(r"(?:^|\s)([가-힣a-z0-9_-]{2,40})(?:이|가|은|는)\s*.{0,40}?(?:입항|접안|정박|들어|이용|수용)", question, re.I)
    if subject_ko and subject_ko[1] not in {"선박", "우리배", "우리선박", "본선", "해당선박", "현재선박", "이선박", "이배", "항구", "항만"}:
        return None
    if context.get("ship"):
        return next((s for s in ships if s["id"] == context["ship"]), None)
    actual = [s for s in ships if not s.get("sample")]
    return actual[0] if len(actual) == 1 else None


def select_ports(question, catalog):
    selected = [p for p in catalog.ports if any(mentions(question, name) for name in ALIASES.get(p.unlocode, (p.name,p.unlocode)))]
    unknown = [name for name in OTHER_PORT_NAMES if mentions(question, name)]
    generic = {"어디", "어느", "어떤", "우리", "현재", "해당", "다른", "가능한", "선석", "항구", "항만", "여기", "which", "any", "all", "safely", "today", "now", "ports", "port", "in", "to", "the", "a", "with", "using", "where"}
    candidates = re.findall(r"([가-힣a-z]{2,20})(?:항구|항만|항)(?:으로|에서|에|은|는|이|가|을|를|도|\s|[?.]|$)", question, re.I)
    candidates += re.findall(r"(?:^|\s)([가-힣a-z]{2,20})(?:에|으로)\s*(?:입항|접안|정박|들어)", question, re.I)
    candidates += re.findall(r"\b(?:enter|at|into)\s+(?:the\s+)?(?:port\s+of\s+)?([a-z]+)", question, re.I)
    aliases = {norm(a) for values in ALIASES.values() for a in values}
    for value in candidates:
        if re.search(r"입항|접안|가능|선박|우리|있는", value):
            continue
        if norm(value) not in generic | aliases and value not in unknown:
            unknown.append(value)
    if unknown:
        return [], None, "unsupported_port", list(dict.fromkeys(unknown))
    explicit = re.findall(r"(?:선석|\bberth\b)\s+([0-9a-z-]{1,20})(?![0-9a-z-])", question, re.I)
    explicit = [v for v in explicit if v.casefold() not in {"only", "with", "limit", "limits", "at", "in", "is", "can", "draft", "draught", "length", "beam"}]
    if not explicit:
        explicit = [b.label for p in catalog.ports for b in p.berths
                    if re.search(r"[a-z]", b.label, re.I) and mentions(question, b.label)]
    explicit = list(dict.fromkeys(label.upper() for label in explicit))
    if explicit:
        matches = [(p, b) for p in (selected or catalog.ports) for b in p.berths if b.label in explicit]
        if len(explicit) != 1 or len(matches) != 1:
            return selected, None, "unsupported_berth", explicit
        return [matches[0][0]], matches[0][1].berth_id, None, []
    if not selected and re.search(r"이\s*항구|해당\s*항구|이\s*선석|that\s+port|this\s+port", question, re.I):
        return [], None, "needs_port", []
    return selected or list(catalog.ports), None, None, []


def try_answer(ctx):
    payload = ctx.body
    raw = payload.get("question")
    followup = is_followup(raw)
    if payload.get("task", "auto") != "auto" or not (is_navigation_question(raw) or followup):
        return None
    question = text(raw, "질문", 2000)
    language = payload.get("language", "auto")
    require(language in ("auto", "ko", "en"), "언어를 확인해 주세요.")
    language = ("ko" if re.search(r"[가-힣]", question) else "en") if language == "auto" else language
    require(payload.get("mode", "extractive") in ("extractive", "llm"), "답변 모드를 확인해 주세요.")
    require(payload.get("filter", "all") in ("all", "imo", "manual"), "문서 필터를 확인해 주세요.")
    context = payload.get("context") or {}
    require(isinstance(context, dict), "선박 문맥을 확인해 주세요.")
    require(context.get("ship") in (None, "") or isinstance(context["ship"], str) and len(context["ship"]) <= 80,
            "앱 선박 ID를 확인해 주세요.")
    en = language == "en"
    def message(ko, english):
        return english if en else ko
    ships = ctx.db.ships()
    ship = select_ship(question, ships, context)
    conditions, condition_issue = parse_conditions(question)
    navigation = {"kind": "port-reference", "reference_only": True, "admission": "not_assessed",
        "status": "needs_ship", "ship": {k: ship.get(k) for k in ("id", "name", "imo")} if ship else None,
        "ports": [], "results": [], "ship_options": [], "port_options": []}
    msg = message("어느 선박을 조회할지 확인해 주세요. 앱 선박을 선택하거나 IMO 번호와 함께 다시 질문해 주세요.",
                  "Please identify one registered ship by IMO/name or select it in the existing context.")
    if not ship:
        navigation["ship_options"] = [{k:s.get(k) for k in ("id","name","imo")} for s in ships if not s.get("sample")][:20]
    elif ship.get("sample"):
        navigation["status"] = "needs_real_ship"
        msg = message("선택한 선박은 가상 예시입니다. 실제 MRV 선박과 연결된 앱 선박이 필요합니다.",
                      "The selected ship is a sample. A real app ship explicitly linked to MRV is required.")
    elif re.search(r"가까운|근처|최단|항로|예상\s*도착|날씨|기상|풍속|바람|실시간\s*(?:대기|혼잡)|nearest|nearby|closest|route|weather|\bwind\b|\beta\b|(?:예선|tugs?|ukc|선저\s*여유)\s*(?:이|가|:|=)?\s*\d+", question, re.I):
        navigation["status"] = "unsupported_scope"
        msg = message("현재 위치·항로·도착 시각·기상·실시간 혼잡 기반 추천은 지원하지 않습니다. 질문에 적은 운항 가정값은 적용하지 않았습니다. 운항 화면의 가정 조건 비교에서 풍속·예선·선저 여유를 명시해 일부 게시 조건을 시험할 수 있습니다.",
                      "Location, route, ETA, weather and live congestion suitability are not assessed. Operational assumptions in text were not applied. Use the operation panel's explicitly hypothetical conditions to test selected published rules.")
    elif re.search(r"(?:흘수|전장|선폭|길이|draught|draft|length|beam|loa)\s*(?:이|가|는|은|:|=)?\s*\d+(?:[.,]\d+)?\s*(?:m(?![a-z])|미터|metre|meter)", question, re.I):
        navigation["status"] = "needs_verified_inputs"
        msg = message("질문에 적은 치수를 저장된 선박 제원으로 대신 사용하지 않습니다. 현재 측정값·시각·출처를 확인하거나 저장된 신고값으로 조회해 주세요.",
                      "Hypothetical dimensions are not substituted for ship data. Confirm measured values/time/source or ask to use stored reported values.")
    elif condition_issue:
        navigation["status"] = condition_issue
        msg = message("실제 입항 불가 판정은 제공하지 않습니다. '공개 제한 초과 선석만 알려줘'로 일부 공개 수치 초과 항목을 조회할 수 있습니다."
                      if condition_issue == "needs_reference_scope" else
                      "요청한 조건을 명확하게 적용할 수 없어 조회를 보류했습니다. 공개 선석의 길이·폭·흘수 제한(m)의 이상·이하 조건과 큰/작은 순 정렬을 명시해 주세요.",
                      "Actual entry prohibition is not assessed. Ask for published reference limits exceeded only."
                      if condition_issue == "needs_reference_scope" else
                      "The requested condition is unsupported or ambiguous; no default list was substituted. Specify public berth length/beam/draught limits in metres and a supported comparison or ordering.")
    else:
        try:
            snapshot = service.load_snapshot()
            catalog = snapshot[0]
            navigation["port_options"] = [{"port_id":p.port_id,"name":p.name,"unlocode":p.unlocode} for p in catalog.ports]
            ports, berth, issue, values = select_ports(question, catalog)
            prior = previous_navigation(ctx.db, ctx.user["id"], context, ship) if followup else None
            if followup and not prior:
                issue = "needs_previous_query"
            elif prior and not issue:
                explicit_port = any(mentions(question, a) for names in ALIASES.values() for a in names)
                if not explicit_port and not berth:
                    ports = [p for p in catalog.ports if p.port_id in prior["selection"]["port_ids"]]
                    berth = prior["selection"].get("berth_id")
                    if len(ports) != len(prior["selection"]["port_ids"]):
                        issue = "needs_previous_query"
                old_query = prior.get("query", {})
                conditions = {"filters": conditions["filters"] or old_query.get("filters", []),
                              "sort": conditions["sort"] or old_query.get("sort"),
                              "status": conditions["status"] or old_query.get("status")}
            if issue:
                navigation["status"] = issue
                msg = message("이전 조회 문맥을 확인할 수 없습니다. 같은 선박의 항구 질문을 다시 작성해 주세요.",
                              "The previous query context cannot be verified. Ask a complete port question for the same ship.") if issue == "needs_previous_query" else message(
                              "요청한 항구·선석을 제공 자료에서 확인할 수 없습니다. 다른 대상으로 대신 조회하지 않았습니다. ",
                              "The requested port/berth could not be resolved in the available data; no other target was substituted. ") + ", ".join(values)
            else:
                result = service.compare_ship(ctx.db, ship["id"], port_ids=[p.port_id for p in ports], berth_id=berth, snapshot=snapshot)
                navigation.update(context=result["context"], latest_record_draught=result.get("latest_record_draught"),
                                  status="reference_only" if result["status"] == "ok" else result["status"], results=result["results"])
                if result["status"] != "ok":
                    msg = message(result["notice"], "An explicit app ship to real MRV mapping is required.")
                else:
                    if prior and result["context"] != prior["context"]:
                        navigation.update(status="needs_previous_query", results=[])
                        msg = message("선박 정보 또는 연결이 변경되어 이전 조회를 이어갈 수 없습니다. 항구 질문을 다시 작성해 주세요.",
                                      "The ship or mapping changed. Ask a complete port question again.")
                        return save_answer(ctx, question, language, navigation, msg)
                    selected_results, counts = select_results(result["results"], conditions)
                    navigation.update(results=selected_results, query={**conditions, "description":describe(conditions)}, **counts,
                        selection={"port_ids":[p.port_id for p in ports], "berth_id":berth})
                    if followup:
                        navigation["previous_query_id"] = context["previousQueryId"]
                    if not counts["matched_berth_count"]:
                        navigation["status"] = "no_reference_matches"
                    for item in selected_results:
                        counts = {state:sum(b["status"] == state for b in item["berths"]) for state in
                            ("partial_reference_check","published_reference_exceeded","insufficient_data")}
                        navigation["ports"].append({"port_id":item["port_id"],"name":item["port_name"],
                            "berth_count":len(item["berths"]),"available_berth_count":item["available_berth_count"],**counts})
                    navigation["coverage_port_count"] = len(catalog.ports)
                    msg = message(f"제공 자료 {len(ports)}개 항구의 {navigation['compared_berth_count']}개 선석 그룹을 비교하고 조건에 맞는 {navigation['matched_berth_count']}개를 표시했습니다. 실제 입항 가능/불가 판정은 아닙니다.",
                        f"Compared {navigation['compared_berth_count']} berth groups across {len(ports)} ports; {navigation['matched_berth_count']} match the reference conditions. Entry permission is not assessed.")
                    if navigation["status"] == "no_reference_matches":
                        msg += message(" 조건에 맞는 공개 참조 항목이 없습니다. 입항 불가를 뜻하지 않습니다.", " No public references match; this does not mean entry is prohibited.")
        except ApiError as exc:
            if exc.status not in (503, 404):
                raise
            navigation["status"] = "unavailable"
            msg = message("현재 선박 DB·매핑 또는 항구 참조 자료를 확인할 수 없어 비교를 보류합니다. 자료 준비 상태를 확인해 주세요.",
                          "Comparison is unavailable. Check the ship database, mapping and reference snapshot.")
    return save_answer(ctx, question, language, navigation, msg)


def save_answer(ctx, question, language, navigation, msg):
    navigation["message"] = msg
    answer_id = str(uuid4())
    answer = {"id":answer_id,"question":question,"task":"navigation","language":language,"generation":"tool",
        "status":"reference_found" if navigation["results"] else "needs_input", "notice":msg,
        "warnings":["NAVIGATION_REFERENCE_ONLY"],"statements":[],"evidence":[],"toolRuns":[],
        "reportSuggested":False,"navigation":navigation}
    ctx.db.run("INSERT INTO queries VALUES(%s,%s,%s,%s)",(answer_id,question,Jsonb(answer),utc_now()))
    ctx.db.run("INSERT INTO query_owner VALUES(%s,%s)",(answer_id,ctx.user["id"]))
    ctx.db.audit(ctx.user,"query","질의",answer_id,{"question":question,"task":"navigation","status":navigation["status"]})
    return answer
