# 独立全栈追溯 MVP 实施计划

**Goal:** 在新目录交付可离线演示的真实 LangGraph 诊断、Reflexion、人工审批及 Pass^3 评测闭环；旧代码和参考仓库只读。

**Architecture:** Java 负责身份、工单、分布式互斥与业务持久化；Python 负责图执行与证据。默认 Mock 外部系统 + MemorySaver；真实 LLM、RedisSaver、Milvus/BGE 均由显式配置启用。Mock 模式仍执行 LangChain Tools、ToolNode、StateGraph 和 interrupt。

**Tech Stack:** Python 3.11、FastAPI、Pydantic v2、LangChain、LangGraph；Java 17、Spring Boot 3、MyBatis-Plus、MySQL、Redis/Redisson、WebClient。

用户已指定完整架构与文件清单，按该规格直接执行；不变更旧运行时、不提交 Git。依 subagent-driven-development 技能把独立 Java 网关交给子任务，主任务实现 Python 并负责集成、规格和质量审查。

- [x] 只读提取旧领域字段、OpenJudge 裁判契约、claw-eval 轨迹及统计公式，保存来源与保护文件哈希。
- [x] 先写行为测试：故障自愈、预算耗尽、遗漏证据、HITL、越权、重放、型号隔离和裁判反例。
- [x] 实现 schemas.py、tools.py、agent_graph.py：结构化证据、五工具、条件路由、最多三次反思、真实 interrupt。
- [x] 实现 main.py：网关认证、所有者隔离、请求幂等、审批绑定及持久化选项。
- [x] 实现 evals：十条黄金样本、确定性轨迹评分、规则/真实 LLM 语义评分、独立三次试验、Bad Case 报表。
- [x] 实现独立可编译的 Java 网关示范与数据库表结构，验证 HTTP 契约。
- [x] 编写 README、来源说明、五章面试指南：真实能力/接入边界/示例数字明确区分。
- [x] 跑最小 Python 测试、30 次离线评测、Java 编译；核对所有受保护文件哈希。

实施记录：Java/文档子任务因账户用量中断，主任务随后接手完成；所有结论以 `evidence/VERIFICATION.md` 的实际验证为准。

## 核心契约

- `POST /api/v1/trace/diagnose`: `{work_order_id,batch_no,request_freeze}`。
- `POST /api/v1/trace/resume`: `{work_order_id,approval_id,approved}`。
- 请求头：`X-Gateway-Token`、`X-Tenant-Id`、`X-User-Id`、`X-User-Role`、`X-Trace-Id`；角色 `viewer / quality_engineer / supervisor`。
- `thread_id = tenant_id + ':' + work_order_id`；Python 从可信头推导，不接受客户端指定 thread_id。
- 响应含 `thread_id,status,report,approval_id,trajectory,episodic_memory,stop_reason`；状态 `COMPLETED / WAITING_APPROVAL / PARTIAL / DENIED / REJECTED`。
- `approval_id` 由服务生成并保存在 checkpoint，冻结批次从已验证 ERP 证据获取；客户端不能替换目标。
- 默认无外部服务依赖不等于无 Python 包依赖。依赖装好后，Mock 运行不需要 Key、Redis、Milvus、MySQL。
- 本地 claw-eval 的 `compute_pass_hat_k` 是 `(c/n)^k`；用户要求的三次全过比例单独实现并明确标为经验 Pass^3，同时给出原公式估计，避免混淆 `pass@3`。

## 验收命令（在本目录）

```powershell
.\.venv\Scripts\python.exe -m pytest python_service/tests -q
.\.venv\Scripts\python.exe -m python_service.evals.run_eval --mode mock
.\.venv\Scripts\python.exe -m python_service.evals.run_eval --mode mock --policy baseline
mvn -f springboot_gateway_demo/pom.xml -DskipTests compile
```
