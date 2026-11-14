"""基于证据的确定性报告构造，仅用于离线教学模式。"""
from .schemas import FactorFinding, Measurement, RootCause8DReport

UNITS = {'moisture_pct': '%', 'temperature_c': '°C', 'pressure_mpa': 'MPa', 'rpm': 'rpm'}


def build_report(state: dict) -> RootCause8DReport:
    evidence = state['evidence']
    mes = evidence['query_defect_inspection']['data']
    erp = evidence['trace_erp_work_order_bom']['data']
    sensor = evidence['query_equipment_telemetry']['data']
    sop = evidence['retrieve_sop_and_8d_cases']['data']
    standards = [d for d in sop['documents'] if d['kind'] == 'SOP' and d['model_code'] == mes['model_code']]
    if not standards:
        raise ValueError('No model-matched SOP')
    limits = standards[0]['limits']
    measurements = []
    abnormalities = []
    for tool_name, fields in [('trace_erp_work_order_bom', ['moisture_pct']),
                              ('query_equipment_telemetry', ['temperature_c', 'pressure_mpa', 'rpm'])]:
        obs = evidence[tool_name]
        for field in fields:
            value = obs['data'][field]
            measurements.append(Measurement(name=field, value=value, unit=UNITS[field],
                                            source_id=obs['evidence_id'], model_code=mes['model_code']))
            if field in limits and not limits[field][0] <= value <= limits[field][1]:
                abnormalities.append(f'{field}={value}{UNITS[field]} 超出 {limits[field]}，标准 {standards[0]["id"]}')
    def factor(status, finding, name):
        return FactorFinding(status=status, finding=finding, evidence_ids=[evidence[name]['evidence_id']])
    moisture_bad = erp['moisture_pct'] > limits['moisture_pct'][1]
    machine_bad = any(not limits[k][0] <= sensor[k] <= limits[k][1] for k in limits if k in sensor)
    frozen = (state.get('freeze_result') or {}).get('data', {}).get('frozen', False)
    return RootCause8DReport(
        work_order_id=state['request']['work_order_id'], batch_no=mes['batch_no'], model_code=mes['model_code'],
        d1_team=['质量工程师', '工艺工程师', '车间主管'],
        d2_problem=f'{mes["defect"]}，部位 {mes["location"]}，抽检不良率 {mes["defect_rate"]:.0%}',
        d3_containment='模拟 ERP 已冻结问题原料并生成 CAPA' if frozen else '建议隔离关联库存；未执行冻结',
        d4_root_cause='；'.join(abnormalities) + '。以上支持相关性归因假设，需对照实验确认因果。',
        d5_corrective_actions=['按本型号 SOP 复核异常参数', '隔离复检并开展受控对照试验'],
        d6_validation='待执行：按相同抽样方案比较纠正前后不良率，未宣称已验证有效',
        d7_prevention=['维护型号与 SOP 版本绑定', '增加物料与机台参数联合检查'],
        d8_closure='待质量负责人验证和签署；本次仅完成诊断草稿',
        factors={
            'Man': factor('UNVERIFIED', '培训记录有效，但尚无操作过程核验，不能排除人为因素', 'query_defect_inspection'),
            'Machine': factor('ABNORMAL' if machine_bad else 'NORMAL', '机台参数对照同型号 SOP', 'query_equipment_telemetry'),
            'Material': factor('ABNORMAL' if moisture_bad else 'NORMAL', '物料含水率对照同型号 SOP', 'trace_erp_work_order_bom'),
            'Method': factor('UNVERIFIED', '已取得 SOP 标准，现场执行一致性仍需确认', 'retrieve_sop_and_8d_cases'),
            'Environment': factor('UNVERIFIED', '仅有湿度记录，缺少环境验收阈值，不能判定正常', 'query_defect_inspection'),
        }, measurements=measurements, evidence_ids=[v['evidence_id'] for v in evidence.values()],
        limitations=['全部数据来自合成 Mock，非生产验证', '4M1E 覆盖不等于每个维度已经排除', '8D D6/D8 尚未现场验证闭环'])
