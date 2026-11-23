# 运行与需求验证说明文档

> 本文档教你**如何把项目跑起来，并逐条验证每个功能需求是否真的生效**。
> 每条命令我都实际运行过，预期输出均为真实结果。
>
> 适用版本：已提交到 `main` 的当前代码（含可选 Tavily MCP 搜索）。
> 环境：Windows，项目根目录 `C:\Users\Yandel\Desktop\work\Traceability-agent-python\fullstack_agent_mvp`。

---

## 0. 先搞清一件事：这个项目"跑起来"不等于"接真工厂"

当前是 **mock 教学模式**：

- 数据来自 `python_service/fixtures.py` 里写死的三个合成案例（**不是真 ERP/真 MES**）；
- 模型决策默认是 `mock` 模式（**不调用任何大模型 API**）；
- 唯一可能访问外网的是"可选 Tavily 搜索"，且**必须自己配 Key 才会触发**。

所以默认状态下，**不需要任何外部服务、不需要 API Key、不需要数据库**，就能跑通全部核心流程。这一点面试时要主动说，是加分项。

---

## 1. 环境准备

### 1.1 确认 Python 虚拟环境

```powershell
cd C:\Users\Yandel\Desktop\work\Traceability-agent-python\fullstack_agent_mvp
.venv\Scripts\python.exe --version
```

预期：输出 Python 版本（3.10 或 3.11 均可）。

> 注意：`.venv` 里没有 `pip`（历史原因）。装新依赖请用系统 Python 指向 venv，见 1.3。

### 1.2 确认核心依赖已装

```powershell
.venv\Scripts\python.exe -c "import fastapi, langchain_core, langgraph; print('core ok')"
```

预期：`core ok`

### 1.3（仅当要测 MCP 搜索时）确认可选依赖

```powershell
.venv\Scripts\python.exe -c "import langchain_mcp_adapters, mcp; print('mcp ok')"
```

预期：`mcp ok`（已装）。如果报 `ModuleNotFoundError`，说明可选依赖没装，按 README 装：

```powershell
python -m pip --python .venv\Scripts\python.exe install langchain-mcp-adapters==0.2.2 mcp==1.30.0 -c requirements.lock.txt
```

> 真实 Tavily 搜索还需要本机有 Node.js / npx（`npx.cmd`）。没有 npx 时搜索会降级为 `MISSING_DEPENDENCY` 或 `TIMEOUT`，不会崩溃。

---

## 2. 一键自检：跑测试

这是最快的"项目是否健康"检查，**面试现场也可以当场跑**：

```powershell
cd C:\Users\Yandel\Desktop\work\Traceability-agent-python\fullstack_agent_mvp

# 核心契约测试（20 个）
.venv\Scripts\python.exe -m pytest python_service\tests -q

# MCP 离线夹具测试（18 个，不访问 Tavily 云端）
.venv\Scripts\python.exe -m pytest tests_mcp -q
```

预期：

```
python_service\tests : 20 passed
tests_mcp            : 18 passed
```

> `python_service\tests` 是"逻辑对不对"的契约测试；`tests_mcp` 是"搜索接入对不对"的离线测试。两者都不需要 Key、不联网。

---

## 3. 启动服务

```powershell
cd C:\Users\Yandel\Desktop\work\Traceability-agent-python\fullstack_agent_mvp
$env:AGENT_MODE = "mock"
.venv\Scripts\python.exe -m uvicorn python_service.main:app --host 127.0.0.1 --port 8000
```

启动成功后会看到类似 `Uvicorn running on http://127.0.0.1:8000`。

> **统一约定**：以下所有验证命令都在 **PowerShell** 下执行。
> 如果看到端口占用报错 `[Errno 10048]`，先执行：
> ```powershell
> netstat -ano | findstr :8000   # 找 PID
> taskkill /PID <PID> /F          # 杀掉
> ```

### 验证服务已起（健康检查）

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

预期输出：

```
status     mode     persistence
------     ----     -----------
ok         mock     memory
```

- `mode=mock`：模型决策走本地确定性逻辑，不调 LLM。
- `persistence=memory`：检查点在进程内存，重启即丢（没有配 Redis）。

---

## 4. 需求逐条验证

下面按"需求 → 验证命令 → 预期结果 → 它证明了什么"组织。
所有命令都在**服务已启动**的前提下执行，且均为 PowerShell 语法。

> **中文乱码怎么办**：PowerShell 控制台默认 GBK 码页，显示中文可能乱码。执行
> ```powershell
> [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
> chcp 65001
> ```
> 再重发请求即可。或者把结果落盘到 UTF-8 文件查看：
> ```powershell
> $r = Invoke-RestMethod ...   # 任意请求
> $r | ConvertTo-Json -Depth 10 | Out-File result.json -Encoding utf8
> notepad result.json
> ```

### 需求 1：质检异常能触发一条完整的取证闭环

**验证命令**（不需要冻结，最快看到完整报告）：

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/trace/diagnose `
  -Method Post `
  -ContentType "application/json" `
  -Headers @{
    "X-Tenant-Id" = "demo"
    "X-User-Id"   = "engineer-1"
    "X-User-Role" = "quality_engineer"
    "X-Trace-Id"  = "demo-trace-1"
  } `
  -Body '{"work_order_id":"WO-DEMO-001","batch_no":"FG-20261001-001","request_freeze":false}'

# 只看关键字段
"状态: $($r.status)"
"工具数: $($r.trajectory.Count)"
$r.trajectory | ForEach-Object { "$($_.sequence). $($_.tool) -> $($_.outcome)" }
"根因: $($r.report.d4_root_cause)"
```

**预期结果**：
- `状态: COMPLETED`
- `工具数: 4`，且 4 条工具顺序固定为：
  1. `query_defect_inspection`（质检单）
  2. `trace_erp_work_order_bom`（ERP 物料）
  3. `query_equipment_telemetry`（机台遥测）
  4. `retrieve_sop_and_8d_cases`（SOP 检索）
- 根因包含三项超差：含水率、温度、压力

**它证明了什么**：`REQUIRED_TOOLS` 锁死的"必查 4 步取证顺序"真实生效，少一步都不会出报告。

---

### 需求 2：根因结论是代码用 SOP 限值算出来的（防幻觉核心）

**验证方式**：改数据，看结论跟着变。

1. 打开 `python_service/fixtures.py`，找到 `FG-20261001-001`，把：
   ```python
   'temperature_c': 275.0, 'pressure_mpa': 52.0, ...
   ```
   改成（都在 SOP 限值内）：
   ```python
   'temperature_c': 260.0, 'pressure_mpa': 70.0, ...
   ```
2. **重启服务**（fixtures 是启动时加载的），重新执行需求 1 的命令。
3. 观察：
   - `report.factors.Machine.status` 从 `ABNORMAL` 变成 `NORMAL`
   - `report.d4_root_cause` 里温度和压力两条超差**消失**，只剩含水率一条
4. **改回原值，再重启**。

**它证明了什么**：报告的每个"异常"都不是模型猜的，是 `reporting.py` 里
`not limits[field][0] <= value <= limits[field][1]` 这段代码逐项比出来的。

---

### 需求 3：批次号格式校验（拦截非法入参）

**验证命令**（传一个格式错误的批次号）：

```powershell
try {
  Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/trace/diagnose `
    -Method Post -ContentType "application/json" `
    -Headers @{
      "X-Tenant-Id" = "demo"
      "X-User-Id"   = "engineer-1"
      "X-User-Role" = "quality_engineer"
      "X-Trace-Id"  = "demo-trace-1"
    } `
    -Body '{"work_order_id":"WO-BAD","batch_no":"ABC123","request_freeze":false}'
} catch {
  "HTTP $([int]$_.Exception.Response.StatusCode) - $($_.ErrorDetails.Message)"
}
```

**预期结果**：输出 `HTTP 422 - ...`（Pydantic 校验失败），请求进不了业务逻辑。

> PowerShell 里 HTTP 4xx/5xx 会抛异常，所以用 `try/catch` 包住才能看到状态码和错误体。

**它证明了什么**：`DiagnoseRequest` 的字段约束在 HTTP 层就拦住了非法入参，不会让坏数据流进图。

---

### 需求 4：查不存在的批次 → 优雅降级而非崩溃

**验证命令**：

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/trace/diagnose `
  -Method Post -ContentType "application/json" `
  -Headers @{
    "X-Tenant-Id" = "demo"
    "X-User-Id"   = "engineer-1"
    "X-User-Role" = "quality_engineer"
    "X-Trace-Id"  = "demo-trace-1"
  } `
  -Body '{"work_order_id":"WO-MISS","batch_no":"FG-20261001-999","request_freeze":false}'

"状态: $($r.status)"
"停止原因: $($r.stop_reason)"
```

**预期结果**：`状态: PARTIAL`，`停止原因` 包含 `MISSING_EVIDENCE`（而非服务器 500 崩溃）。

**它证明了什么**：证据不全会走 `partial` 降级分支，不会硬编一个根因出来。

---

### 需求 5：冻结原料批次必须先人工审批（人机协同）

**第 1 步**：发起需要冻结的诊断：

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/trace/diagnose `
  -Method Post -ContentType "application/json" `
  -Headers @{
    "X-Tenant-Id" = "demo"
    "X-User-Id"   = "engineer-1"
    "X-User-Role" = "quality_engineer"
    "X-Trace-Id"  = "demo-trace-2"
  } `
  -Body '{"work_order_id":"WO-FREEZE-001","batch_no":"FG-20261001-001","request_freeze":true}'

"状态: $($r.status)"
"审批ID: $($r.approval_id)"
$approvalId = $r.approval_id   # 记下这个值，下一步用
```

**预期结果**：
- `状态: WAITING_APPROVAL`
- `审批ID: 一段 UUID`

**它证明了什么**：`request_freeze=true` 时图走到 `approval` 节点就 `interrupt()` 挂起，不会擅自冻结。

**第 2 步**：用 supervisor 身份批准（复用上一步的 `$approvalId`）：

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/trace/resume `
  -Method Post -ContentType "application/json" `
  -Headers @{
    "X-Tenant-Id" = "demo"
    "X-User-Id"   = "supervisor-1"
    "X-User-Role" = "supervisor"
    "X-Trace-Id"  = "demo-trace-2"
  } `
  -Body '{"work_order_id":"WO-FREEZE-001","approval_id":"第一步返回的approval_id","approved":true}'

"状态: $($r2.status)"
"围堵措施: $($r2.report.d3_containment)"
```

**预期结果**：
- `状态: COMPLETED`
- `围堵措施` 显示"已冻结问题原料并生成 CAPA"

**它证明了什么**：批准后图从挂起点恢复，执行 `freeze_erp_stock_batch` 写操作，然后出报告。

> 注意：第 2 步的 Body 用了 `ConvertTo-Json`，因为 `approved` 是布尔值，手写 JSON 字符串容易漏引号。

---

### 需求 6：审批决定不可变（幂等）

**验证命令**：对上面同一个 `WO-FREEZE-001`，再次提交 `resume`，但把 `approved` 改成 `false`：

```powershell
try {
  Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/trace/resume `
    -Method Post -ContentType "application/json" `
    -Headers @{
      "X-Tenant-Id" = "demo"
      "X-User-Id"   = "supervisor-1"
      "X-User-Role" = "supervisor"
      "X-Trace-Id"  = "demo-trace-2"
    } `
    -Body (@{ work_order_id="WO-FREEZE-001"; approval_id=$approvalId; approved=$false } | ConvertTo-Json)
} catch {
  "HTTP $([int]$_.Exception.Response.StatusCode) - $($_.ErrorDetails.Message)"
}
```

**预期结果**：输出 `HTTP 409 - ...Approval decision is immutable...`。

**它证明了什么**：审批决定一旦落库就不可翻转，防止"先批后反悔"造成的数据不一致。

---

### 需求 7：非本人工单 / 非 supervisor 越权被拒（RBAC）

**验证命令 A**：用 `quality_engineer` 身份去 resume（resume 只允许 supervisor）：

```powershell
try {
  Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/trace/resume `
    -Method Post -ContentType "application/json" `
    -Headers @{
      "X-Tenant-Id" = "demo"
      "X-User-Id"   = "engineer-1"
      "X-User-Role" = "quality_engineer"
      "X-Trace-Id"  = "demo-trace-2"
    } `
    -Body (@{ work_order_id="WO-FREEZE-001"; approval_id="x"; approved=$true } | ConvertTo-Json)
} catch {
  "HTTP $([int]$_.Exception.Response.StatusCode) - $($_.ErrorDetails.Message)"
}
```

**预期结果**：输出 `HTTP 403 - ...Only supervisor can approve...`。

**验证命令 B**：用另一个普通用户查别人的工单：

```powershell
try {
  Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/trace/diagnose `
    -Method Post -ContentType "application/json" `
    -Headers @{
      "X-Tenant-Id" = "demo"
      "X-User-Id"   = "other-engineer"
      "X-User-Role" = "quality_engineer"
      "X-Trace-Id"  = "demo-trace-1"
    } `
    -Body '{"work_order_id":"WO-DEMO-001","batch_no":"FG-20261001-001","request_freeze":false}'
} catch {
  "HTTP $([int]$_.Exception.Response.StatusCode) - $($_.ErrorDetails.Message)"
}
```

**预期结果**：输出 `HTTP 403 - ...Work order belongs to another user...`（因为 `WO-DEMO-001` 之前是 `engineer-1` 创建的）。

**它证明了什么**：`runtime.py` 的归属校验 + 角色校验在起作用，权限判断不交给模型。

---

### 需求 8（可选）：Tavily MCP 搜索接入

**8.1 无 Key 时：必须降级不崩溃**

```powershell
$env:TAVILY_API_KEY = ""
.venv\Scripts\python.exe scripts\verify_tavily.py
```

预期输出：

```
SKIPPED: TAVILY_API_KEY is not configured; no Tavily request was made.
```

退出码 `77`（跳过），**不是通过**。这证明：不配 Key，服务不启动子进程、不联网、不崩。

**8.2 配 Key 后：真实联网验收**

1. 去 [tavily.com](https://tavily.com) 注册，拿一个 API Key（有免费额度）。
2. 在**你的终端**（不是写进代码）设置环境变量：

   ```powershell
   # PowerShell（只对当前窗口生效）
   $env:TAVILY_API_KEY = "tvly-你的key"
   ```

   > 不要把 Key 写进源码、commit、或贴到聊天里。

3. 在同一个终端里运行：

   ```powershell
   .venv\Scripts\python.exe scripts\verify_tavily.py
   ```

预期输出（真实调用一次 Tavily 搜索）：

```
PASS: real Tavily MCP result persisted separately from mandatory evidence.
```

退出码 `0`。同时会打印出 `query / outcome / reason / urls` 和 `evidence_tools`（应仍是 4 个必查工具）。

**它证明了什么**：
- 搜索经 `langchain-mcp-adapters` + MCP SDK stdio 客户端，真实拉起 `npx tavily-mcp` 子进程；
- 搜索结果是**外部背景资料**，存进 `web_references`，**不混入 `evidence` 必查证据**；
- 四个必查工具一个不少（`evidence_tools` 仍是那 4 个）。

**8.3 搜索失败的降级路径**（面试可讲，不必都测）

| 场景 | 返回的 `reason` |
|---|---|
| 没配 Key | `NOT_CONFIGURED` |
| 缺 MCP 依赖 | `MISSING_DEPENDENCY` |
| 没有 Node/npx | `MCP_UNAVAILABLE`（或 `MISSING_DEPENDENCY`） |
| 45 秒超时 | `TIMEOUT` |
| 每诊断线程重复搜索 | `SEARCH_LIMIT_REACHED`（至多一次） |

---

## 5. 关停服务

前台运行时按 `Ctrl+C` 即可。如果之前是后台起的，用：

```powershell
# 找到占用 8000 端口的进程
netstat -ano | findstr :8000
# 记下 PID，然后
taskkill /PID <PID> /F
```

---

## 6. 面试前 10 分钟速检清单

按顺序跑一遍，全绿即可上场：

```powershell
cd C:\Users\Yandel\Desktop\work\Traceability-agent-python\fullstack_agent_mvp

# 1. 测试
.venv\Scripts\python.exe -m pytest python_service\tests tests_mcp -q
# → 38 passed

# 2. 启动
$env:AGENT_MODE = "mock"
.venv\Scripts\python.exe -m uvicorn python_service.main:app --host 127.0.0.1 --port 8000

# 3. 健康检查（另开一个终端）
Invoke-RestMethod http://127.0.0.1:8000/health
# → status=ok, mode=mock, persistence=memory

# 4. 一次完整诊断（需求 1 的命令）
# → status=COMPLETED，trajectory 有 4 条，d4 有三项超差
```

---

## 7. 需求 ↔ 代码位置速查（面试被追问时快速定位）

| 需求 | 代码位置 |
|---|---|
| 必查 4 步取证顺序 | `python_service/tools.py` 末尾 `READ_TOOLS` / `REQUIRED_TOOLS` |
| 入参强校验 | `python_service/tools.py` 的 `BatchArgs` / `TelemetryArgs` / `SopArgs` |
| 防幻觉（批次/型号/时间窗比对） | `python_service/agent_graph.py` 的 `evidence_error` |
| 熔断（最多 3 次反思、12 轮 actor） | `python_service/agent_graph.py` 的 `MAX_RETRIES` / `MAX_ACTOR_TURNS` |
| 写操作物理隔离 + 审批挂起 | `python_service/agent_graph.py` 的 `approval` / `freeze` 节点 |
| 审批决定不可变 + 幂等 | `python_service/runtime.py` 的 `resume` |
| 报告数值防伪造 | `python_service/evals/graders.py` 的 `validate_report` |
| Tavily MCP 搜索 | `python_service/web_search.py` |
| 三个 mock 案例数据 | `python_service/fixtures.py` |
