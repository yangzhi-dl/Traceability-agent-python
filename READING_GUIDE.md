# 新手阅读大纲：不良品根因追溯智能体（fullstack_agent_mvp）

> 这份文档是给"第一次接触这个项目"的人准备的阅读路线图。
> 目标不是让你背代码，而是让你在动手读每一份文件之前，先知道：
> 它为什么存在、它解决了什么问题、读的时候该盯住哪几个符号、读完该能回答哪几个问题。
>
> 阅读顺序按依赖关系排列，后读的文件会用到前面文件里定义的概念。

---

## 0. 先建立三个心智模型（读完这节再碰代码）

在你打开任何 .py 文件之前，先记住这个项目不是"聊天机器人"，而是一条
**受约束的取证流水线**。它只有三件事：

### 心智模型一：取证顺序是"死"的

一条不良品追溯，必须按这个顺序走，少一步都不行：

```
质检单（起点，发现不良）
  → 物料维度（ERP 工单 → BOM → 原料批次 → 含水率）
  → 机台维度（设备遥测，时间窗必须等于质检单的生产时间窗）
  → 方法维度（同型号 SOP 检索）
  → 对照 SOP 限值，用代码判定哪些参数超差
```

顺序和"必查项"不是模型自由发挥的，是写死在代码里的（`REQUIRED_TOOLS`）。

### 心智模型二：防幻觉靠"代码比对"，不靠"模型自觉"

大模型可能会编造单据号、篡改数值、跨型号套用标准。这个项目的答案从来不是
"在 prompt 里叮嘱它别乱来"，而是**用 Python 做mjki9888888888确定性校验**：

- 工具返回的批次号 != 请求的批次号 → 直接判 `BATCH_MISMATCH`
- 工具返回的型号 != 质检单的型号 → 直接判 `MODEL_MISMATCH`
- 报告的数值、单位、来源对不上证据 → 直接判 `unsupported number/unit/source`

你读代码时，凡是看到 `evidence_error`、`validate_report`、`limits` 这些词，
就是这套防幻觉机制在起作用。

### 心智模型三：高风险写操作被"物理隔离"

全项目只有一个写操作：`freeze_erp_stock_batch`（冻结原料批次）。

它**不在**普通工具列表里，而是被单独挂在审批节点之后。大模型在推理阶段
**根本调用不到它**——这是图拓扑级别的权限隔离，比任何"禁止写操作"的提示词
都可靠。你读 `agent_graph.py` 时要专门体会这一点。 

---

## 1. 阅读路线图（一张图看懂依赖关系）

```
第 0 步   README.md / PROJECT_MAP.md     建立全局地图，知道有哪些文件
             │
第 1 步   schemas.py                     数据契约：所有实体长什么样
             │
第 2 步   fixtures.py                    数据从哪来：合成教学数据
             │
第 3 步   tools.py                       五个工具 + 混合检索器
             │
第 4 步   agent_graph.py                 ★ 核心：状态机 + 9 节点 + 条件边
             │
第 5 步   reporting.py + graders.py      报告怎么算出来、怎么被验证
             │
第 6 步   main.py + runtime.py           服务怎么进门、怎么锁、怎么恢复
             │
第 7 步   tests/test_contract.py + evals/   怎么证明"它对"
             │
第 8 步   springboot_gateway_demo/       进阶：Java 网关示范（可后置）
```

**建议节奏**：第 0~2 步一次读完（很薄），第 3~4 步各花一整块时间，
第 5~6 步连起来读，第 7 步结合跑测试一起看。

---

## 2. 分步阅读指南

### 第 0 步：README.md + PROJECT_MAP.md（约 15 分钟）

**目的**：建立地图，不用细读。

**盯住**：
- `PROJECT_MAP.md` 第 3 节「功能 → 文件 → 核心符号」对照表
- `PROJECT_MAP.md` 第 5 节「推荐源码阅读顺序」
- `README.md` 里的启动方式和"未验证边界"

**读完该能回答**：
1. 这个项目分哪三大部分？（Python 智能体 / Java 网关 / 测试与评测）
2. "9 个节点"分别是哪 9 个名字？

---

### 第 1 步：schemas.py（数据契约层）

**目的**：理解"强类型契约"——项目里不允许用裸 dict 传核心实体。

**盯住**：
- `StrictModel`：`extra='forbid'` 意味着多传一个字段都会报错
- `Role` / `Status` / `Outcome` / `Factor` 这些 `Literal` 枚举
- `Identity`：`tenant_id` 有正则约束 `^[A-Za-z0-9_-]{1,64}$`
- `ToolObservation`：每一个工具结果都被包装成 `outcome + source + evidence_id + data`
- `RootCause8DReport`：`report_status` 被锁死为 `DRAFT_PENDING_VALIDATION`（草稿，不是结论）

**关键洞察**：
`evidence_id` 是防伪造的地基。它的格式是 `{source}:{key}`，例如
`MES:FG-20261001-001`。后面所有"报告引用的证据必须真实存在"的校验，
都是在比对这一串 ID 是否来自真实工具返回。

**读完该能回答**：
1. 为什么 `report_status` 只有一个允许值？
2. `evidence_id` 在整个防幻觉体系里扮演什么角色？

---

### 第 2 步：fixtures.py（数据从哪来）

**目的**：明白"这不是连了真工厂"，数据是写死的合成教学数据。

**盯住**：
- `CASES`：三个不良案例，各自对应不同型号（A-HOUSING / B-HOUSING / PCBA-C）
- `SOPS`：每个型号一份 SOP（含 `limits` 限值）+ 一份历史 8D 案例
- `case()`：把 CASE 补全成完整记录（加上 `production_start/end`、`erp_work_order` 等）

**关键洞察**：
三个案例是精心设计的，对应三种不同的"根因组合"：

| 批次 | 型号 | 故意埋的异常 |
|---|---|---|
| FG-20261001-001 | A-HOUSING | 含水率超 + 温度超 + 压力低（多因子复合） |
| FG-20261001-002 | B-HOUSING | 温度超，但含水率在标准内（单因子） |
| FG-20261001-003 | PCBA-C | 回流温度低，无压力/转速参数（字段缺失场景） |

**读完该能回答**：

1. 为什么说这三个案例是"教学用心"的设计？
2. `limits` 里的数值区间，最终被谁用来判定超差？

---

### 第 3 步：tools.py（五个工具 + 混合检索）

**目的**：理解工具怎么被"类型化"、怎么被"只读/写"区分。

**盯住**：
- `READ_TOOLS` vs `freeze_erp_stock_batch`（后者不在 READ_TOOLS 里！）
- `BatchArgs` / `TelemetryArgs` / `SopArgs` / `FreezeArgs` 的入参 schema
- `query_equipment_telemetry` 里的时间窗校验（对不上就返回 `EMPTY`）
- `freeze_erp_stock_batch` 的 `state: Annotated[dict, InjectedState]`（身份系统注入）
- `HybridRetriever.search`：型号过滤 → BM25+向量 → RRF 融合 → 重排序

**关键洞察**：
1. **时间窗校验是硬编码的**：遥测工具要求 `start_time/end_time` 必须精确等于
   MES 质检单的 `production_start/end`，否则返回 `EMPTY`。这对应架构约束里的
   "单据时空先后一致性"的雏形。
2. **写工具的入参不是模型给的**：`FreezeArgs` 里的 `state` 是 `InjectedState`，
   由系统从图状态注入，模型无法伪造身份和审批决定。

**读完该能回答**：
1. `freeze_erp_stock_batch` 为什么不能放进 `READ_TOOLS`？
2. 遥测工具什么时候返回 `EMPTY`？`EMPTY` 和 `NOT_FOUND` 区别在哪？

---

### 第 4 步：agent_graph.py（★ 核心：状态机）

**目的**：这是整个项目的"心脏"，值得反复读。

**盯住**：
- `TraceState`：所有图状态字段（`messages` / `evidence` / `retries` / `route` ...）
- `MAX_RETRIES = 3` / `MAX_ACTOR_TURNS = 12`（熔断预算）
- 9 个节点的注册（`graph.add_node`）
- 条件边的路由表（`graph.add_conditional_edges`）
- `evaluate` 节点的 `evidence_error`（防幻觉闸门）
- `approval` 节点的 `interrupt()`（人机协同挂起点）
- `reflect` → `actor` 的回退环路（自我纠错，但有熔断）

**关键洞察（读的时候逐条对）**：

1. **`evaluate` 是"闸门"不是"决策器"**：它只做确定性比对，决定
   `route` 走哪。失败就 `reflect`，证据齐全才 `approval`/`report`。

2. **环路有熔断**：`reflect` 把 `retries + 1` 写回状态，超过 `MAX_RETRIES`
   就强制走 `partial`（降级），不会死循环。

3. **`interrupt()` 是挂起而非结束**：图在 `approval` 节点挂起，状态存检查点。
   恢复时 `Command(resume=decision)` 从挂起点继续，且审批决定绑定校验
   （approval_id + role + approved 三者必须匹配）。

4. **报告生成后还有一道闸**：`report` 节点里调用了 `validate_report`，
   报告造假（引用了不存在的证据 ID、数值对不上）会被打回 `PARTIAL`。

**读完该能回答**：
1. 画一遍 9 节点的状态流转图（不看文档默画）。
2. 如果 actor 在证据不全时就想出报告，`evaluate` 会把它路由到哪？
3. 为什么说"写工具被物理隔离"？隔离的拓扑依据是什么？

---

### 第 5 步：reporting.py + graders.py（报告与验证）

**目的**：理解"报告的每一个异常结论都是代码算出来的"。

**盯住**：
- `build_report`：纯函数，输入 state，输出 `RootCause8DReport`
- 超差判定：`if field in limits and not limits[field][0] <= value <= limits[field][1]`
- `validate_report`：报告落库前的"运行时闸门"，逐项核对证据 ID、数值、单位、型号
- `TrajectoryGrader`：审计工具派发顺序和预算

**关键洞察**：
`build_report` 里那句
`d4_root_cause = '；'.join(abnormalities) + '。以上支持相关性归因假设，需对照实验确认因果。'`
体现了项目最克制的立场：**数据只能证明"相关"，不能假装"因果"**。

`validate_report` 里最值得看的是这段：
```python
number = r'(?<![A-Za-z0-9])\d+(?:\.\d+)?'
allowed = {float(n) for n in re.findall(number, json.dumps(found, ensure_ascii=False))}
```
它把报告正文里出现的**每一个数字**都拿去和证据里的数字比对，
对不上就是"报告在编造数值"。

**读完该能回答**：
1. 报告里 `Machine=ABNORMAL` 这个结论，是哪一行代码算出来的？
2. 如果 LLM 在 D4 里写了一个证据里没有的数值，`validate_report` 怎么拦？

---

### 第 6 步：main.py + runtime.py（服务门面与恢复）

**目的**：理解请求怎么进门、工单怎么锁、崩溃后怎么恢复。

**盯住**：
- `trusted_identity`：把 HTTP 头解析成 `Identity`（Pydantic 校验）
- `TraceService.diagnose`：工单级锁 + 幂等 + 检查点重放
- `TraceService.resume`：审批决定的"不可变"校验
- `config()`：`thread_id = f'{tenant_id}:{work_order_id}'`（工单隔离的 key）
- `response()`：怎么判断"是挂起等待审批"还是"已经跑完"

**关键洞察**：
1. **幂等**：同一个工单重复 `diagnose`，如果参数一致就返回已有结果，
   不会重跑一遍。
2. **审批不可变**：`resume` 里如果上一次已经批准，这次传 `approved=false`
   会直接 409（`Approval decision is immutable`）。
3. **崩溃恢复**：`resume` 里若发现"审批已存在但图还没跑完"（`snapshot.next`），
   会 `invoke(None, config)` 把挂起的执行继续跑完——这是检查点机制的价值。

**读完该能回答**：
1. `thread_id` 是怎么构成的？为什么它天然实现了租户间工单隔离？
2. 同一审批请求提交两次，第二次会发生什么？

---

### 第 7 步：tests/test_contract.py + evals/（怎么证明"它对"）

**目的**：理解"测试"和"评测"是两回事。

**盯住**：
- `test_contract.py`：契约测试（确定性，跑得快，证明逻辑正确）
- `evals/graders.py`：轨迹裁判 + 语义裁判
- `evals/run_eval.py`：评测入口，策略对照（baseline vs optimized）

**关键洞察**：
- **测试**回答"逻辑对不对"（幂等、权限、重放、审批绑定）。
- **评测**回答"效果好不好"（报告是否忠实、是否完备）。
- 评测里 `TrajectoryGrader` 是纯确定性的（数工具、查顺序、查预算），
  `SemanticGrader` 才可能调 LLM，且 LLM 失败会被记为失败，绝不降级冒充成功。

**读完该能回答**：
1. "契约测试"和"评测"各自守护什么？
2. 为什么语义裁判失败时返回 `score=0` 而不是跳过？

---

### 第 8 步（进阶）：springboot_gateway_demo/（Java 网关示范）

**目的**：理解"如果这是个真实生产系统，Java 层补了什么"。

**盯住**：
- `DefectTraceController.java`：对外 HTTP 接口（diagnose / resume / find）
- `TraceWorkflow.java`：锁（Redisson）、CAS 版本号、审批落库、幂等重放
- `WorkOrderEntity.java`：MySQL 是唯一权威数据源，Redis 只做锁/缓存/检查点

**关键洞察**：
Java 层和 Python 层做了**同一件事的两道防线**：Python 用进程内锁 + 检查点，
Java 用 Redisson 分布式锁 + MySQL 版本号 CAS。读的时候对照着看，
能加深对"并发 + 幂等"的理解。

**读完该能回答**：
1. Java 网关的锁和 Python 服务的锁，各自的 key 前缀是什么？为什么不同？
2. `TraceWorkflow.cas()` 里那个"版本号比对"防的是什么？

---

## 3. 动手验证清单（边读边跑）

### 启动服务（mock 模式，不依赖任何外部 API）

```bash
# 在项目根目录 fullstack_agent_mvp 下
.venv/Scripts/python.exe -m uvicorn python_service.main:app --host 127.0.0.1 --port 8000
```

验证健康检查：

```bash
curl http://127.0.0.1:8000/health
# 期望：{"status":"ok","mode":"mock","persistence":"memory"}
```

### 发起一次诊断（request_freeze=false，走 report 分支，最快看到报告）

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/trace/diagnose \
  -H 'Content-Type: application/json' \
  -H 'X-Tenant-Id: demo' \
  -H 'X-User-Id: engineer-1' \
  -H 'X-User-Role: quality_engineer' \
  -H 'X-Trace-Id: demo-trace-1' \
  -d '{"work_order_id":"WO-DEMO-001","batch_no":"FG-20261001-001","request_freeze":false}'
```

观察 `trajectory` 里 4 个工具的顺序，和 `report` 里 `d4_root_cause` 的超差结论。

### 发起一次需要审批的请求（request_freeze=true）

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/trace/diagnose \
  -H 'Content-Type: application/json' \
  -H 'X-Tenant-Id: demo' -H 'X-User-Id: engineer-1' \
  -H 'X-User-Role: quality_engineer' -H 'X-Trace-Id: demo-trace-1' \
  -d '{"work_order_id":"WO-DEMO-002","batch_no":"FG-20261001-001","request_freeze":true}'
```

返回的 `status` 会是 `WAITING_APPROVAL`，并带一个 `approval_id`。

### 用 supervisor 身份批准（替换成上一步拿到的 approval_id）

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/trace/resume \
  -H 'Content-Type: application/json' \
  -H 'X-Tenant-Id: demo' -H 'X-User-Id: supervisor-1' \
  -H 'X-User-Role: supervisor' -H 'X-Trace-Id: demo-trace-1' \
  -d '{"work_order_id":"WO-DEMO-002","approval_id":"<上一步的approval_id>","approved":true}'
```

最终 `status` 会是 `COMPLETED`。

### 跑测试

```bash
.venv/Scripts/python.exe -m pytest python_service/tests -q
# 期望：20 passed
```

### 建议的实验（强烈推荐）

改 `python_service/fixtures.py` 里 `FG-20261001-001` 的 `temperature_c`
从 `275.0` 改成 `260.0`（在 SOP 限值 250~270 之内），重新跑诊断，
观察报告里 `Machine` 因子从 `ABNORMAL` 变成 `NORMAL`，
`d4_root_cause` 里温度那条超差记录消失。

这个实验会让你直观理解：**报告的每个"异常"都是代码用 SOP 限值算出来的，
不是模型猜的**。做完记得改回来。

---

## 4. 关键术语速查表

| 术语 | 含义 | 出现位置 |
|---|---|---|
| DocType | ERPNext 的单据类型（质检单、工单等） | CLAUDE.md / schemas |
| evidence_id | 证据签名，格式 `{source}:{key}` | tools.py / schemas |
| ToolObservation | 每个工具返回结果的统一包装 | schemas.py |
| REQUIRED_TOOLS | 必查的 4 个读工具 | tools.py |
| TraceState | LangGraph 图状态（TypedDict） | agent_graph.py |
| MAX_RETRIES / MAX_ACTOR_TURNS | 自我纠错和 actor 的熔断预算 | agent_graph.py |
| interrupt / Command(resume=...) | LangGraph 人机协同挂起与恢复 | agent_graph.py / runtime.py |
| CAS | Compare-And-Swap，版本号乐观锁 | TraceWorkflow.java |
| RRF | Reciprocal Rank Fusion，多路召回融合 | tools.py |
| 4M1E | Man/Machine/Material/Method/Environment | reporting.py |
| 8D | 八步问题解决法（D1~D8） | reporting.py / schemas.py |

---

## 5. 新手常见困惑（FAQ）

**Q1：我在代码里找不到 `docstatus == 1` 的校验，是不是文档骗我？**

不是。CLAUDE.md 里描述的 `docstatus` 铁律是**目标架构约束**（对接真实 ERPNext
时的蓝图）。当前 MVP 是 mock 教学版，数据在 `fixtures.py` 里，没有真实单据状态。
它的"防伪造"是通过 `evidence_id` 比对、`BATCH_MISMATCH`/`MODEL_MISMATCH` 校验、
`validate_report` 数值核对来实现的——这是同一思想在 mock 层的落地形态。

**Q2：`mock` 模式和 `llm` 模式有什么区别？**

`mock` 模式下 actor 不调任何 LLM，由 `mock_actor()` 按"缺哪个证据就调哪个工具"
的确定性逻辑决策。`llm` 模式才真正调 `ChatOpenAI`。两种模式共用同一套
图、工具、检查点、审批机制——所以 mock 也能完整验证流程。

**Q3：`EMPTY` 和 `NOT_FOUND` 有什么不一样？**

- `NOT_FOUND`：查不到这个批次（可能批次号写错了）。
- `EMPTY`：批次存在，但这次查询没取到有效证据（例如遥测时间窗对不上）。

两者在 `evidence_error` 里都会被当作失败（`outcome != 'FOUND'`），
因为"空结果"意味着证据缺口，必须回头补齐。

**Q4：为什么报告永远标记为 `DRAFT_PENDING_VALIDATION`？**

因为诊断只能给出"相关性归因假设"，CAPA 是否有效、根因是否坐实，
必须靠后续现场验证。把草稿伪装成结论，正是这个项目要防范的"过度自信"。

**Q5：我该从哪个文件开始写代码练习？**

建议从 `reporting.py` 的 `build_report` 或 `tools.py` 的某个工具入手——
它们是最独立的纯函数/纯工具，改起来风险小，容易验证。

---

## 6. 一句话总结

> 这个项目教你的不是"怎么调 LLM"，而是"**当 LLM 被允许在工业场景里行动时，
> 如何用确定性的代码，把它关进 ERP 单据和批次血缘的笼子里**"。
>
> 带着这句话去读代码，你会更容易理解每一处设计为什么长这样。
