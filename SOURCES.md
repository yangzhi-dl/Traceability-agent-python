# 来源、复刻边界与旧业务映射

核对日期：2026-10-31。所有实现均位于当前新目录；参考源码只读使用。此工程是机制复刻和独立示范，不是已部署的旧系统迁移，也没有把三个开源项目原样嵌入运行时。

## 只读提取的旧代码

| 仓库相对路径 | 观察到的事实 | 新工程映射 |
|---|---|---|
| `src/main/java/com/yandel/traceabilityagent/business/traceability/infrastructure/agent/TraceabilityToolProvider.java` | 批次、物料、工单、质量记录；标识 batchNo/workOrderNo/materialCode/equipmentId；只读工具集合 | `DiagnoseRequest`、五工具参数、型号与批次绑定 |
| 同目录 `TraceabilityReadTools.java` | 摘要、谱系、证据；工具上下文恢复租户身份；观察包含状态、source、facts、evidenceIds、质量、retryable | `Identity`、`ToolObservation`、`ToolTrace`；租户隔离与结构化证据 |
| `src/main/java/com/yandel/traceabilityagent/business/batch/infrastructure/persistence/entity/QualityInspectionEntity.java` | tenantId/plantId/batchId/itemId/processExecutionId、模板版本、inspection/result、时间、数据质量、乐观锁版本 | 工单归属、MES 生产窗口、MySQL 工单版本、SOP 版本引用 |
| `src/main/java/com/yandel/traceabilityagent/business/analysis/application/agent/RootCauseAgentOutput.java` | 候选原因 dimension/uncertainty/recommendedActions/evidenceRefs；证据引用 snapshotEvidenceId/stance/explanation | 五维诊断、证据 ID、行动与不确定性、D6/D8 保留待验证 |

旧代码读取范围没有证明其已经接通 ERPNext/MES 写操作。本工程的工艺数值、供应商、质检异常、库存冻结结果均为新建合成 Mock，不能当作原项目线上数据。

仓库规则引用的 `docs/harness-agent-protocol-consistency-plan.md` 在本次指定路径不存在。用户本次明确授权在隔离目录使用 LangGraph，因此没有修改原 AgentScope 运行时。

## 开源机制的准确对应

| 来源 | 本次阅读位置 | 本工程采用的机制 | 差异 |
|---|---|---|---|
| [Reflexion 官方仓库](https://github.com/noahshinn/reflexion) 与 [论文](https://arxiv.org/abs/2303.11366) | 官方项目说明、情景记忆反馈范式 | `actor -> tools -> evaluate -> reflect -> actor`；自然语言反馈保存在 episodic_memory | 以 LangGraph 重写；不训练权重；每个工单最多三次反思；不是整套原始 benchmark 移植 |
| [OpenJudge](https://github.com/agentscope-ai/OpenJudge) | `ref_repos/OpenJudge/openjudge/graders/base_grader.py`、`graders/common/correctness.py` | 可插拔裁判、rubric、证据依据与 score；`SemanticGrader` 使用 Pydantic structured output | 原 BaseGrader 包含异步 `_aevaluate`、策略与资源调度；本地简化为同步 `grade`。原 correctness 为 1–5 分，本工程按需求用 0/1 |
| [Claw-Eval](https://github.com/claw-eval/claw-eval) | `ref_repos/claw-eval/src/claw_eval/graders/base.py`、`models/scoring.py`、README | 实际工具调度轨迹、成功/失败观察、恢复审计、多次独立试验 | 定义制造场景偏序和权限断言；未复刻多模态沙箱、全部任务或 leaderboard |

**统计差异：** 本地 claw-eval README 将 Pass^3 描述为三次全过；但 `models/scoring.py:compute_pass_hat_k` 实现 `(c/n)^k`。本工程主指标按用户要求计算 `mean(all(trial_successes))`；附加输出 `mean((c/n)^3)` 供对照。二者不是同一个估计量。`pass@k` 则表示 k 次中至少一次成功，不能替代稳定性要求。

`reason` 保存字段、来源和扣分规则说明，不要求或保存隐含思维链。离线规则打分不是 OpenJudge 真实 LLM 裁判结果。

## 运行时 API 依据

- [LangGraph interrupt 官方说明](https://docs.langchain.com/oss/python/langgraph/interrupts)：checkpoint + 相同 thread_id + `Command(resume=...)`；恢复会重执行被挂起节点，所以副作用位于后续 ToolNode。
- [LangGraph Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)：StateGraph、条件边与状态 reducer。
- [ToolNode 官方 API](https://reference.langchain.com/python/langgraph.prebuilt/tool_node/ToolNode)：类型化工具、注入状态、异常处理；本机安装版本实际运行了这些扩展点。
- [LangGraph Redis 官方实现](https://github.com/redis-developer/langgraph-redis)：`RedisSaver.from_conn_string(...).setup()`；需要 JSON 和 Search 能力。普通无模块 Redis 7 不满足要求，Redis 8 或 Redis Stack 可作为接入目标。
- [MilvusClient.search 官方接口](https://milvus.io/api-reference/pymilvus/v2.6.x/MilvusClient/Vector/search.md)：向量搜索、标量 filter 和 output_fields。
- [Sentence Transformers CrossEncoder](https://www.sbert.net/docs/package_reference/cross_encoder/model.html)：query-document 成对打分与 local_files_only 模型加载约束。

Python 实际安装版本保存在 `requirements.lock.txt`。真实 LLM、Redis/Milvus/BGE、MySQL、JWT issuer 的联调结论单独以验证记录为准，不由离线测试推断。
