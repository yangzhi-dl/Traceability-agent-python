"""传输层契约。数值观察记录保留来源 ID、单位与型号标识。"""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

Role = Literal['viewer', 'quality_engineer', 'supervisor']
Status = Literal['COMPLETED', 'WAITING_APPROVAL', 'PARTIAL', 'DENIED', 'REJECTED']
Outcome = Literal['FOUND', 'NOT_FOUND', 'EMPTY', 'ERROR', 'DENIED']
Factor = Literal['Man', 'Machine', 'Material', 'Method', 'Environment']


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Identity(StrictModel):
    tenant_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,64}$')
    user_id: str = Field(min_length=1, max_length=100)
    role: Role
    trace_id: str = Field(min_length=1, max_length=100)


class DiagnoseRequest(StrictModel):
    work_order_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,64}$')
    batch_no: str = Field(min_length=1, max_length=80)
    request_freeze: bool = False


class ResumeRequest(StrictModel):
    work_order_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,64}$')
    approval_id: str = Field(min_length=1, max_length=100)
    approved: bool


class Measurement(StrictModel):
    name: str
    value: float
    unit: str
    source_id: str
    model_code: str


class FactorFinding(StrictModel):
    status: Literal['ABNORMAL', 'NORMAL', 'UNVERIFIED']
    finding: str
    evidence_ids: list[str]


class RootCause8DReport(StrictModel):
    work_order_id: str
    batch_no: str
    model_code: str
    d1_team: list[str] = Field(min_length=1)
    d2_problem: str
    d3_containment: str
    d4_root_cause: str
    d5_corrective_actions: list[str] = Field(min_length=1)
    d6_validation: str
    d7_prevention: list[str] = Field(min_length=1)
    d8_closure: str
    factors: dict[Factor, FactorFinding]
    measurements: list[Measurement]
    evidence_ids: list[str]
    limitations: list[str] = Field(min_length=1)
    # 报告为诊断草稿：已批准的库存冻结并不能证明 CAPA 措施有效。
    report_status: Literal['DRAFT_PENDING_VALIDATION'] = 'DRAFT_PENDING_VALIDATION'


class ToolObservation(StrictModel):
    outcome: Outcome
    source: str
    evidence_id: str
    data: dict[str, Any] = Field(default_factory=dict)
    message: str = ''


class ToolTrace(StrictModel):
    sequence: int
    call_id: str
    tool: str
    args: dict[str, Any]
    outcome: Outcome
    observation: ToolObservation


class WebSearchRequest(StrictModel):
    """只允许公开技术关键词，禁止附带工单、批次或企业内部数据。"""
    model_config = ConfigDict(extra='forbid', strict=True)
    query: str = Field(min_length=1, max_length=500)

    @field_validator('query')
    @classmethod
    def nonblank_query(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('搜索词不能为空')
        return value.strip()


class WebReference(StrictModel):
    """外部公开资料不是工厂实测证据，来源 URL 与摘要同时保留。"""
    model_config = ConfigDict(extra='forbid', strict=True)
    title: str = Field(min_length=1, max_length=1000)
    url: HttpUrl
    summary: str = Field(min_length=1, max_length=4000)


class WebSearchResult(WebSearchRequest):
    source: Literal['TAVILY_MCP'] = 'TAVILY_MCP'
    outcome: Literal['FOUND', 'EMPTY', 'ERROR']
    reason: Literal['OK', 'NO_RESULTS', 'NOT_CONFIGURED', 'MISSING_DEPENDENCY',
                    'MCP_UNAVAILABLE', 'INVALID_RESPONSE', 'SEARCH_LIMIT_REACHED', 'TIMEOUT']
    references: list[WebReference] = Field(default_factory=list, max_length=3)

    @model_validator(mode='after')
    def consistent_outcome(self):
        if self.outcome == 'FOUND':
            if not self.references or self.reason != 'OK':
                raise ValueError('成功搜索必须包含来源，且 reason 为 OK')
        elif self.references or (self.outcome == 'EMPTY' and self.reason != 'NO_RESULTS'):
            raise ValueError('空结果或失败不可携带成功引用')
        elif self.outcome == 'ERROR' and self.reason in {'OK', 'NO_RESULTS'}:
            raise ValueError('失败结果必须提供失败原因')
        return self


class TraceResponse(StrictModel):
    thread_id: str
    status: Status
    report: RootCause8DReport | None = None
    approval_id: str | None = None
    trajectory: list[ToolTrace] = Field(default_factory=list)
    episodic_memory: list[str] = Field(default_factory=list)
    web_references: list[WebSearchResult] = Field(default_factory=list)
    stop_reason: str


class GraderScore(StrictModel):
    # 基于证据的评分依据，而非模型私有的思维链。
    reason: str = Field(min_length=1, description='具体证据、规则命中和扣分说明；不要输出隐含思维链')
    score: Literal[0, 1]


class SemanticScore(GraderScore):
    faithfulness: Literal[0, 1]
    completeness: Literal[0, 1]


class ServiceError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(message)
