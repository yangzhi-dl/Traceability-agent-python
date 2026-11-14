"""传输层契约。数值观察记录保留来源 ID、单位与型号标识。"""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

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


class TraceResponse(StrictModel):
    thread_id: str
    status: Status
    report: RootCause8DReport | None = None
    approval_id: str | None = None
    trajectory: list[ToolTrace] = Field(default_factory=list)
    episodic_memory: list[str] = Field(default_factory=list)
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
