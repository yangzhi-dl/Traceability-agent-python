# Spring Boot 网关示范

Java 17 / Spring Boot 3.5.13。源文件按需求直接放在本目录，pom 的 `sourceDirectory` 和 `includes` 明确只编译根部 Java 文件，测试位于 `tests/`。这是独立 Maven 工程，不依赖旧 AgentScope 工程。

## 运行依赖

1. 在新的 MySQL 8 数据库显式执行 `schema.sql`；程序不自动建表，不访问旧库。
2. 启动 Redis。若 Python 同时使用 RedisSaver，需 Redis 8 或带 JSON/Search 的 Redis Stack。
3. 准备 OAuth2/OIDC 签发方。JWT 必须包含 `iss`、`aud`、有效签名/时效、`sub`、`tenant_id`、`roles` 字符串列表；角色为 `quality_engineer` / `supervisor` / `viewer`。
4. Python 与 Java 使用相同 `GATEWAY_TOKEN`；Python 绑定私网或本机地址。

必填环境变量：`MYSQL_URL`、`MYSQL_USER`、`MYSQL_PASSWORD`、`GATEWAY_TOKEN`、`JWT_ISSUER`、`JWT_JWK_URI`。可选：`PYTHON_URL`（默认 http://127.0.0.1:8000）、`GATEWAY_REDIS_ADDRESS`（默认 redis://127.0.0.1:6379）、`JWT_AUDIENCE`（默认 trace-gateway）。凭据从环境注入，不写入源码。

```powershell
$env:JAVA_HOME='D:\jdk17'
$env:Path='D:\jdk17\bin;' + $env:Path
mvn test
mvn spring-boot:run
```

本机全局 Maven settings 含无效的示例镜像，本次验证使用了新目录 `.cache/settings.xml` 覆盖全局/用户设置，缓存只写 `.m2/`：

```powershell
mvn -gs .cache/settings.xml -s .cache/settings.xml '-Dmaven.repo.local=.m2' test
```

普通机器使用默认 Maven 设置即可。该本地 settings 指向旧 Maven artifact 目录仅用于只读复用依赖，不修改旧目录。

## HTTP 闭环

`POST :8081/api/v1/trace/diagnose` 携带 `Authorization: Bearer ...`：

```json
{"work_order_id":"WO-DEMO-001","batch_no":"FG-20261001-001","request_freeze":true}
```

网关验证 JWT、推导角色与租户，在 `trace:gateway:{tenant}:{order}` 上取得锁，建立 MySQL 工单，通过 WebClient 调 Python。返回 WAITING_APPROVAL 后落库 approval_id，并释放锁，不在人工等待期间持锁。

主管使用自己的 JWT 调 `POST :8081/api/v1/trace/resume`：

```json
{"work_order_id":"WO-DEMO-001","approval_id":"使用实际返回值","approved":true}
```

网关再次获取同一把锁，将审批决定和审批人持久化，然后调用 Python /resume；最终 `report` JSON 与结果存到 MySQL。`GET /api/v1/trace/work-orders/{id}` 允许本租户工单所有者或主管查看。

## 需要掌握的边界

- `Actor.from` 只接收 Spring Security 验证后的 Jwt；从不信任浏览器提交的身份/角色头。
- `TraceWorkflow.withLock` 使用 Redisson 显式 owner ID 与 watchdog，`Mono.usingWhen` 在正常、异常、取消三条路径释放锁。数据库读写在 boundedElastic，WebClient 不阻塞事件线程。
- MySQL 唯一键 + version 条件更新约束并发写；版本缓存带 60 秒 TTL，只在数据库授权后读取；缓存失败不推翻已经落库的报告。
- 相同 diagnose 请求重放返回现有快照，不同参数 409。相同审批决定可重试；批准改拒绝或替换 approval_id 返回 409。
- HTTP 与 MySQL 没有跨服务 ACID 事务。网络错误记录 RETRYABLE_ERROR；用同工单/审批 ID 重试，从 Python checkpoint 恢复结果。客户端断开时 RUNNING 也可用相同请求恢复。持久化 Python checkpoint 是真实重启恢复的前提。
- Redisson 不能保证外部 ERP exactly-once。真实 ERP 适配器必须以 `thread_id:approval_id:raw_batch` 幂等键原子完成冻结/CAPA；本工程只有确定性 Mock ERP。
- 生产升级还需要任务队列/超时回收、审批审计追加表、组织 ACL、敏感报告保留策略、可观测性和故障演练。当前测试使用 Mock Mapper/Redis/HTTP，不宣称已经验证 MySQL/Redis/JWT 签发方的端到端联调。
- `PythonAgentWebClient.diagnoseEvents` 可消费 Python 的单条最终结果 SSE；主业务接口使用 JSON，未实现逐 token SSE。

测试覆盖 JWT claim 映射、受信头转发、诊断→挂起→审批→报告持久化调用、审批重放、网络失败释放锁/重试、角色和跨线程结果校验。实际外部数据库/Redis 服务没有在测试中启动。
