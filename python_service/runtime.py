"""服务门面：可信身份、检查点归属、请求/审批重放。"""
from contextlib import ExitStack, contextmanager
from threading import Lock, RLock
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from .schemas import DiagnoseRequest, Identity, ResumeRequest, ServiceError, TraceResponse


class TraceService:
    def __init__(self, mode: str = 'auto', redis_url: str | None = None):
        from .agent_graph import build_graph, selected_mode
        self.mode = selected_mode(mode)
        self.stack = ExitStack()
        self.redis = None
        if redis_url:
            try:
                from langgraph.checkpoint.redis import RedisSaver
                from redis import Redis
            except ImportError as exc:
                raise RuntimeError(
                    'REDIS_URL set but Redis checkpoint deps are missing; '
                    'install with: uv pip install -r requirements-integrations.txt'
                ) from exc
            saver = self.stack.enter_context(RedisSaver.from_conn_string(redis_url))
            saver.setup()  # 需 Redis Stack / Redis 8（含 JSON + Search 模块），而非普通 Redis 7。
            self.redis = Redis.from_url(redis_url)
            self.stack.callback(self.redis.close)
        else:
            saver = InMemorySaver()
        self.graph = build_graph(saver, self.mode)
        self.locks: dict[str, Lock] = {}
        self.lock_guard = RLock()

    def close(self):
        self.stack.close()

    @staticmethod
    def config(order: str, identity: Identity) -> dict:
        return {'configurable': {'thread_id': f'{identity.tenant_id}:{order}'}, 'recursion_limit': 90}

    @contextmanager
    def locked(self, thread: str):
        if self.redis:
            # 这也会串行化直接调用 Python 服务的请求；与网关锁使用不同的键前缀。
            mutex = self.redis.lock(f'trace:python:{thread}', timeout=1200, blocking=False)
        else:
            with self.lock_guard:
                mutex = self.locks.setdefault(thread, Lock())
        acquired = mutex.acquire(blocking=False)
        if not acquired:
            raise ServiceError(409, 'Work order is already executing')
        try:
            yield
        finally:
            mutex.release()

    def response(self, config: dict) -> TraceResponse:
        snapshot = self.graph.get_state(config)
        state = snapshot.values
        waiting = bool(snapshot.next) and any(t.interrupts for t in snapshot.tasks)
        return TraceResponse(thread_id=state['thread_id'],
            status='WAITING_APPROVAL' if waiting else state.get('status', 'PARTIAL'),
            approval_id=state['approval_id'] if waiting or state.get('approval') else None,
            report=state.get('report'), trajectory=state.get('trajectory', []),
            episodic_memory=state.get('episodic_memory', []),
            stop_reason='HUMAN_APPROVAL_REQUIRED' if waiting else state.get('stop_reason', 'INCOMPLETE'))

    def diagnose(self, request: DiagnoseRequest, identity: Identity, *, fault: str = 'none', policy: str = 'optimized') -> TraceResponse:
        config = self.config(request.work_order_id, identity)
        thread = config['configurable']['thread_id']
        with self.locked(thread):
            existing = self.graph.get_state(config)
            if existing.values:
                if existing.values['identity']['user_id'] != identity.user_id and identity.role != 'supervisor':
                    raise ServiceError(403, 'Work order belongs to another user')
                if existing.values['request'] != request.model_dump():
                    raise ServiceError(409, 'Work order already exists with different parameters')
                # 待处理的挂起中断必须显式恢复；失败的非中断节点可以直接重放。
                if existing.next and not any(t.interrupts for t in existing.tasks):
                    self.graph.invoke(None, config)
                return self.response(config)
            initial = {'messages': [], 'thread_id': thread, 'request': request.model_dump(),
                       'identity': identity.model_dump(), 'evidence': {}, 'trajectory': [],
                       'episodic_memory': [], 'retries': 0, 'actor_turns': 0, 'fault': fault,
                       'policy': policy, 'approval_id': str(uuid4()), 'report': None,
                       'stop_reason': 'STARTED'}
            self.graph.invoke(initial, config)
            return self.response(config)

    def resume(self, request: ResumeRequest, identity: Identity) -> TraceResponse:
        if identity.role != 'supervisor':
            raise ServiceError(403, 'Only supervisor can approve')
        config = self.config(request.work_order_id, identity)
        with self.locked(config['configurable']['thread_id']):
            snapshot = self.graph.get_state(config)
            if not snapshot.values:
                raise ServiceError(404, 'Work order does not exist in this tenant')
            state = snapshot.values
            if state['approval_id'] != request.approval_id:
                raise ServiceError(409, 'Approval ID does not match pending action')
            previous = state.get('approval')
            if previous:
                if previous['approved'] != request.approved:
                    raise ServiceError(409, 'Approval decision is immutable')
                if snapshot.next:
                    self.graph.invoke(None, config)  # 审批后恢复因传输中断/崩溃而挂起的执行
                return self.response(config)
            if not any(t.interrupts for t in snapshot.tasks):
                raise ServiceError(409, 'No pending approval')
            decision = {'approved': request.approved, 'approval_id': request.approval_id,
                        'role': identity.role, 'approver': identity.user_id, 'trace_id': identity.trace_id}
            self.graph.invoke(Command(resume=decision), config)
            return self.response(config)
