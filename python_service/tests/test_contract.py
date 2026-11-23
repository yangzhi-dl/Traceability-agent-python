"""Behavior gates exercise the real graph, ToolNode and FastAPI boundaries."""
import importlib.util


def test_graph_module_exists():
    assert importlib.util.find_spec('python_service.agent_graph') is not None, 'Graph is not implemented'


def make_service():
    from python_service.agent_graph import TraceService
    return TraceService(mode='mock')


def context(role='quality_engineer', user='alice', tenant='plant-a'):
    from python_service.schemas import Identity
    return Identity(user_id=user, role=role, tenant_id=tenant, trace_id='test-trace')


def request(order='WO-TEST', batch='FG-20261001-001', freeze=False):
    from python_service.schemas import DiagnoseRequest
    return DiagnoseRequest(work_order_id=order, batch_no=batch, request_freeze=freeze)


def test_reflexion_recovers_and_preserves_failed_attempt():
    s = make_service()
    r = s.diagnose(request(), context(), fault='bad_batch')
    assert r.status == 'COMPLETED'
    assert len(r.episodic_memory) == 1
    assert any(t.outcome == 'ERROR' for t in r.trajectory)
    assert r.report is not None
    assert set(r.report.factors) == {'Man', 'Machine', 'Material', 'Method', 'Environment'}


def test_missing_time_and_missing_dimension_are_repaired():
    for fault in ['missing_window', 'skip_material']:
        r = make_service().diagnose(request(), context(), fault=fault)
        assert r.status == 'COMPLETED'
        assert r.episodic_memory
        assert any(t.tool == 'trace_erp_work_order_bom' and t.outcome == 'FOUND' for t in r.trajectory)


def test_retry_budget_is_three_and_unknown_batch_cannot_complete():
    for req, fault in [(request(), 'persistent_error'), (request(batch='FG-20990101-999'), 'none')]:
        r = make_service().diagnose(req, context(), fault=fault)
        assert r.status == 'PARTIAL'
        assert len(r.episodic_memory) == 3
        assert r.report is None


def test_real_interrupt_resume_and_no_duplicate_write():
    from python_service.schemas import ResumeRequest
    s = make_service()
    req = request(freeze=True)
    waiting = s.diagnose(req, context())
    assert waiting.status == 'WAITING_APPROVAL'
    assert waiting.approval_id
    assert not any(t.tool == 'freeze_erp_stock_batch' for t in waiting.trajectory)
    cfg = s.config(req.work_order_id, context())
    assert s.graph.get_state(cfg).next
    approval = ResumeRequest(work_order_id=req.work_order_id, approval_id=waiting.approval_id, approved=True)
    r = s.resume(approval, context('supervisor', 'bob'))
    assert r.status == 'COMPLETED'
    writes = [t for t in r.trajectory if t.tool == 'freeze_erp_stock_batch']
    assert len(writes) == 1 and writes[0].outcome == 'FOUND'
    assert s.resume(approval, context('supervisor', 'bob')) == r


def test_approval_rbac_binding_and_rejection():
    import pytest
    from python_service.schemas import ResumeRequest, ServiceError
    s = make_service()
    w = s.diagnose(request(freeze=True), context())
    with pytest.raises(ServiceError) as denied:
        s.resume(ResumeRequest(work_order_id='WO-TEST', approval_id=w.approval_id, approved=True), context())
    assert denied.value.status_code == 403
    with pytest.raises(ServiceError):
        s.resume(ResumeRequest(work_order_id='WO-TEST', approval_id='wrong', approved=True), context('supervisor'))
    r = s.resume(ResumeRequest(work_order_id='WO-TEST', approval_id=w.approval_id, approved=False), context('supervisor'))
    assert r.status == 'REJECTED'
    assert not any(t.tool == 'freeze_erp_stock_batch' for t in r.trajectory)


def test_viewer_cannot_freeze_and_threads_are_isolated():
    import pytest
    from python_service.schemas import ServiceError
    s = make_service()
    assert s.diagnose(request(freeze=True), context('viewer')).status == 'DENIED'
    with pytest.raises(ServiceError):
        s.diagnose(request(freeze=True), context(user='mallory'))
    assert s.diagnose(request(), context(tenant='plant-b')).thread_id == 'plant-b:WO-TEST'


def test_same_order_conflicting_request_is_rejected():
    import pytest
    from python_service.schemas import ServiceError
    s = make_service()
    first = s.diagnose(request(), context())
    assert s.diagnose(request(), context()) == first
    with pytest.raises(ServiceError):
        s.diagnose(request(batch='FG-20261001-002'), context())


def test_wrong_model_sop_and_fabricated_numbers_fail_grader():
    from python_service.evals.graders import SemanticGrader, TrajectoryGrader
    r = make_service().diagnose(request(), context())
    assert SemanticGrader(mode='mock').grade(r).score == 1
    assert TrajectoryGrader().grade(r).score == 1
    corrupt = r.model_copy(deep=True)
    corrupt.report.measurements[0].value += 999
    assert SemanticGrader(mode='mock').grade(corrupt).score == 0
    omitted = r.model_copy(deep=True)
    omitted.trajectory = [t for t in omitted.trajectory if t.tool != 'trace_erp_work_order_bom']
    assert TrajectoryGrader().grade(omitted).score == 0


def test_hybrid_retrieval_has_exact_model_filter():
    from python_service.tools import HybridRetriever
    results = HybridRetriever().search('B-HOUSING', 'A-HOUSING moisture SOP')
    assert results and all(d['model_code'] == 'B-HOUSING' for d in results)


def test_api_requires_gateway_auth_and_validates_schema(monkeypatch):
    from fastapi.testclient import TestClient
    from python_service.main import create_app
    monkeypatch.setenv('GATEWAY_TOKEN', 'test-only-secret')
    with TestClient(create_app(make_service())) as client:
        assert client.post('/api/v1/trace/diagnose', json={}).status_code == 401
        headers = {'X-Gateway-Token': 'test-only-secret', 'X-Tenant-Id': 'plant-a',
                   'X-User-Id': 'alice', 'X-User-Role': 'quality_engineer', 'X-Trace-Id': 'test-trace'}
        assert client.post('/api/v1/trace/diagnose', json={}, headers=headers).status_code == 422
        r = client.post('/api/v1/trace/diagnose', json=request().model_dump(), headers=headers)
        assert r.status_code == 200 and r.json()['status'] == 'COMPLETED'


def test_pass_three_uses_independent_all_runs():
    from python_service.evals.run_eval import metrics
    m = metrics([[True, True, False], [True, True, True]])
    assert m['pass1'] == 5 / 6
    assert m['pass3'] == 0.5


def test_resume_cannot_cross_tenant_or_reverse_decision():
    import pytest
    from python_service.schemas import ResumeRequest, ServiceError
    s = make_service()
    w = s.diagnose(request(freeze=True), context())
    approval = ResumeRequest(work_order_id='WO-TEST', approval_id=w.approval_id, approved=False)
    with pytest.raises(ServiceError) as absent:
        s.resume(approval, context('supervisor', tenant='other'))
    assert absent.value.status_code == 404
    s.resume(approval, context('supervisor'))
    with pytest.raises(ServiceError):
        s.resume(approval.model_copy(update={'approved': True}), context('supervisor'))


def test_trace_grader_rejects_wrong_order_loop_and_unapproved_write():
    from python_service.evals.graders import TrajectoryGrader
    r = make_service().diagnose(request(), context())
    wrong_order = r.model_copy(deep=True)
    wrong_order.trajectory[1], wrong_order.trajectory[3] = wrong_order.trajectory[3], wrong_order.trajectory[1]
    for i, row in enumerate(wrong_order.trajectory):
        row.sequence = i + 1
    assert TrajectoryGrader().grade(wrong_order).score == 0
    loop = r.model_copy(deep=True)
    loop.trajectory *= 5
    assert TrajectoryGrader().grade(loop).score == 0
    write = r.model_copy(deep=True)
    write.trajectory.append(write.trajectory[-1].model_copy(update={'tool': 'freeze_erp_stock_batch', 'call_id': 'new', 'sequence': 5}))
    assert TrajectoryGrader().grade(write).score == 0


def test_freeze_tool_denies_forged_or_mismatched_approval():
    from python_service.tools import freeze_erp_stock_batch
    state = {'approval': {'approved': True, 'role': 'quality_engineer', 'approval_id': 'a'},
             'approval_id': 'a', 'evidence': {'trace_erp_work_order_bom': {'data': {'raw_batch': 'RM-1'}}}}
    assert freeze_erp_stock_batch.invoke({'batch_no': 'RM-1', 'state': state})['outcome'] == 'DENIED'
    state['approval']['role'] = 'supervisor'
    assert freeze_erp_stock_batch.invoke({'batch_no': 'RM-OTHER', 'state': state})['outcome'] == 'DENIED'


def test_wrong_batch_tool_evidence_is_not_accepted():
    from python_service.agent_graph import evidence_error
    from python_service.tools import query_defect_inspection
    state = {'request': request().model_dump(), 'evidence': {}}
    wrong = query_defect_inspection.invoke({'batch_no': 'FG-20261001-002'})
    assert evidence_error(state, 'query_defect_inspection', wrong) is not None


def test_app_fails_closed_in_production_without_gateway_secret(monkeypatch):
    import pytest
    from fastapi.testclient import TestClient
    from python_service.main import create_app
    monkeypatch.setenv('APP_ENV', 'production')
    monkeypatch.delenv('GATEWAY_TOKEN', raising=False)
    with pytest.raises(RuntimeError, match='GATEWAY_TOKEN'):
        with TestClient(create_app(make_service())):
            pass


def test_order_concurrency_rejected():
    import pytest
    from python_service.schemas import ServiceError
    s = make_service()
    with s.locked('plant-a:WO-TEST'):
        with pytest.raises(ServiceError) as busy:
            s.diagnose(request(), context())
    assert busy.value.status_code == 409


def test_llm_graph_branch_uses_bound_tools_and_structured_output_without_network(monkeypatch):
    import json
    from langchain_core.runnables import RunnableLambda
    from python_service import agent_graph
    from python_service.fixtures import START, END
    from python_service.reporting import build_report
    from python_service.schemas import RootCause8DReport

    calls = iter([
        ('query_defect_inspection', {'batch_no': 'FG-20261001-001'}),
        ('trace_erp_work_order_bom', {'batch_no': 'FG-20261001-001'}),
        ('query_equipment_telemetry', {'batch_no': 'FG-20261001-001', 'start_time': START, 'end_time': END}),
        ('retrieve_sop_and_8d_cases', {'model_code': 'A-HOUSING', 'query': 'A-HOUSING SOP'}),
    ])
    structured_schemas = []

    class ScriptedProvider:
        def bind_tools(self, tools, parallel_tool_calls):
            # 四个必查工具保持原样，另绑定一个可选搜索工具。
            from python_service.tools import REQUIRED_TOOLS
            assert not parallel_tool_calls
            assert [tool.name for tool in tools] == [*REQUIRED_TOOLS, 'web_search']
            return RunnableLambda(lambda prompt: agent_graph.call_message(*next(calls)))

        def with_structured_output(self, schema):
            structured_schemas.append(schema)
            return RunnableLambda(lambda prompt: build_report(json.loads(prompt.to_messages()[-1].content)))

    monkeypatch.setattr(agent_graph, 'selected_mode', lambda mode: 'llm')
    monkeypatch.setattr(agent_graph, 'model', lambda mode: ScriptedProvider())
    s = agent_graph.TraceService(mode='llm')
    result = s.diagnose(request(), context())
    assert result.status == 'COMPLETED'
    assert structured_schemas == [RootCause8DReport]


def test_api_approval_and_sse_transport(monkeypatch):
    from fastapi.testclient import TestClient
    from python_service.main import create_app
    monkeypatch.delenv('GATEWAY_TOKEN', raising=False)
    monkeypatch.setenv('APP_ENV', 'demo')
    with TestClient(create_app(make_service())) as client:
        w = client.post('/api/v1/trace/diagnose', json=request(freeze=True).model_dump()).json()
        body = {'work_order_id': 'WO-TEST', 'approval_id': w['approval_id'], 'approved': True}
        assert client.post('/api/v1/trace/resume', json=body).status_code == 403
        r = client.post('/api/v1/trace/resume', json=body, headers={'X-User-Role': 'supervisor', 'X-User-Id': 'bob'})
        assert r.status_code == 200 and r.json()['status'] == 'COMPLETED'
        sse = client.post('/api/v1/trace/diagnose/stream', json=request(order='WO-SSE').model_dump())
        assert sse.headers['content-type'].startswith('text/event-stream')
        assert 'event: result' in sse.text and 'COMPLETED' in sse.text
