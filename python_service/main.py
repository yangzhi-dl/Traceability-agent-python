"""HTTP 边界。演示模式仅限本地；生产环境必须配置网关密钥。"""
import hmac
import os
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import ValidationError

from .agent_graph import TraceService
from .schemas import DiagnoseRequest, Identity, ResumeRequest, ServiceError, TraceResponse


def trusted_identity(
    x_gateway_token: Annotated[str | None, Header()] = None,
    x_tenant_id: Annotated[str, Header()] = 'demo',
    x_user_id: Annotated[str, Header()] = 'demo-engineer',
    x_user_role: Annotated[str, Header()] = 'quality_engineer',
    x_trace_id: Annotated[str, Header()] = 'demo-trace',
) -> Identity:
    secret = os.getenv('GATEWAY_TOKEN')
    if secret and (not x_gateway_token or not hmac.compare_digest(secret, x_gateway_token)):
        raise HTTPException(401, 'Invalid gateway authentication')
    # 未配置密钥时即为显式声明的 localhost 演示，绝不视为已认证服务。
    try:
        return Identity(tenant_id=x_tenant_id, user_id=x_user_id, role=x_user_role, trace_id=x_trace_id)
    except ValidationError:
        raise HTTPException(422, 'Invalid identity headers') from None


def create_app(service: TraceService | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app):
        if os.getenv('APP_ENV', 'demo') != 'demo' and not os.getenv('GATEWAY_TOKEN'):
            raise RuntimeError('GATEWAY_TOKEN is required outside explicit demo mode')
        app.state.service = service or TraceService(mode=os.getenv('AGENT_MODE', 'auto'), redis_url=os.getenv('REDIS_URL'))
        yield
        if service is None:
            app.state.service.close()

    app = FastAPI(title='Independent traceability MVP', lifespan=lifespan)

    @app.exception_handler(ServiceError)
    async def service_error(_request, exc):
        return JSONResponse(status_code=exc.status_code, content={'detail': str(exc)})

    @app.post('/api/v1/trace/diagnose', response_model=TraceResponse)
    def diagnose(body: DiagnoseRequest, identity: Annotated[Identity, Depends(trusted_identity)]):
        return app.state.service.diagnose(body, identity)

    @app.post('/api/v1/trace/resume', response_model=TraceResponse)
    def resume(body: ResumeRequest, identity: Annotated[Identity, Depends(trusted_identity)]):
        return app.state.service.resume(body, identity)

    @app.post('/api/v1/trace/diagnose/stream')
    def diagnose_stream(body: DiagnoseRequest, identity: Annotated[Identity, Depends(trusted_identity)]):
        # 只发一个终结性的 SSE 事件，用于验证传输层互通，而非逐 token 流式输出。
        # 在响应头发出前先同步执行，使鉴权/冲突错误仍保留正确的 HTTP 状态码。
        result = app.state.service.diagnose(body, identity)
        return StreamingResponse(iter([f'event: result\ndata: {result.model_dump_json()}\n\n']), media_type='text/event-stream')

    @app.get('/health')
    def health():
        return {'status': 'ok', 'mode': app.state.service.mode,
                'persistence': 'redis' if app.state.service.redis else 'memory'}

    return app


app = create_app()
