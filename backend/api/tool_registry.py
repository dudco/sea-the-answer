"""Single allowlist of tools the model may request (ADR 0024).

Only read-only tools that run behind the ordinary user permission checks are
registered. Arguments are suggestions from the model: they are validated here
and resolved against registered ships, documents and ports by the dispatcher.
"""
from dataclasses import dataclass
import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

DATASETS = ('ais', 'mrv', 'dwt', 'noon', 'operations', 'documents', 'ports')
Mention = Annotated[str, Field(min_length=1, max_length=100)]
PeriodText = Annotated[str, Field(max_length=100)]


class ToolCallError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class Args(BaseModel):
    model_config = ConfigDict(extra='forbid')


class DatasetStatusArgs(Args):
    datasets: list[Literal[DATASETS]] = Field(min_length=1, max_length=7,
        description='확인할 자료 종류. 질문이 자료 전체를 물으면 모두 넣는다.')
    ship_mentions: list[Mention] = Field(default_factory=list, max_length=1,
        description='질문에 적힌 선박 이름이나 IMO 표기 그대로. 없으면 빈 배열.')
    period_text: PeriodText = Field(default='', description='질문에 적힌 기간 표현 그대로(예: 2024년). 계산하지 않는다.')


class AisStatusArgs(Args):
    ship_mentions: list[Mention] = Field(default_factory=list, max_length=1,
        description='질문에 적힌 선박 이름이나 IMO 표기 그대로. 없으면 빈 배열.')


class OperationsArgs(Args):
    ship_mentions: list[Mention] = Field(default_factory=list, max_length=2,
        description='질문에 적힌 선박 이름이나 IMO 표기 그대로, 최대 2개.')
    period_text: PeriodText = Field(default='', description='질문에 적힌 기간 표현 그대로(예: 지난달, 2025년 1월과 2월).')
    display: Literal['text', 'table', 'chart'] = Field(default='text', description='표나 차트를 요청했을 때만 table 또는 chart.')


class MrvArgs(Args):
    ship_mentions: list[Mention] = Field(default_factory=list, max_length=2,
        description='질문에 적힌 선박 이름이나 IMO 표기 그대로, 최대 2개.')
    period_text: PeriodText = Field(default='', description='질문에 적힌 보고 연도 표현 그대로(예: 작년, 2024년).')
    accept_reference: bool = Field(default=False,
        description='직전 답변이 참고값 계산 동의를 물었고 사용자가 동의한 경우에만 true.')


class CombinedArgs(Args):
    ship_mentions: list[Mention] = Field(default_factory=list, max_length=2,
        description='질문에 적힌 선박 이름이나 IMO 표기 그대로, 최대 2개.')
    period_text: PeriodText = Field(default='', description='질문에 적힌 기간·연도 표현 그대로.')
    accept_reference: bool = Field(default=False,
        description='직전 답변이 참고값 계산 동의를 물었고 사용자가 동의한 경우에만 true.')


Dimension = Literal['length', 'beam', 'draught']


class PortFilter(Args):
    dimension: Dimension
    op: Literal['>=', '<=', '>', '<', '=']
    value_m: float = Field(gt=0, le=1000)


class PortSort(Args):
    dimension: Dimension
    direction: Literal['asc', 'desc']


class PortArgs(Args):
    ship_mention: str = Field(default='', max_length=100, description='질문에 적힌 선박 표기 그대로. 없으면 빈 문자열.')
    port_mentions: list[Mention] = Field(default_factory=list, max_length=5,
        description='질문에 적힌 항구 이름 그대로. 없으면 빈 배열(제공 항구 전체).')
    berth_mention: str = Field(default='', max_length=40, description='질문에 적힌 선석 번호 그대로. 없으면 빈 문자열.')
    filters: list[PortFilter] = Field(default_factory=list, max_length=3,
        description='공개 선석 제한값(m) 조건. 질문에 명시된 조건만.')
    sort: PortSort | None = Field(default=None, description='제한값 정렬을 요청했을 때만.')
    status_filter: Literal['published_reference_exceeded', 'insufficient_data', 'partial_reference_check'] | None = None


class SelectedDocumentArgs(Args):
    document_mentions: list[Mention] = Field(min_length=1, max_length=5, description='질문에 적힌 문서 제목 그대로.')


class EmissionsArgs(Args):
    fuel_t: float = Field(ge=0, le=1e7)
    factor: float = Field(gt=0, le=10, description='tCO2/t 연료')
    dwt: float = Field(gt=0, le=1e7)
    distance_nm: float = Field(gt=0, le=1e7)


UtcTime = Annotated[str, Field(pattern=r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{3})?Z$')]
Offset = Annotated[int, Field(ge=-720, le=840, multiple_of=15)]


class VoyageTimeArgs(Args):
    start: UtcTime
    end: UtcTime
    start_offset_min: Offset = 0
    end_offset_min: Offset = 0


class ClarifyArgs(Args):
    missing: list[Literal['task', 'ships', 'periods', 'years', 'documents', 'ports']] = Field(min_length=1, max_length=6)


class DeclineArgs(Args):
    reason: Literal['realtime_position', 'weather', 'forecast', 'data_change', 'entry_approval', 'off_topic']


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args: type[Args]
    kind: Literal['data', 'control']


@dataclass(frozen=True)
class Call:
    tool: Tool
    args: Args


TOOLS = {tool.name: tool for tool in (
    Tool('get_dataset_status', '서버에 등록된 해사 자료(AIS·MRV·DWT·Noon·운항기록·문서·항만)의 유무·건수·출처·수집일을 확인한다.',
         DatasetStatusArgs, 'data'),
    Tool('get_ais_catalog_status', '연결된 AIS 수집본의 관측 수와 특정 선박의 관측 여부를 확인한다.', AisStatusArgs, 'data'),
    Tool('summarize_operations', '등록 선박의 기간별 일별 운항기록(연료·CO2·거리)을 합계·비교한다.', OperationsArgs, 'data'),
    Tool('calculate_mrv_reference', 'MRV 보고 자료로 연도별 참고 탄소집약도를 계산한다. 공식 CII 등급이 아니다.', MrvArgs, 'data'),
    Tool('calculate_operations_and_mrv', '운항 실적 합계와 MRV 참고 탄소집약도를 함께 계산한다.', CombinedArgs, 'data'),
    Tool('compare_port_conditions', '선박 제원과 항구 선석의 공개 제한값(길이·폭·흘수)을 비교한다. 입항 허가 판정이 아니다.',
         PortArgs, 'data'),
    Tool('ask_selected_documents', '사용자가 지정한 문서 안에서만 근거를 찾아 답한다.', SelectedDocumentArgs, 'data'),
    Tool('calculate_emissions', '질문에 주어진 연료량·배출계수·DWT·거리로 배출량과 단순 집약도를 계산한다.', EmissionsArgs, 'data'),
    Tool('voyage_time', '질문에 주어진 UTC 시각과 선내 시차로 항해 시간을 계산한다.', VoyageTimeArgs, 'data'),
    Tool('request_clarification', '어떤 작업이나 대상(선박·기간·문서·항구)인지 불명확해 되물어야 할 때 쓴다.', ClarifyArgs, 'control'),
    Tool('decline_request', '실시간 위치·기상·예측·자료 변경·입항 승인·해사 업무와 무관한 요청일 때 쓴다.', DeclineArgs, 'control'),
)}


def _inline(schema):
    """Inline $defs and drop titles: small models handle flat schemas more reliably."""
    definitions = schema.pop('$defs', {})

    def resolve(node):
        if isinstance(node, dict):
            if '$ref' in node:
                return resolve(dict(definitions[node['$ref'].rsplit('/', 1)[1]]))
            return {k: resolve(v) for k, v in node.items() if k != 'title'}
        if isinstance(node, list):
            return [resolve(v) for v in node]
        return node
    return resolve(schema)


def parameters(tool):
    return _inline(tool.args.model_json_schema())


def model_tools():
    return [{'type': 'function', 'function': {'name': t.name, 'description': t.description, 'parameters': parameters(t)}}
            for t in TOOLS.values()]


def catalog():
    return [{'name': t.name, 'description': t.description, 'kind': t.kind, 'parameters': parameters(t)}
            for t in TOOLS.values()]


def parse_call(name, arguments):
    tool = TOOLS.get(name) if isinstance(name, str) else None
    if tool is None:
        raise ToolCallError('MODEL_UNKNOWN_TOOL')
    if isinstance(arguments, str):
        if len(arguments.encode()) > 4096:
            raise ToolCallError('MODEL_ARGUMENTS_TOO_LARGE')
        try:
            arguments = json.loads(arguments) if arguments.strip() else {}
        except (ValueError, RecursionError):
            raise ToolCallError('MODEL_INVALID_ARGUMENTS') from None
    if not isinstance(arguments, dict):
        raise ToolCallError('MODEL_INVALID_ARGUMENTS')
    try:
        return tool, tool.args.model_validate(arguments)
    except ValidationError:
        raise ToolCallError('MODEL_INVALID_ARGUMENTS') from None
