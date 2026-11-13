"""Synthetic teaching data; no actual ERP/customer records are used."""
from copy import deepcopy

START = '2026-10-01T08:00:00+08:00'
END = '2026-10-01T10:00:00+08:00'

CASES = {
    'FG-20261001-001': {
        'model_code': 'A-HOUSING', 'defect': '注塑外壳缩水', 'defect_rate': 0.12,
        'location': '加强筋背面', 'equipment_id': 'IMM-01', 'raw_batch': 'RM-20260930-001',
        'material': 'PC-ABS-A', 'supplier': 'SYNTHETIC-SUPPLIER-01', 'moisture_pct': 0.08,
        'temperature_c': 275.0, 'pressure_mpa': 52.0, 'rpm': 90.0,
        'cause': '原料含水率超标，料筒温度偏高且保压压力不足，支持缩水复合原因假设',
    },
    'FG-20261001-002': {
        'model_code': 'B-HOUSING', 'defect': '尺寸超差', 'defect_rate': 0.07,
        'location': '装配卡扣', 'equipment_id': 'IMM-02', 'raw_batch': 'RM-20260930-002',
        'material': 'PA66-B', 'supplier': 'SYNTHETIC-SUPPLIER-02', 'moisture_pct': 0.12,
        'temperature_c': 285.0, 'pressure_mpa': 65.0, 'rpm': 105.0,
        'cause': '料筒温度偏高，支持收缩率变化导致尺寸超差的假设；原料含水率在本型号标准内',
    },
    'FG-20261001-003': {
        'model_code': 'PCBA-C', 'defect': '焊接虚焊', 'defect_rate': 0.09,
        'location': '连接器焊点', 'equipment_id': 'REFLOW-01', 'raw_batch': 'RM-20260930-003',
        'material': 'SOLDER-C', 'supplier': 'SYNTHETIC-SUPPLIER-03', 'moisture_pct': 0.03,
        'temperature_c': 218.0, 'pressure_mpa': 0.0, 'rpm': 0.0,
        'cause': '回流峰值温度低于工艺下限，支持焊料润湿不足导致虚焊的假设',
    },
}

SOPS = [
    {'id': 'SOP-A-v1', 'model_code': 'A-HOUSING', 'kind': 'SOP',
     'text': 'A-HOUSING PC-ABS-A injection shrinkage moisture drying temperature pressure SOP',
     'limits': {'moisture_pct': [0.0, 0.02], 'temperature_c': [250.0, 270.0], 'pressure_mpa': [60.0, 80.0]}},
    {'id': 'SOP-B-v2', 'model_code': 'B-HOUSING', 'kind': 'SOP',
     'text': 'B-HOUSING PA66-B dimensional deviation moisture drying temperature pressure SOP',
     'limits': {'moisture_pct': [0.0, 0.15], 'temperature_c': [260.0, 280.0], 'pressure_mpa': [60.0, 75.0]}},
    {'id': 'SOP-C-v1', 'model_code': 'PCBA-C', 'kind': 'SOP',
     'text': 'PCBA-C SOLDER-C cold solder reflow peak temperature moisture SOP',
     'limits': {'moisture_pct': [0.0, 0.05], 'temperature_c': [235.0, 245.0]}},
    *[{'id': f'8D-{c["model_code"]}-history', 'model_code': c['model_code'], 'kind': '8D',
       'text': f'{c["model_code"]} historical 8D {c["cause"]}', 'limits': {}} for c in CASES.values()],
]


def case(batch: str) -> dict | None:
    record = CASES.get(batch)
    if record is None:
        return None
    return dict(deepcopy(record), batch_no=batch, production_start=START, production_end=END,
                erp_work_order=f'ERP-{batch}', operator_training='VALID', environment_rh_pct=48.0)
