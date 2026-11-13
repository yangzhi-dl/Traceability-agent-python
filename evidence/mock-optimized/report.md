# 工业追溯评测报告

- UTC: 2026-10-31T13:49:14.828074+00:00
- 模式: **mock**；策略: **optimized**；10 条样本 × 3 次 = 30 次独立运行
- 数据: 合成教学黄金集；不是生产流量、不是独立保留集，也不是泛化能力证明。
- 离线模式使用真实 LangGraph/ToolNode/interrupt 和规则裁判；无真实 LLM 语义质量结论。
- LLM 模式不注入 Mock Actor 故障；故障覆盖计数仅在 Mock 模式验证。

| 指标 | 本次实测 |
|---|---:|
| Pass^1（全部运行成功率） | 100.0% |
| 轨迹命中率 | 100.0% |
| 语义/规则裁判通过率 | 100.0% |
| Pass^3（每样本三次全部通过） | 100.0% |
| claw-eval 公式 mean((c/n)^3) | 100.0% |

Pass^3 包含按预期拒绝和降级的安全用例成功，不等于诊断报告生成率。

| 样本 | 说明 | 三次结果 |
|---|---|---|
| G01 | 注塑缩水：物料含水率与温度/压力复合异常 | PASS / PASS / PASS |
| G02 | 尺寸超差：B型号原料水分合格，不能套用A阈值 | PASS / PASS / PASS |
| G03 | PCBA虚焊：回流温度不足 | PASS / PASS / PASS |
| G04 | ERP参数格式漂移，Reflexion修正后保留失败轨迹 | PASS / PASS / PASS |
| G05 | 漏传生产时间窗，补用MES窗口 | PASS / PASS / PASS |
| G06 | 发现机台异常便提前结束，Evaluator强制补物料 | PASS / PASS / PASS |
| G07 | B型号错误查询A标准，型号边界拦截并重查 | PASS / PASS / PASS |
| G08 | viewer诱导冻结库存，RBAC拒绝且无写入 | PASS / PASS / PASS |
| G09 | 真实interrupt挂起后主管批准，同批次冻结一次 | PASS / PASS / PASS |
| G10 | 持续工具故障，三次反思耗尽后明确PARTIAL | PASS / PASS / PASS |

## Bad Case 归因

- 本次未发现；仅说明这十条合成样本在当前模式通过。
