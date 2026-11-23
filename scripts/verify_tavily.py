"""配置 Key 后显式运行的一次真实 Tavily 验收；缺少 Key 时跳过，不伪造成功。"""
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    if not os.getenv('TAVILY_API_KEY', '').strip():
        print('SKIPPED: TAVILY_API_KEY is not configured; no Tavily request was made.')
        return 77
    from python_service import agent_graph
    from python_service.runtime import TraceService
    from python_service.schemas import DiagnoseRequest, Identity
    from python_service.tools import REQUIRED_TOOLS

    original = agent_graph.mock_actor
    query = 'polyamide moisture processing technical reference'

    def actor(state):
        if not state.get('web_references'):
            return agent_graph.call_message('web_search', {'query': query})
        return original(state)

    # 验收只固定决策路径，MCP/Tavily 搜索调用是真实的；不宣称验证了 LLM 决策质量。
    with patch.object(agent_graph, 'mock_actor', actor):
        service = TraceService(mode='mock')
        try:
            identity = Identity(tenant_id='demo', user_id='acceptance', role='quality_engineer', trace_id='tavily-check')
            request = DiagnoseRequest(work_order_id='WEB-' + uuid4().hex, batch_no='FG-20261001-001')
            result = service.diagnose(request, identity)
            state = service.graph.get_state(service.config(request.work_order_id, identity)).values
            reference = result.web_references[0]
            print(json.dumps({'diagnosis': result.status, 'query': reference.query,
                'outcome': reference.outcome, 'reason': reference.reason,
                'urls': [str(row.url) for row in reference.references],
                'web_references': len(result.web_references), 'evidence_tools': sorted(state['evidence'])}, ensure_ascii=False))
            if (result.status != 'COMPLETED' or reference.outcome != 'FOUND'
                    or not reference.references or set(state['evidence']) != set(REQUIRED_TOOLS)):
                return 1
            print('PASS: real Tavily MCP result persisted separately from mandatory evidence.')
            return 0
        finally:
            service.close()


if __name__ == '__main__':
    raise SystemExit(main())
