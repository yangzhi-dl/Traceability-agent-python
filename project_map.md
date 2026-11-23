# fullstack_agent_mvp 目录结构映射

核对日期：2026-11-09。依据当前文件清单、Python 入口与 Graph 注册、Runtime、工具、Java 调用关系整理；本次仅生成导航文档，没有重新运行服务、测试或评测。

项目根目录：`C:\Users\Yandel\Desktop\work\Traceability-agent\fullstack_agent_mvp`

## 1. 项目定位

独立的不良品根因追溯 MVP：质检异常 → ERP 工单/BOM 与设备数据 → 同型号 SOP/案例检索 → 证据检查与有限反思 → 8D 诊断草稿；需要冻结原料批次时先经过人工审批。

主要分为 Python 智能体服务、Java 网关示范、测试与评测三部分。当前没有独立前端页面工程；也不是相邻的通用编码助手 `pi-agent-python`。

## 2. 完整源码与资料树

以下路径均相对上述项目根目录。虚拟环境、缓存、字节码、Maven 依赖缓存及构建产物未展开。

```text
fullstack_agent_mvp/
├── readme.md                         # 项目说明、启动、审批演示及接入边界
├── project_map.md                    # 本目录映射文档
├── implementation_plan.md            # 实施计划
├── ultimate_interview_guide.md        # 项目面试准备资料
├── sources.md                        # 来源与参考记录
├── requirements.txt                  # Python 主依赖范围
├── requirements.lock.txt             # 固定依赖版本快照
├── requirements-integrations.txt     # Redis checkpoint、Milvus、模型检索扩展依赖
├── .gitignore                        # Python 工程忽略规则
│
├── python_service/                   # Python：FastAPI + LangChain + LangGraph
│   ├── __init__.py                   # Python 包标识
│   ├── main.py                       # HTTP 入口、可信身份依赖、应用生命周期
│   ├── runtime.py                    # TraceService：工单隔离、锁、重放、审批恢复
│   ├── agent_graph.py                # TraceState、Graph 节点、条件路由、模型决策
│   ├── tools.py                      # 质检/ERP/设备/检索/冻结工具与 HybridRetriever
│   ├── schemas.py                    # Pydantic：身份、请求、响应、观察、8D 报告
│   ├── reporting.py                  # 从证据构造结构化 8D 报告
│   ├── fixtures.py                   # 本地模拟业务数据、SOP 与案例
│   ├── tests/
│   │   └── test_contract.py          # Graph、工具、审批、权限、重放等契约测试
│   └── evals/
│       ├── __init__.py               # 评测包标识
│       ├── golden_dataset.json       # 黄金评测样本
│       ├── graders.py                # 轨迹裁判、报告证据校验、可选语义裁判
│       └── run_eval.py               # 评测入口、策略对照、指标与结果文件输出
│
├── springboot_gateway_demo/          # Java：独立 Maven 网关示范工程
│   ├── readme.md                     # Java 启动依赖、调用方式和未验证边界
│   ├── pom.xml                       # Maven 构建；显式使用本目录 Java 源文件
│   ├── .gitignore                    # 网关工程忽略规则
│   ├── GatewayApplication.java       # Spring Boot 启动入口
│   ├── GatewayConfiguration.java     # 安全、客户端等基础设施装配
│   ├── Actor.java                    # 从已验证 JWT 映射调用者身份，不是 LLM Agent
│   ├── DefectTraceController.java    # 诊断、审批恢复、工单查询 HTTP 接口
│   ├── TraceWorkflow.java            # 锁、请求幂等、工单状态、审批与报告落库编排
│   ├── PythonAgentWebClient.java     # WebClient 调用 Python JSON/SSE 接口
│   ├── WorkOrderEntity.java          # 工单持久化实体
│   ├── WorkOrderMapper.java          # MyBatis-Plus 工单访问接口
│   ├── schema.sql                    # 新数据库的建表脚本，需显式执行
│   ├── resources/
│   │   └── application.yml           # 网关配置与环境变量占位
│   └── tests/
│       ├── ActorTest.java            # JWT 身份映射测试
│       ├── PythonClientTest.java     # Python 客户端调用契约测试
│       └── WorkflowTest.java         # 工单、审批、重放、失败恢复等工作流测试
│
└── evidence/                         # 已有验证记录；不是运行时代码
    ├── verification.md               # 验证说明
    ├── python-tests.txt              # 已保存的 Python 测试输出
    ├── java-tests.txt                # 已保存的 Java 测试输出
    ├── protected-files-before.json   # 受保护文件的修改前快照记录
    ├── protected-files-verification.json # 受保护文件的核对记录
    ├── mock-baseline/
    │   ├── report.md                 # Mock baseline 策略评测报告
    │   └── trials.json               # 对应逐次运行记录
    └── mock-optimized/
        ├── report.md                 # Mock optimized 策略评测报告
        └── trials.json               # 对应逐次运行记录
```

## 3. 功能 → 文件 → 核心符号

| 要找的功能 | 文件 | 已核对的入口或符号 |
|---|---|---|
| Python 服务启动与 HTTP 路由 | `python_service/main.py` | `create_app`、`app`、`trusted_identity` |
| 发起诊断 / 恢复审批 | `python_service/runtime.py` | `TraceService.diagnose`、`TraceService.resume` |
| 工单级隔离、并发控制、检查点 | `python_service/runtime.py` | `config`、`locked`；`InMemorySaver` / 可选 `RedisSaver` |
| Agent 共享状态与图编排 | `python_service/agent_graph.py` | `TraceState`、`build_graph` |
| 业务工具与混合检索 | `python_service/tools.py` | `query_defect_inspection`、`trace_erp_work_order_bom`、`query_equipment_telemetry`、`retrieve_sop_and_8d_cases`、`freeze_erp_stock_batch`、`HybridRetriever` |
| 报告结构与构造 | `python_service/schemas.py`、`python_service/reporting.py` | `RootCause8DReport`、`build_report` |
| 自动评测 | `python_service/evals/run_eval.py`、`python_service/evals/graders.py` | `run`、`TrajectoryGrader`、`SemanticGrader` |
| Java 对外入口 | `springboot_gateway_demo/DefectTraceController.java` | `diagnose`、`resume`、`find` |
| Java 业务编排与落库 | `springboot_gateway_demo/TraceWorkflow.java` | `diagnose`、`resume`、`withLock`；使用 `WorkOrderMapper` |
| Java → Python 通信 | `springboot_gateway_demo/PythonAgentWebClient.java` | `diagnose`、`resume`、`diagnoseEvents` |

## 4. 已核对的核心调用链

```text
调用方
  → DefectTraceController.java        Java HTTP 入口 / JWT 调用者身份
  → TraceWorkflow.java                锁、工单状态、幂等与持久化编排
  → PythonAgentWebClient.java         HTTP 调用 Python
  → python_service/main.py           FastAPI 路由 / 身份依赖
  → python_service/runtime.py         TraceService / 工单检查点 / 权限与重放
  → python_service/agent_graph.py     LangGraph 图执行
      → python_service/tools.py      工具调用与检索
      → python_service/reporting.py  报告构造
  → TraceResponse                    Python 返回结构化结果
  → TraceWorkflow.java               保存工单结果 / 审批状态
  → 调用方
```

本地 Python 演示可直接从 `main.py` 的 HTTP 接口进入，不必启动 Java 网关。`main.py` 从 `agent_graph.py` 导入的 `TraceService` 是再导出的公共入口；该类实际定义在 `runtime.py`。

Graph 实际注册 9 个节点：`actor`、`tools`、`evaluate`、`reflect`、`approval`、`freeze`、`after_freeze`、`report`、`partial`。读取图结构时从 `build_graph` 的节点与边注册开始，不要把它与 PiAgent 的 4 节点图混淆。

## 5. 推荐源码阅读顺序

1. `readme.md`：先确认要解决的问题、运行模式与边界。
2. `python_service/schemas.py`：理解请求、报告和工具观察的数据契约。
3. `python_service/main.py` → `python_service/runtime.py`：理解请求如何进入工单执行。
4. `python_service/agent_graph.py`：理解状态、节点、反思循环和审批分支。
5. `python_service/tools.py` → `python_service/reporting.py`：理解数据与证据如何进入报告。
6. `python_service/tests/test_contract.py` → `python_service/evals/`：理解正确性验证与效果评测的区别。
7. `springboot_gateway_demo/`：最后阅读身份、数据库、锁及跨服务调用。

## 6. 阅读边界

- `tools.py` 包含模拟工业系统及可选真实检索路径；存在 ERP/机台工具不代表已连接真实工厂系统。
- Graph 使用真实 LangGraph；`mock` 模式的模型决策为本地模拟，不能当成真实 LLM 效果。
- 默认检查点在进程内存中；配置 Redis 后才走 Redis 检查点与锁路径。目录中没有独立的数据库持久化模块。
- `baseline` 是修复行为消融对照，不是历史生产基线；`evidence/` 是已有结果，本次未复跑。
- Java 源文件直接放在 `springboot_gateway_demo/`，这是该工程的实际布局，不应按常见模板虚构 `src/main/java/`。
- SSE 入口目前发送单条最终结果事件，不是逐 token 或逐节点实时流。
