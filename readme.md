# 独立全栈不良品追溯 MVP

## 可选 Tavily MCP 搜索

新增 `python_service/web_search.py`，经官方 `langchain-mcp-adapters.load_mcp_tools` 和 MCP SDK stdio 客户端，启动固定版本 `npx -y tavily-mcp@0.2.22`。只选择 `tavily_search`/`tavily-search`，不暴露爬取、提取等其他能力。

- `READ_TOOLS` 和 `REQUIRED_TOOLS` 仍只有原四项；Actor 与只读 ToolNode 额外绑定 `web_search`。
- 未设置 `TAVILY_API_KEY` 时不启动子进程、不访问网络，返回 `ERROR / NOT_CONFIGURED`。依赖缺失、超时或服务失败也返回脱敏降级结果。
- `mock_actor` 不使用搜索，即使设置 Key，默认 mock 诊断仍保持确定性。
- 搜索是可选背景资料；新字段 `web_references` 保存查询词、状态、标题、URL 和摘要，并在 `TraceResponse` 返回。失败尝试也保留状态用于审计。
- 新请求、结果与引用均经过 Pydantic v2 校验；Graph 检查点仅保存 `model_dump(mode="json")` 的快照，读取时重新校验。
- 搜索结果不进入 `evidence`、`evidence_error` 或必查顺序；搜索失败不消耗反思重试次数。网页数字不参与工厂报告的数字白名单。报告仍只以内部证据生成，外部参考单独返回。
- 每个诊断线程至多尝试一次搜索；再次调用仅返回 `SEARCH_LIMIT_REACHED`，不再访问 Tavily。恢复过程中若外部请求已完成但检查点尚未保存，仍存在重放窗口；本实现不宣称外部 API exactly-once。
- 只发送公开型号、材料或标准关键词。不要把内部工单、批次、人员、供应商或实测数据放入查询词；网页内容是不可信数据，不是操作指令。

在已经安装主依赖的项目中，使用**系统 Python 的 pip**给 `.venv` 安装可选 MCP 依赖，不要求 `.venv` 自带 pip：

```powershell
python -m pip --python .venv\Scripts\python.exe install langchain-mcp-adapters==0.2.2 mcp==1.30.0 -c requirements.lock.txt
```

这两项依赖只写入 `requirements-integrations.txt`，没有加入主依赖。不要为了只安装 MCP 而一次性安装全部可选重型 RAG 依赖。运行 stdio Server 还需要 Node.js/npx；首次启动可能需要下载 npm 包，45 秒超时会降级为 `TIMEOUT`，可先预热 npm 缓存。

在本机安全设置环境变量 `TAVILY_API_KEY`，不要将真实 Key 写入源码、命令记录或聊天。服务必须继承该环境变量。只有真实 LLM 模式会自主选择搜索；该模式还需要原来的模型配置。

```powershell
.\.venv\Scripts\python.exe -m pytest python_service/tests -q
.\.venv\Scripts\python.exe -m pytest tests_mcp -q
.\.venv\Scripts\python.exe scripts\verify_tavily.py
```

最后一条是显式真实联网验收，会消耗一次 Tavily 搜索调用：固定一条公开查询，经实际 Graph / ToolNode / MCP 写入 `web_references`，检查四个必查证据仍完整。没有 Key 时退出码为 77（跳过），不是通过。普通 `tests_mcp` 只使用离线夹具；其中 stdio 用例确实运行本地 MCP Server 和官方适配器，但不是 Tavily 云端测试。

本次仅更新原契约测试中“绑定工具总数为 4”的断言，改为检查“四个原必查工具 + web_search”；原有 20 个测试没有删减。审批、冻结及主工具文件不变。

参考：[LangChain load_mcp_tools 接口](https://reference.langchain.com/python/langchain-mcp-adapters/tools/load_mcp_tools)、[Tavily 官方 MCP Server](https://github.com/tavily-ai/tavily-mcp)。以本次安装的适配器 0.2.2、MCP 1.30.0 与 npm 0.2.22 源码核验为准，不依赖未固定的 latest。

本目录展示：质检异常 → ERP 物料/BOM + 机台传感器 → 同型号 SOP → 8D 诊断草稿；错误或证据不足触发最多三次 Reflexion；冻结原料批次通过真实 LangGraph `interrupt()` 等待主管批准。

旧 AgentScope 工程与 `ref_repos/` 保持只读。新项目使用真实 FastAPI/Pydantic/LangChain/LangGraph；默认把模型决策、外部工业系统和检索服务替换为明确标注的本地模拟。**安装 Python 包后，不需要任何外部服务或 API Key 就能运行。** 这不表示 Python 第三方包零依赖。

## 立即运行（PowerShell，当前目录为 fullstack_agent_mvp）

已建好的 `.venv` 可直接使用：

```powershell
.\.venv\Scripts\python.exe -m pytest python_service/tests -q
.\.venv\Scripts\python.exe -m python_service.evals.run_eval --mode mock
.\.venv\Scripts\python.exe -m python_service.evals.run_eval --mode mock --policy baseline
$env:AGENT_MODE='mock'
.\.venv\Scripts\python.exe -m uvicorn python_service.main:app --host 127.0.0.1 --port 8000
```

新机器使用 Python 3.11：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
```

`requirements.txt` 是主依赖范围，`requirements.lock.txt` 是本次测试的完整固定版本快照。不要使用根目录旧 Java 项目的构建命令运行本工程。

## 完整审批演示

启动服务后，在另一个终端执行以下代码。它仅操作内置 Mock ERP：

```powershell
$headers=@{'X-Tenant-Id'='demo';'X-User-Id'='engineer-1';'X-User-Role'='quality_engineer';'X-Trace-Id'='demo-trace-1'}
$body=@{work_order_id='WO-DEMO-001';batch_no='FG-20261001-001';request_freeze=$true} | ConvertTo-Json
$waiting=Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/v1/trace/diagnose' -Headers $headers -ContentType 'application/json' -Body $body
$waiting.status  # WAITING_APPROVAL，尚未冻结
$headers['X-User-Id']='supervisor-1'
$headers['X-User-Role']='supervisor'
$approval=@{work_order_id='WO-DEMO-001';approval_id=$waiting.approval_id;approved=$true} | ConvertTo-Json
$done=Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/v1/trace/resume' -Headers $headers -ContentType 'application/json' -Body $approval
$done.status  # COMPLETED，仅指诊断草稿完成
$done.report
```

同租户同工单相同参数重复请求返回现有结果；改变批次或冻结意图返回 409。审批 ID、批准/拒绝决定不可在重放中替换。不同用户不能接管现有工单，主管可审批本租户工单。`thread_id` 在服务端由 `tenant_id:work_order_id` 推导。

`/api/v1/trace/diagnose/stream` 发送一个最终 `result` SSE 事件，展示 WebClient SSE 兼容；它不是逐 token 或节点实时流。主要接口为同步结果 HTTP JSON，Java 使用非阻塞 WebClient 调用。

## 模式和接入边界

| 能力 | 默认实际执行 | 可选接入与限制 |
|---|---|---|
| 状态机/工具/审批 | 真实 StateGraph、ToolNode、interrupt、MemorySaver | Memory 仅一个进程，重启丢状态；Redis 模式才支持进程间恢复 |
| Actor/Reflector/8D | 确定性模拟，报告数值来自工具观察 | `AGENT_MODE=llm` 或自动检测 Key；用 ChatOpenAI，需 `OPENAI_API_KEY`，可设 `OPENAI_MODEL`；不读取或修改旧配置 |
| 评测 | 真实轨迹 + 本地规则裁判 | `--mode llm` 启用结构化语义裁判，`JUDGE_MODEL` 可指定独立模型；失败记录为失败，不伪装规则通过 |
| ERP/MES/库存/CAPA | 明确的合成 Mock | 没有真实 ERPNext 写连接。实际写适配器必须将审批 ID 幂等键与冻结/CAPA 放入外部系统事务 |
| Hybrid RAG | BM25 + 本地 token cosine + 本地 lexical rerank；严格型号过滤 | `RAG_BACKEND=real` 调用真实 Milvus 与本地 embedding/BGE CrossEncoder，需预装模型与集合；不自动下载模型 |
| Java/MySQL/Redis/JWT | 独立 Spring Boot 示例代码 | 见 `springboot_gateway_demo/readme.md`；运行需要这些服务和认证签发方 |

不携带 `OPENAI_API_KEY` 时自动使用 Mock；若已有 Key 且只想离线体验，显式使用 `AGENT_MODE=mock` / `--mode mock`。真实模式是有费用的网络调用入口，本次自动验证不调用真实模型。

## 可选 Redis 和真实检索

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-integrations.txt
$env:REDIS_URL='redis://127.0.0.1:6379/0'
```

RedisSaver 需要 Redis 8 或带 JSON/Search 的 Redis Stack；初始化会创建 checkpoint 索引。生产接入需持久化/AOF、备份、独立凭据和明确保留策略。Python API 锁与 Java Redisson 锁使用不同前缀，避免跨服务互相死锁；Python 锁租期为 1,200 秒，仍应为真实长任务设计续租、超时及监控。

真实检索参数：`MILVUS_URI`、可选 `MILVUS_TOKEN`、`MILVUS_COLLECTION`（默认 `trace_sops`）、`EMBEDDING_MODEL_PATH`、`BGE_RERANKER_PATH`。两个模型路径必须是已存在的本地模型。Milvus 集合需要 `id` 字符串主键、`model_code/text/kind`、`limits` JSON 和匹配 embedding 维度的向量字段；数据内容与 `fixtures.SOPS` 一致，索引使用余弦相似度。模型先过滤，再 BM25/向量双路召回、RRF 合并和 BGE 重排。

## 认证边界

`APP_ENV=demo` 且没有 `GATEWAY_TOKEN` 时，仅用于绑定 `127.0.0.1` 的本机演示，身份头可手工填写。设置共享的 `GATEWAY_TOKEN` 后，Python 要求对应 `X-Gateway-Token`。非 demo 模式缺少该密钥会启动失败。真实部署仅允许受信网关经私网/TLS访问 Python；用户身份和角色由 Java 验证 JWT 后映射，不能让公网用户直接伪造这些头。

角色：viewer 可只读诊断，不能冻结；quality_engineer 可提出冻结请求；supervisor 可批准/拒绝。审批目标从已校验 ERP 观察提取，客户端不提交替代原料批次。生产工单 ACL、组织层级及审批职责分离仍需按实际系统补齐。

## 如何解读评测

- 黄金集十条、每条三次独立 service/checkpointer/工单，保存完整成功/失败工具记录与判分依据。
- Pass^1 = 所有运行成功次数 / 总运行次数；Pass^3 = 三次全部成功的样本数 / 样本数。成功同时要求轨迹、语义/规则和黄金断言通过。
- 包含正确拒绝与正确降级，所以 Pass^3 不是报告产出率。
- 本地 claw-eval 源码的 `(c/n)^3` 估计另列，不与三次全过比例或 `pass@3` 混淆。
- baseline 是故意关闭纠错行为的确定性消融，对照证明的是反馈控制逻辑；不是历史生产版本，也不能据此声称 LLM 鲁棒性提高多少。
- 同一十条固定合成样本反复跑是回归验证，没有独立 holdout、业务专家盲评或生产效果证据。规则裁判只能检查有限字段/结构/数值，复杂因果语义仍需真实裁判及人工校准。

产物：`evidence/mock-optimized/report.md`、`evidence/mock-baseline/report.md`、各目录 `trials.json`。详细来源见 [sources.md](sources.md)，学习与面试见 [ultimate_interview_guide.md](ultimate_interview_guide.md)。提示词给出的 64→94、76→95、58→86 只能作为假设故事，不是本工程实测。
