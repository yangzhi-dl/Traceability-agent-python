"""从 fullstack_agent_mvp 目录运行：python -m python_service.evals.run_eval --mode mock。

每次试验使用全新的服务/检查点与唯一工单。模拟的 baseline 是对纠错行为的
消融对照，而非历史生产基线。
"""
import argparse
import json
import statistics
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from ..agent_graph import TraceService, selected_mode
from ..schemas import DiagnoseRequest, Identity, ResumeRequest
from .graders import SemanticGrader, TrajectoryGrader

ROOT = Path(__file__).resolve().parents[2]


def metrics(successes: list[list[bool]]) -> dict[str, float]:
    if not successes or any(len(row) != 3 for row in successes):
        raise ValueError('Pass^3 requires exactly three independent trials per sample')
    # Pass^1 等于每次运行的平均成功率，而非仅取第一次侥幸通过。
    return {'pass1': sum(sum(row) for row in successes) / (3 * len(successes)),
            'pass3': sum(all(row) for row in successes) / len(successes),
            'claw_pass_hat3': statistics.mean((sum(row) / 3) ** 3 for row in successes)}


def golden_errors(sample, result, mode):
    errors = []
    if result.report and sample.get('expected_model') != result.report.model_code:
        errors.append('golden model mismatch')
    if result.report:
        cause = result.report.d4_root_cause
        for field in sample.get('expected_anomalies', []):
            # Mock 报告使用字段名；真实模型由裁判做语义校验。
            if mode == 'mock' and field not in cause:
                errors.append(f'golden root cause omits {field}')
        if sample['id'] in {'G02', 'G07'} and result.report.factors['Material'].status != 'NORMAL':
            errors.append('B model moisture must not be classified as abnormal')
    if mode == 'mock' and len(result.episodic_memory) < sample.get('min_reflections', 0):
        errors.append('fault path was not exercised')
    if sample.get('approve') and sum(t.tool == 'freeze_erp_stock_batch' and t.outcome == 'FOUND' for t in result.trajectory) != 1:
        errors.append('approved action must occur exactly once')
    return errors


def run(mode='auto', policy='optimized', output_dir: Path | None = None):
    actual = selected_mode(mode)
    samples = json.loads(Path(__file__).with_name('golden_dataset.json').read_text(encoding='utf-8'))
    semantic = SemanticGrader(actual)
    trajectory = TrajectoryGrader()
    results, groups = [], []
    for sample in samples:
        group = []
        for trial in range(3):
            started = time.perf_counter()
            service = TraceService(mode=actual)
            order = f'{sample["id"]}-{trial}-{uuid4().hex[:8]}'
            identity = Identity(tenant_id='eval', user_id='engineer', role=sample['role'], trace_id=uuid4().hex)
            try:
                result = service.diagnose(DiagnoseRequest(work_order_id=order, batch_no=sample['batch_no'],
                    request_freeze=sample['request_freeze']), identity, fault=sample['fault'], policy=policy)
                waiting_seen = result.status == 'WAITING_APPROVAL'
                if waiting_seen and sample.get('approve'):
                    result = service.resume(ResumeRequest(work_order_id=order, approval_id=result.approval_id, approved=True),
                                            identity.model_copy(update={'role': 'supervisor', 'user_id': 'supervisor'}))
                audit = trajectory.grade(result, sample['expected_status'])
                judge = semantic.grade(result, sample['expected_status'], reference=sample)
                errors = golden_errors(sample, result, actual)
                if sample.get('approve') and not waiting_seen:
                    errors.append('missing real HITL interrupt')
                passed = audit.score == judge.score == 1 and not errors
                results.append({'sample': sample['id'], 'trial': trial + 1, 'passed': passed,
                    'trajectory': audit.model_dump(), 'semantic': judge.model_dump(), 'golden_errors': errors,
                    'duration_ms': round((time.perf_counter() - started) * 1000, 2), 'result': result.model_dump()})
            except Exception as exc:
                passed = False
                results.append({'sample': sample['id'], 'trial': trial + 1, 'passed': False,
                                'error': type(exc).__name__})  # 日志中不记录 HTTP 响应或密钥
            finally:
                service.close()
            group.append(passed)
        groups.append(group)
    stats = metrics(groups)
    audit_rate = sum(r.get('trajectory', {}).get('score', 0) for r in results) / len(results)
    semantic_rate = sum(r.get('semantic', {}).get('score', 0) for r in results) / len(results)
    failures = Counter()
    for r in results:
        if not r['passed']:
            reasons = [r.get('error', ''), *r.get('golden_errors', [])]
            reasons += [r[k]['reason'] for k in ['trajectory', 'semantic'] if k in r and not r[k]['score']]
            failures.update(reason for reason in reasons if reason)
    lines = ['# 工业追溯评测报告', '', f'- UTC: {datetime.now(timezone.utc).isoformat()}',
             f'- 模式: **{actual}**；策略: **{policy}**；10 条样本 × 3 次 = 30 次独立运行',
             '- 数据: 合成教学黄金集；不是生产流量、不是独立保留集，也不是泛化能力证明。',
             '- 离线模式使用真实 LangGraph/ToolNode/interrupt 和规则裁判；无真实 LLM 语义质量结论。',
             '- LLM 模式不注入 Mock Actor 故障；故障覆盖计数仅在 Mock 模式验证。', '',
             '| 指标 | 本次实测 |', '|---|---:|',
             f'| Pass^1（全部运行成功率） | {stats["pass1"]:.1%} |',
             f'| 轨迹命中率 | {audit_rate:.1%} |', f'| 语义/规则裁判通过率 | {semantic_rate:.1%} |',
             f'| Pass^3（每样本三次全部通过） | {stats["pass3"]:.1%} |',
             f'| claw-eval 公式 mean((c/n)^3) | {stats["claw_pass_hat3"]:.1%} |', '',
             'Pass^3 包含按预期拒绝和降级的安全用例成功，不等于诊断报告生成率。', '',
             '| 样本 | 说明 | 三次结果 |', '|---|---|---|']
    lines += [f'| {s["id"]} | {s["description"]} | {" / ".join("PASS" if ok else "FAIL" for ok in row)} |' for s, row in zip(samples, groups)]
    lines += ['', '## Bad Case 归因', '']
    lines += [f'- {count} 次：{reason}' for reason, count in failures.items()] or ['- 本次未发现；仅说明这十条合成样本在当前模式通过。']
    report = '\n'.join(lines) + '\n'
    folder = output_dir or ROOT / 'evidence' / f'{actual}-{policy}'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'report.md').write_text(report, encoding='utf-8')
    (folder / 'trials.json').write_text(json.dumps({'mode': actual, 'policy': policy, 'metrics': stats, 'trials': results},
                                                ensure_ascii=False, indent=2), encoding='utf-8')
    print(report)
    return stats, results


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['auto', 'mock', 'llm'], default='auto')
    parser.add_argument('--policy', choices=['optimized', 'baseline'], default='optimized')
    args = parser.parse_args()
    run(args.mode, args.policy)
