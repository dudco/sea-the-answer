"""Reviewed public guidance stays distinct from current measurements and entry approval."""
from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl, model_validator

PILOT = 'https://www.sjofartsverket.se/en/services/pilotage/pilot-area-gothenburg/standards--procedures/'
HELSINKI = 'https://www.portofhelsinki.fi/en/professionals/information-for-port-users/'
DOCUMENTS = {
    'gothenburg_draught': ('WPI:24020', PILOT+'maximum-draught/', 'Maximum Draught', 'Sjöfartsverket'),
    'gothenburg_tugs': ('WPI:24020', PILOT+'tug-regulations/', 'Tug Regulations', 'Sjöfartsverket'),
    'gothenburg_weather': ('WPI:24020', PILOT+'visibility-wind-darkness/', 'Visibility Wind Darkness', 'Sjöfartsverket'),
    'gothenburg_control': ('WPI:24020', 'https://www.portofgothenburg.com/maritime/port-control/', 'Port Control', 'Gothenburg Port Authority'),
    'helsinki_regulations': ('WPI:28190', HELSINKI+'instructions/port-of-helsinki-harbour-regulations/', 'Port of Helsinki Harbour Regulations', 'Port of Helsinki Ltd'),
    'helsinki_cruise_navigation': ('WPI:28190', HELSINKI+'instructions-for-cruise-ships/navigation-safety/', 'Navigation & Safety', 'Port of Helsinki Ltd'),
}
Hash = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class PublishedValue(Strict):
    label: str = Field(min_length=1, max_length=100)
    value: Annotated[Decimal, Field(ge=0, lt=1000000, allow_inf_nan=False)]
    unit: Literal['m', 'm/s', 'NM', 'h', 'DWT', '°C']


class GuidanceFact(Strict):
    id: str = Field(pattern=r'^[a-z][a-z0-9-]{1,79}$')
    title: str = Field(min_length=1, max_length=120)
    summary: str = Field(min_length=1, max_length=600)
    scope: str = Field(min_length=1, max_length=600)
    values: list[PublishedValue] = Field(default_factory=list, max_length=8)
    berth_ids: list[Annotated[str, Field(pattern=r'^WPI:[0-9]+:BERTH:[0-9A-Z-]+$')]] = Field(default_factory=list, max_length=3)
    evidence_text: str = Field(min_length=1, max_length=1600)
    locator: str = Field(min_length=1, max_length=200)


class PortGuidance(Strict):
    id: str
    port_id: str
    title: str
    url: HttpUrl
    attribution: str
    raw_sha256: Hash
    content_sha256: Hash
    retrieved_at: AwareDatetime
    displayed_updated_on: date | None
    effective_on: date | None
    facts: list[GuidanceFact] = Field(min_length=1, max_length=20)
    applicability: Literal['requires_review'] = 'requires_review'

    @model_validator(mode='after')
    def binding(self):
        expected = DOCUMENTS.get(self.id)
        if not expected or (self.port_id, str(self.url), self.title, self.attribution) != expected:
            raise ValueError('Unreviewed official guidance identity/URL/port')
        if len({f.id for f in self.facts}) != len(self.facts):
            raise ValueError('Duplicate guidance fact')
        if any(not berth.startswith(self.port_id+':BERTH:') for fact in self.facts for berth in fact.berth_ids):
            raise ValueError('Guidance berth outside its port')
        return self


def guidance_context(documents, port_id, berth_id, now):
    rows = []
    for doc in documents:
        if doc.port_id != port_id:
            continue
        row = doc.model_dump(mode='json')
        row['facts'] = [fact.model_dump(mode='json') for fact in doc.facts
                        if not berth_id or not fact.berth_ids or berth_id in fact.berth_ids]
        if not row['facts']:
            continue
        row['capture_age_status'] = ('time_in_future' if doc.retrieved_at > now else
            'stale' if now-doc.retrieved_at > timedelta(days=7) else 'within_age_window')
        row['displayed_revision_age_status'] = ('unknown' if doc.displayed_updated_on is None else
            'time_in_future' if doc.displayed_updated_on > now.date() else
            'older_than_one_year' if (now.date()-doc.displayed_updated_on).days > 365 else 'within_one_year')
        rows.append(row)
    return {'reference_only': True, 'applicability': 'requires_review', 'documents': rows,
        'notice': '수집 시점에 공식 웹사이트에서 제공한 지침입니다. 개정일·적용일과 수집일은 다르며 최신 공고 전체·현재 적용 여부·입항 승인을 확인한 결과가 아닙니다. 선종·접근 경로·입출항·선석 등 원문의 적용 조건을 확인하세요.',
        'freshness_policy': {'capture_days':7, 'revision_display_days':365, 'basis':'application display policy, not a navigation regulation'},
        'used_for_automatic_comparison':False}
