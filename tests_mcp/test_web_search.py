"""新增 MCP 链路测试；与既有二十项闭环测试分开运行。"""
import importlib
import json

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import ToolMessage
from pydantic import ValidationError


QUERY = 'polyamide moisture processing technical reference'
TEXT = 'Detailed Results:\n\nTitle: Public technical note\nURL: https://example.org/polyamide\nContent: Public background, not factory evidence.'


def modules():
    return importlib.import_module('python_service.web_search'), importlib.import_module('python_service.schemas')


def test_new_contract_exists():
    from python_service import schemas
    assert hasattr(schemas, 'WebSearchResult'), '尚未实现独立搜索契约'


def test_required_tools_unchanged():
    from python_service.tools import READ_TOOLS, REQUIRED_TOOLS
    assert REQUIRED_TOOLS == [
        'query_defect_inspection', 'trace_erp_work_order_bom',
        'query_equipment_telemetry', 'retrieve_sop_and_8d_cases']
    assert [tool.name for tool in READ_TOOLS] == REQUIRED_TOOLS


def test_no_key_health_and_diagnosis(monkeypatch):
    monkeypatch.delenv('TAVILY_API_KEY', raising=False)
    monkeypatch.delenv('GATEWAY_TOKEN', raising=False)
    from python_service.main import create_app
    from python_service.runtime import TraceService
    with TestClient(create_app(TraceService(mode='mock'))) as client:
        assert client.get('/health').json()['status'] == 'ok'
        result = client.post('/api/v1/trace/diagnose', json={
            'work_order_id': 'WO-WEB', 'batch_no': 'FG-20261001-001'}).json()
    assert result['status'] == 'COMPLETED'
    assert result['web_references'] == []


def test_no_key_returns_unavailable(monkeypatch):
    web, schema = modules()
    monkeypatch.delenv('TAVILY_API_KEY', raising=False)
    result = schema.WebSearchResult.model_validate_json(web.web_search.invoke({'query': QUERY, 'state': {}}))
    assert result.outcome == 'ERROR'
    assert result.reason == 'NOT_CONFIGURED'
    assert result.references == []


@pytest.mark.parametrize('content', [TEXT, json.dumps({'results': [
    {'title': 'Public technical note', 'url': 'https://example.org/polyamide', 'content': 'Public background'}]})])
def test_response_normalization(content):
    web, schema = modules()
    result = web.parse_search_reply(schema.WebSearchRequest(query=QUERY), ToolMessage(content=content, tool_call_id='t'))
    assert result.outcome == 'FOUND'
    assert result.query == QUERY
    assert str(result.references[0].url) == 'https://example.org/polyamide'
    assert result.references[0].summary


def test_strict_contracts():
    _, schema = modules()
    for query in [42, '', '   ']:
        with pytest.raises(ValidationError):
            schema.WebSearchRequest(query=query)
    with pytest.raises(ValidationError):
        schema.WebSearchRequest(query=QUERY, unexpected=True)
    with pytest.raises(ValidationError):
        schema.WebReference(title='x', url='javascript:alert(1)', summary='x')


def scripted_search(monkeypatch):
    from python_service import agent_graph
    original = agent_graph.mock_actor
    check = agent_graph.evidence_error
    def actor(state):
        if not state.get('web_references'):
            return agent_graph.call_message('web_search', {'query': QUERY})
        return original(state)
    def evidence_error(state, name, observation):
        assert name != 'web_search', '联网结果不得进入必查证据校验'
        return check(state, name, observation)
    monkeypatch.setattr(agent_graph, 'mock_actor', actor)
    monkeypatch.setattr(agent_graph, 'evidence_error', evidence_error)


@pytest.mark.parametrize('configured', [False, True])
def test_real_graph_keeps_web_separate(monkeypatch, configured):
    web, schema = modules()
    if configured:
        monkeypatch.setenv('TAVILY_API_KEY', 'local-test-only')
    else:
        monkeypatch.delenv('TAVILY_API_KEY', raising=False)
    async def response(request):
        return ToolMessage(content=TEXT, tool_call_id='mcp-test')
    monkeypatch.setattr(web, '_mcp_search', response)
    scripted_search(monkeypatch)
    from python_service.runtime import TraceService
    from python_service.tools import REQUIRED_TOOLS
    from python_service.evals.graders import TrajectoryGrader, SemanticGrader
    service = TraceService(mode='mock')
    identity = schema.Identity(tenant_id='demo', user_id='alice', role='quality_engineer', trace_id='t')
    request = schema.DiagnoseRequest(work_order_id='WO-WEB-GRAPH', batch_no='FG-20261001-001')
    result = service.diagnose(request, identity)
    state = service.graph.get_state(service.config(request.work_order_id, identity)).values
    assert result.status == 'COMPLETED'
    assert set(state['evidence']) == set(REQUIRED_TOOLS)
    assert len(result.web_references) == 1
    assert result.web_references[0].outcome == ('FOUND' if configured else 'ERROR')
    assert not result.episodic_memory
    assert result.trajectory[0].tool == 'web_search'
    assert TrajectoryGrader().grade(result).score == 1
    assert SemanticGrader(mode='mock').grade(result).score == 1
    assert service.diagnose(request, identity) == result


def test_web_numbers_cannot_become_factory_evidence(monkeypatch):
    web, schema = modules()
    monkeypatch.setenv('TAVILY_API_KEY', 'local-test-only')
    async def response(request):
        return ToolMessage(content=TEXT + ' 999999', tool_call_id='mcp-test')
    monkeypatch.setattr(web, '_mcp_search', response)
    scripted_search(monkeypatch)
    from python_service.runtime import TraceService
    from python_service.evals.graders import validate_report
    identity = schema.Identity(tenant_id='demo', user_id='alice', role='quality_engineer', trace_id='t')
    result = TraceService(mode='mock').diagnose(schema.DiagnoseRequest(work_order_id='WO-NUM', batch_no='FG-20261001-001'), identity)
    changed = result.report.model_copy(update={'d4_root_cause': 'Temperature is 999999.'})
    assert 'unsupported numeric assertion in report prose' in validate_report(changed, result.trajectory)


def test_at_most_one_transport_search(monkeypatch):
    web, schema = modules()
    monkeypatch.setenv('TAVILY_API_KEY', 'local-test-only')
    calls = []
    async def response(request):
        calls.append(request.query)
        return ToolMessage(content=TEXT, tool_call_id='mcp-test')
    monkeypatch.setattr(web, '_mcp_search', response)
    first = schema.WebSearchResult.model_validate_json(web.web_search.invoke({'query': QUERY, 'state': {}}))
    second = schema.WebSearchResult.model_validate_json(web.web_search.invoke({
        'query': QUERY, 'state': {'web_references': [first.model_dump(mode='json')]}}))
    assert calls == [QUERY]
    assert second.reason == 'SEARCH_LIMIT_REACHED'


def test_transport_error_does_not_leak_secret(monkeypatch):
    web, schema = modules()
    monkeypatch.setenv('TAVILY_API_KEY', 'never-echo-this')
    async def failure(request):
        raise RuntimeError('never-echo-this')
    monkeypatch.setattr(web, '_mcp_search', failure)
    raw = web.web_search.invoke({'query': QUERY, 'state': {}})
    assert 'never-echo-this' not in raw
    assert schema.WebSearchResult.model_validate_json(raw).reason == 'MCP_UNAVAILABLE'


def test_unexpected_response_is_not_empty_success(monkeypatch):
    web, schema = modules()
    monkeypatch.setenv('TAVILY_API_KEY', 'local-test-only')
    async def response(request):
        return ToolMessage(content='unexpected provider output', tool_call_id='mcp-test')
    monkeypatch.setattr(web, '_mcp_search', response)
    result = schema.WebSearchResult.model_validate_json(web.web_search.invoke({'query': QUERY, 'state': {}}))
    assert result.reason == 'INVALID_RESPONSE'


def test_real_stdio_adapter_and_toolnode(monkeypatch):
    import sys
    from pathlib import Path
    from mcp import StdioServerParameters
    web, schema = modules()
    monkeypatch.setenv('TAVILY_API_KEY', 'local-test-only')
    def parameters(cwd):
        return StdioServerParameters(command=sys.executable,
            args=[str(Path(__file__).with_name('stdio_server_fixture.py'))], cwd=cwd,
            env={'TAVILY_API_KEY': 'local-test-only'})
    monkeypatch.setattr(web, '_server_parameters', parameters)
    scripted_search(monkeypatch)
    from python_service.runtime import TraceService
    identity = schema.Identity(tenant_id='demo', user_id='alice', role='quality_engineer', trace_id='t')
    result = TraceService(mode='mock').diagnose(schema.DiagnoseRequest(work_order_id='WO-STDIO', batch_no='FG-20261001-001'), identity)
    assert result.status == 'COMPLETED'
    reference = result.web_references[0]
    assert reference.outcome == 'FOUND', reference.reason
    assert str(reference.references[0].url) == 'https://example.org/local-mcp'


def test_timeout_is_optional_and_sanitized(monkeypatch):
    import asyncio
    web, schema = modules()
    monkeypatch.setenv('TAVILY_API_KEY', 'local-test-only')
    monkeypatch.setattr(web, 'SEARCH_TIMEOUT_SECONDS', 0.01)
    async def slow(request):
        await asyncio.sleep(1)
    monkeypatch.setattr(web, '_mcp_search', slow)
    result = schema.WebSearchResult.model_validate_json(web.web_search.invoke({'query': QUERY, 'state': {}}))
    assert result.reason == 'TIMEOUT'


def test_missing_adapter_is_optional(monkeypatch):
    import builtins
    web, schema = modules()
    monkeypatch.setenv('TAVILY_API_KEY', 'local-test-only')
    original = builtins.__import__
    def guarded(name, *args, **kwargs):
        if name.startswith('langchain_mcp_adapters'):
            raise ImportError('adapter is not installed')
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', guarded)
    result = schema.WebSearchResult.model_validate_json(web.web_search.invoke({'query': QUERY, 'state': {}}))
    assert result.reason == 'MISSING_DEPENDENCY'


def test_mock_never_uses_search_even_with_key(monkeypatch):
    web, schema = modules()
    monkeypatch.setenv('TAVILY_API_KEY', 'local-test-only')
    async def forbidden(request):
        pytest.fail('mock 不应进行联网搜索')
    monkeypatch.setattr(web, '_mcp_search', forbidden)
    from python_service.runtime import TraceService
    identity = schema.Identity(tenant_id='demo', user_id='alice', role='quality_engineer', trace_id='t')
    result = TraceService(mode='mock').diagnose(schema.DiagnoseRequest(work_order_id='WO-MOCK', batch_no='FG-20261001-001'), identity)
    assert result.status == 'COMPLETED'
    assert result.web_references == []


def test_model_schema_does_not_expose_state():
    web, _ = modules()
    assert set(web.web_search.tool_call_schema.model_json_schema()['properties']) == {'query'}
