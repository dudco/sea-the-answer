"""Small, reviewable search vocabulary; never changes stored document text.

Aliases are search hints, not regulatory equivalence statements. Add narrow
phrases plus positive/negative retrieval tests instead of broad substring rules.
"""

# Keep maritime compounds intact before stripping particles/endings with Kiwi.
KOREAN_TERMS = (
    "선급", "평형수", "선급정지", "선급등록", "강선규칙", "선급검사",
    "복원성", "감항성", "흘수", "재화중량", "총톤수", "황함유량",
    "탄소집약도", "배출규제해역", "구명설비", "소화설비", "갑판화물",
)

SEARCH_SYNONYMS = (
    ("fuel", "연료"), ("emission", "emissions", "배출량"),
    ("report", "보고서"), ("cii", "탄소집약도", "carbon intensity"),
    ("eca", "배출규제해역", "emission control area"),
    ("sulphur", "sulfur", "황"), ("sulphur content", "sulfur content", "황함유량"),
    ("sox", "sulphur oxides", "sulfur oxides", "황산화물"),
    ("rating", "등급"), ("corrective", "시정", "개선"),
    ("changeover", "전환"), ("checklist", "점검표"),
    ("classification", "선급"), ("class suspension", "suspension of class", "선급정지", "선급 정지"),
    ("ballast water", "평형수"), ("stability", "복원성"),
    ("draught", "draft", "흘수"), ("deadweight", "dwt", "재화중량"),
    ("gross tonnage", "gt", "총톤수"),
    ("heavy deck cargo", "heavy deck cargoes", "중량 갑판화물", "중량 갑판 화물"),
    ("fire fighting", "firefighting", "소화설비"),
    ("life saving appliances", "lifesaving appliances", "구명설비"),
)

# Do NOT remove negation (not/no/without/않/없/안/못), thresholds, units or
# domain words such as 적용/기준/검사. POS filtering handles Korean grammar.
STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "at", "for", "by", "with", "from",
    "is", "are", "was", "were", "be", "been", "being", "this", "that", "these", "those",
    "what", "which", "how", "please",
    "및", "또는", "그리고", "대해", "대한", "해당", "무엇", "어떻게", "뭐",
})
