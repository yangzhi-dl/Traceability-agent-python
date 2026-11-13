-- Run explicitly in a NEW MySQL 8 database; application never runs DDL automatically.
CREATE TABLE defect_work_order (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    tenant_id VARCHAR(64) NOT NULL,
    work_order_id VARCHAR(64) NOT NULL,
    owner_id VARCHAR(100) NOT NULL,
    batch_no VARCHAR(80) NOT NULL,
    request_freeze BOOLEAN NOT NULL,
    status VARCHAR(32) NOT NULL,
    operation_state VARCHAR(32) NOT NULL,
    last_operation VARCHAR(16),
    approval_id VARCHAR(100),
    approval_decision BOOLEAN,
    approver_id VARCHAR(100),
    trace_id VARCHAR(100),
    report_json JSON,
    response_json JSON,
    version BIGINT NOT NULL DEFAULT 0,
    updated_at DATETIME(6) NOT NULL,
    UNIQUE KEY uk_tenant_order (tenant_id, work_order_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
