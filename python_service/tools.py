"""五个带类型的工业工具。真实检索为可选接入；ERP 始终为模拟实现。"""
import hashlib
import math
import os
import re
from collections import Counter
from datetime import datetime
from typing import Annotated, Any

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState
from pydantic import Field
from rank_bm25 import BM25Okapi

from .fixtures import SOPS, case
from .schemas import StrictModel, ToolObservation


def tokens(text: str) -> list[str]:
    return re.findall(r'[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*|[\u4e00-\u9fff]', text.lower())


class HybridRetriever:
    """BM25 + 向量召回 -> RRF 融合 -> 重排序，全程强制型号过滤。

    mock：本地词元余弦 / 词汇重排器，明确不依赖 Milvus 或 BGE。
    real：本地安装的 embedding/BGE 模型与已有的 Milvus 集合。
    """
    def __init__(self, backend: str | None = None):
        self.backend = backend or os.getenv('RAG_BACKEND', 'mock')
        if self.backend not in {'mock', 'real'}:
            raise ValueError('RAG_BACKEND must be mock or real')
        self.documents = SOPS
        if self.backend == 'real':
            self._init_real_backend()

    def _init_real_backend(self):
        # 可选的重型依赖（pymilvus / sentence-transformers）在此延迟导入，
        # 使 mock 模式无需安装它们。通过 requirements-integrations.txt 安装。
        try:
            from pymilvus import MilvusClient
            from sentence_transformers import CrossEncoder, SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                'RAG_BACKEND=real requires pymilvus and sentence-transformers; '
                'install with: uv pip install -r requirements-integrations.txt'
            ) from exc
        # 强制要求本地模型目录：处理请求时绝不联网下载模型。
        self.embedding = SentenceTransformer(os.environ['EMBEDDING_MODEL_PATH'], local_files_only=True)
        self.reranker = CrossEncoder(os.environ['BGE_RERANKER_PATH'], local_files_only=True)
        self.milvus = MilvusClient(uri=os.environ['MILVUS_URI'], token=os.getenv('MILVUS_TOKEN', ''))

    def search(self, model_code: str, query: str) -> list[dict[str, Any]]:
        if not re.fullmatch(r'[A-Z0-9-]+', model_code):
            raise ValueError('Invalid model code')
        docs = [d for d in self.documents if d['model_code'] == model_code]
        if not docs:
            return []
        bm25 = BM25Okapi([tokens(d['text']) for d in docs])
        bm25_scores = bm25.get_scores(tokens(query))
        lexical = sorted(range(len(docs)), key=lambda i: bm25_scores[i], reverse=True)
        if self.backend == 'real':
            hits = self.milvus.search(
                collection_name=os.getenv('MILVUS_COLLECTION', 'trace_sops'),
                data=self.embedding.encode([query], normalize_embeddings=True).tolist(),
                filter=f'model_code == "{model_code}"', limit=8,
                output_fields=['id', 'model_code', 'text', 'kind', 'limits'])
            vector_docs = [h['entity'] for h in hits[0] if h['entity']['model_code'] == model_code]
        else:
            q = Counter(tokens(query))
            def cosine(d):
                t = Counter(tokens(d['text']))
                return sum(q[k] * t[k] for k in q) / max(1, math.sqrt(sum(v*v for v in q.values()) * sum(v*v for v in t.values())))
            vector_docs = sorted(docs, key=cosine, reverse=True)
        fused: dict[str, dict] = {}
        for ranking in [[docs[i] for i in lexical], vector_docs]:
            for rank, doc in enumerate(ranking):
                row = fused.setdefault(doc['id'], dict(doc, rrf_score=0.0))
                row['rrf_score'] += 1 / (60 + rank + 1)
        candidates = sorted(fused.values(), key=lambda d: d['rrf_score'], reverse=True)
        if self.backend == 'real':
            scores = self.reranker.predict([(query, d['text']) for d in candidates])
        else:
            scores = [len(set(tokens(query)) & set(tokens(d['text']))) + (2 if d['kind'] == 'SOP' else 0) for d in candidates]
        for doc, score in zip(candidates, scores):
            doc['rerank_score'] = float(score)
            doc['retrieval_backend'] = self.backend
        return sorted(candidates, key=lambda d: d['rerank_score'], reverse=True)[:4]


class BatchArgs(StrictModel):
    batch_no: str = Field(description='MES 成品批次，严格格式 FG-YYYYMMDD-NNN；不可传原料 RM 批次')


class TelemetryArgs(BatchArgs):
    start_time: str = Field(description='MES production_start，含时区的 ISO8601')
    end_time: str = Field(description='MES production_end，含时区的 ISO8601')


class SopArgs(StrictModel):
    model_code: str = Field(description='必须使用 MES 返回的精确型号，禁止跨型号套用标准')
    query: str


class FreezeArgs(StrictModel):
    batch_no: str = Field(description='已经人工批准的 ERP 原料批次')
    state: Annotated[dict, InjectedState]


def observation(outcome: str, source: str, key: str, data: dict | None = None, message: str = '') -> dict:
    return ToolObservation(outcome=outcome, source=source, evidence_id=f'{source}:{key}',
                           data=data or {}, message=message).model_dump()


def lookup(batch_no: str) -> dict | None:
    if not re.fullmatch(r'FG-\d{8}-\d{3}', batch_no):
        raise ValueError('BATCH_FORMAT: expected FG-YYYYMMDD-NNN; use MES canonical batch_no')
    return case(batch_no)


@tool(args_schema=BatchArgs)
def query_defect_inspection(batch_no: str) -> dict:
    """首先查询 MES 的缺陷、精确型号、生产时间窗及人/环境事实。
    仅调用本工具后诊断尚未完成：还需分别排查物料、机台与方法。
    """
    c = lookup(batch_no)
    if not c:
        return observation('NOT_FOUND', 'MES', batch_no, message='Batch not found')
    keys = ['batch_no', 'model_code', 'defect', 'defect_rate', 'location', 'equipment_id',
            'production_start', 'production_end', 'operator_training', 'environment_rh_pct']
    return observation('FOUND', 'MES', batch_no, {k: c[k] for k in keys})


@tool(args_schema=BatchArgs)
def trace_erp_work_order_bom(batch_no: str) -> dict:
    """物料维度：ERP 工单 -> BOM -> 原料批次 -> 含水率 -> 供应商。
    即使机台温度异常也必须执行；多种原因可能同时存在。
    """
    c = lookup(batch_no)
    if not c:
        return observation('NOT_FOUND', 'ERP', batch_no)
    keys = ['batch_no', 'model_code', 'erp_work_order', 'material', 'raw_batch', 'supplier', 'moisture_pct']
    return observation('FOUND', 'ERP', batch_no, {k: c[k] for k in keys})


@tool(args_schema=TelemetryArgs)
def query_equipment_telemetry(batch_no: str, start_time: str, end_time: str) -> dict:
    """机台维度：严格在 MES 生产时间窗内查询遥测数据。
    温度异常不能排除物料含水率问题；两个工具均为必查项。
    """
    c = lookup(batch_no)
    if not c:
        return observation('NOT_FOUND', 'SENSOR', batch_no)
    start, end = datetime.fromisoformat(start_time), datetime.fromisoformat(end_time)
    if not start.tzinfo or not end.tzinfo or start >= end:
        raise ValueError('TIME_WINDOW: require timezone and start < end')
    if start != datetime.fromisoformat(c['production_start']) or end != datetime.fromisoformat(c['production_end']):
        return observation('EMPTY', 'SENSOR', batch_no, message='TIME_WINDOW: align with MES production window')
    data = {k: c[k] for k in ['batch_no', 'model_code', 'equipment_id', 'temperature_c', 'pressure_mpa', 'rpm']}
    data.update(start_time=start_time, end_time=end_time,
                samples=[{'at': start_time, 'temperature_c': c['temperature_c'], 'pressure_mpa': c['pressure_mpa']},
                         {'at': end_time, 'temperature_c': c['temperature_c'], 'pressure_mpa': c['pressure_mpa']}])
    return observation('FOUND', 'SENSOR', batch_no, data)


@tool(args_schema=SopArgs)
def retrieve_sop_and_8d_cases(model_code: str, query: str) -> dict:
    """方法维度：同型号 BM25 + 向量召回 + 重排序，检索 SOP 与历史 8D。
    在 ERP 与传感器之后调用，将其实测参数与本型号标准限值对照。
    """
    docs = HybridRetriever().search(model_code, query)
    return observation('FOUND' if docs else 'EMPTY', 'SOP', model_code,
                       {'model_code': model_code, 'documents': docs})


@tool(args_schema=FreezeArgs)
def freeze_erp_stock_batch(batch_no: str, state: Annotated[dict, InjectedState]) -> dict:
    """高风险操作：冻结已批准的 ERP 原料批次并创建幂等的 CAPA 单。
    仅 interrupt 之后的 ToolNode 暴露本工具。身份/状态由系统注入，绝不来自模型参数。
    """
    decision = state.get('approval', {})
    raw = state.get('evidence', {}).get('trace_erp_work_order_bom', {}).get('data', {}).get('raw_batch')
    if (decision.get('approved') is not True or decision.get('role') != 'supervisor'
            or decision.get('approval_id') != state.get('approval_id') or batch_no != raw):
        return observation('DENIED', 'ERP_WRITE', batch_no, message='Approval binding or RBAC failed')
    # Mock ERP 使用确定性的操作 ID。真实 ERP 适配器必须在自身事务中强制该幂等键，
    # 覆盖冻结与 CAPA 创建两个动作。
    key = f'{state["thread_id"]}:{state["approval_id"]}:{batch_no}'
    operation_id = hashlib.sha256(key.encode()).hexdigest()[:20]
    return observation('FOUND', 'ERP_WRITE', operation_id,
                       {'raw_batch': batch_no, 'frozen': True, 'capa_id': f'CAPA-{operation_id}',
                        'idempotency_key': key, 'backend': 'mock'})


READ_TOOLS = [query_defect_inspection, trace_erp_work_order_bom, query_equipment_telemetry, retrieve_sop_and_8d_cases]
REQUIRED_TOOLS = [t.name for t in READ_TOOLS]
