# 交付验证记录

日期：2026-10-31。验证对象仅为 `fullstack_agent_mvp/`。

| 检查 | 实际结果 | 记录 |
|---|---|---|
| 用户指定文件清单 | 11 / 11 存在，五章指南齐全 | implementation_plan.md、ultimate_interview_guide.md |
| Python 3.11 测试 | 20 passed | python-tests.txt |
| Python 语法编译 | compileall 退出码 0 | 本次命令输出 |
| Java 17 编译与测试 | 8 tests，0 failures，0 errors | java-tests.txt；Java target/surefire-reports |
| 优化策略离线评测 | 10 样本 × 3，30 / 30 成功；Pass^1、轨迹命中、经验 Pass^3 均 100% | mock-optimized/report.md、trials.json |
| 关闭纠错的 Mock 消融 | 18 / 30；各指标 60%；G04–G07 失败 | mock-baseline/report.md、trials.json |
| 原文件保护 | 2,265 个已跟踪旧文件及参考文件全部 SHA-256 一致，缺失/变化 0 | protected-files-before.json、protected-files-verification.json |
| Git 状态 | 原有 ref_repos/、tmp/ 未跟踪状态保留，仅新增 fullstack_agent_mvp/ | 本次 git status 输出 |

Python 测试执行真实 StateGraph/ToolNode/interrupt/Command、Pydantic、FastAPI TestClient；覆盖格式与时间窗自愈、证据遗漏、三次预算耗尽、未知批次、人工审批、跨租户/越权/替换审批/反转决定、重复请求、并发互斥、精确型号检索、假数值和非法轨迹拒绝、SSE 格式。模型分支另用本地 ScriptedProvider 验证 bind_tools/structured output 衔接，没有调用真实模型服务。

Java 测试覆盖 JWT claim 映射、受信 HTTP 头、工单诊断→等待审批→恢复→持久化调用、重复审批、网络错误释放锁与重试、取消订阅释放锁、越权/反转审批、跨线程响应校验。Mapper、Redis、HTTP 使用测试替身；不是实际基础设施联调。

首次 Python 用例在图不存在时失败；错误批次证据测试先复现失败，再加入请求批次绑定。后续模型分支测试发现显式 null 冻结结果的处理缺口，修复后全套 20 测试通过。Java Actor claim 测试先因骨架未实现失败，后实现并扩展到 8 项通过。

## 验证边界

- 实际模型 API、真实 LLM 裁判、RedisSaver 服务、Milvus/BGE 模型、MySQL、JWT 签发方和外部 ERP 未做端到端联调。
- Java 是独立可编译的网关示范，真实运行需要配置 README 列明的基础设施。
- Mock 100% 是确定性控制流程回归结果，不能当作真实模型准确率、随机稳定性或生产收益。
- D6/D8 保持待现场验证；冻结成功是 Mock ERP 返回，不是真实库存操作。
- 没有修改旧 Java/配置/参考源码，没有 Git commit、push 或分支切换。
