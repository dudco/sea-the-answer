"""Bounded public-limit interpretation; never a vessel measurement or entry decision."""
from copy import deepcopy
from decimal import Decimal
import operator
import re

DIMENSIONS = {"length": ("길이", "length"), "beam": ("폭", "beam"), "draught": ("흘수", "draught")}
FIELD = r"흘수|전장|길이|선폭|폭|draught|draft|length|loa|beam"
LIMIT = rf"(?:(?:최대\s*(?:선박\s*)?)(?:{FIELD})|(?:{FIELD})\s*(?:제한(?:값)?|한계(?:값)?|한도|limit))"
UNIT = r"(?:미터|metres?|meters?|m)(?![a-z])"
NUMBER = r"\d{1,5}(?:[.,]\d{1,3})?"
NUMERIC = re.compile(rf"(?P<field>{LIMIT})\s*(?:이|가|는|은|:)?\s*(?P<prefix>>=|<=|≥|≤|>|<|=)?\s*"
                     rf"(?P<value>{NUMBER})\s*{UNIT}\s*(?P<suffix>이상|이하|초과|미만|같은|동일|exactly)?"
                     r"(?:인)?\s*(?:(?:선석|곳)\s*만)?", re.I)
SORT = re.compile(rf"(?P<field>{LIMIT})\s*(?:이|가|을|를|:)?\s*"
                  r"(?P<direction>큰|높은|낮은|작은|높게|낮게|내림차순|오름차순|descending|ascending)"
                  r"\s*(?:순서대로|순서로|순으로|순|정렬)?", re.I)
OPS = {">=": operator.ge, "<=": operator.le, ">": operator.gt, "<": operator.lt, "=": operator.eq}
OP_NAMES = {">=": ("이상", "at least"), "<=": ("이하", "at most"), ">": ("초과", "above"),
            "<": ("미만", "below"), "=": ("동일", "exactly")}
OP_CODES = {"≥": ">=", "≤": "<=", "이상": ">=", "이하": "<=", "초과": ">", "미만": "<",
            "같은": "=", "동일": "=", "exactly": "="}
STATES = {
    "published_reference_exceeded": (r"공개\s*(?:제한|수치)(?:값)?(?:을|가|를)?\s*초과(?:한)?\s*(?:(?:선석|곳)\s*)?만", "공개 수치 초과만", "Published references exceeded only"),
    "insufficient_data": (r"자료(?:가)?\s*부족(?:한)?\s*(?:(?:선석|곳)\s*)?만", "자료 부족만", "Insufficient data only"),
    "partial_reference_check": (r"일부\s*공개\s*수치\s*이내(?:인)?\s*(?:(?:선석|곳)\s*)?만", "일부 공개 수치 이내만", "Some published values within only"),
}


def dimension(label):
    label = label.casefold()
    if re.search(r"흘수|draught|draft", label):
        return "draught"
    return "beam" if re.search(r"폭|beam", label) else "length"


def parse_conditions(question):
    """Return only explicitly understood predicates, otherwise request clarification."""
    empty = {"filters": [], "sort": None, "status": None}
    if re.search(r"불가능|불가(?:한|인|능)?|못\s*(?:들어|입항|접안)|입항\s*금지|cannot|can't|impossible|not\s+(?:allowed|possible)", question, re.I):
        return empty, "needs_reference_scope"
    # OR, negated conditions and ranges need a fuller expression grammar. Never drop them.
    if re.search(r"또는|아니면|\bor\b|제외|빼고|않은|아닌|이외|사이|between|except", question, re.I):
        return empty, "unsupported_condition"
    query = deepcopy(empty)
    remaining = question
    for state, (pattern, _, _) in STATES.items():
        if re.search(pattern, remaining, re.I):
            if query["status"]:
                return empty, "unsupported_condition"
            query["status"] = state
            remaining = re.sub(pattern, " ", remaining, flags=re.I)
    numeric = list(NUMERIC.finditer(remaining))
    for match in numeric:
        prefix, suffix = match["prefix"], match["suffix"]
        op = OP_CODES.get(prefix, prefix) if prefix else OP_CODES.get((suffix or "").casefold())
        if not op or suffix and OP_CODES.get(suffix.casefold()) != op:
            return empty, "unsupported_condition"
        value = Decimal(match["value"].replace(",", "."))
        if value <= 0 or len(query["filters"]) >= 3:
            return empty, "unsupported_condition"
        query["filters"].append({"kind": dimension(match["field"]), "op": op, "value_m": str(value)})
    remaining = NUMERIC.sub(" ", remaining)
    sorts = list(SORT.finditer(remaining))
    if len(sorts) > 1:
        return empty, "unsupported_condition"
    if sorts:
        match = sorts[0]
        query["sort"] = {"kind": dimension(match["field"]), "direction": "asc" if match["direction"].casefold() in
                         ("낮은", "작은", "낮게", "오름차순", "ascending") else "desc"}
    remaining = SORT.sub(" ", remaining)
    # A condition marker left unconsumed cannot silently turn into the default list.
    if re.search(rf"{LIMIT}|\d+(?:[.,]\d+)?\s*(?:m\b|미터|ft\b)|이상|이하|미만|초과|정렬|순서|순으로|순대로|큰\s*순|높은\s*순|낮은\s*순|작은\s*순|오름|내림|부족|이내|(?:선석|곳|항구)\s*만|only|sort|order|limit|at\s+least|at\s+most", remaining, re.I):
        return empty, "unsupported_condition"
    return query, None


def describe(query):
    ko, en = [], []
    if query["status"]:
        _, korean, english = STATES[query["status"]]
        ko.append(korean); en.append(english)
    for f in query["filters"]:
        k, e = DIMENSIONS[f["kind"]]
        op_ko, op_en = OP_NAMES[f["op"]]
        ko.append(f"공개 {k} 제한 {f['value_m']} m {op_ko}")
        en.append(f"Published {e} limit {op_en} {f['value_m']} m")
    if query["sort"]:
        s = query["sort"]; k, e = DIMENSIONS[s["kind"]]
        ko.append(f"공개 {k} 제한 {'큰' if s['direction']=='desc' else '작은'} 순 · 항구별 정렬")
        en.append(f"Published {e} limit {s['direction']} · within each port")
    return {"ko": " / ".join(ko) or "제공 선석 전체 · 기본 순서", "en": " / ".join(en) or "All available berths · source order"}


def select_results(results, query):
    """Filter a copy; retain source metadata, original checks and explicit unknown counts."""
    results = deepcopy(results)
    total = matched = unknown = 0
    for result in results:
        original = result["berths"]
        total += len(original)
        rows = []
        for berth in original:
            if query["status"] and berth["status"] != query["status"]:
                continue
            values = {c["kind"]: Decimal(c["berth_listed_m"]) if c["berth_listed_m"] is not None else None for c in berth["checks"]}
            if any(values.get(f["kind"]) is None for f in query["filters"]):
                unknown += 1
                continue
            if all(OPS[f["op"]](values[f["kind"]], Decimal(f["value_m"])) for f in query["filters"]):
                rows.append(berth)
        if query["sort"]:
            s = query["sort"]
            def key(berth):
                value = next((c["berth_listed_m"] for c in berth["checks"] if c["kind"] == s["kind"]), None)
                return (value is None, (Decimal(value) * (-1 if s["direction"] == "desc" else 1)) if value is not None else Decimal(0))
            rows.sort(key=key)
        result["available_berth_count"] = len(original)
        result["berths"] = rows
        matched += len(rows)
    return results, {"compared_berth_count": total, "matched_berth_count": matched, "excluded_unknown_count": unknown}
