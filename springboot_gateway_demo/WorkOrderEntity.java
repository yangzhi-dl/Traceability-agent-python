package com.example.tracegateway;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import java.time.LocalDateTime;

/** MySQL is the business authority; Redis is only the mutex/cache/checkpoint store. */
@TableName("defect_work_order")
public class WorkOrderEntity {
    @TableId(type = IdType.AUTO)
    private Long id;
    private String tenantId;
    private String workOrderId;
    private String ownerId;
    private String batchNo;
    private Boolean requestFreeze;
    private String status;
    private String operationState;
    private String lastOperation;
    private String approvalId;
    private Boolean approvalDecision;
    private String approverId;
    private String traceId;
    private String reportJson;
    private String responseJson;
    private Long version;
    private LocalDateTime updatedAt;

    public Long getId() { return id; }
    public void setId(Long v) { id = v; }
    public String getTenantId() { return tenantId; }
    public void setTenantId(String v) { tenantId = v; }
    public String getWorkOrderId() { return workOrderId; }
    public void setWorkOrderId(String v) { workOrderId = v; }
    public String getOwnerId() { return ownerId; }
    public void setOwnerId(String v) { ownerId = v; }
    public String getBatchNo() { return batchNo; }
    public void setBatchNo(String v) { batchNo = v; }
    public Boolean getRequestFreeze() { return requestFreeze; }
    public void setRequestFreeze(Boolean v) { requestFreeze = v; }
    public String getStatus() { return status; }
    public void setStatus(String v) { status = v; }
    public String getOperationState() { return operationState; }
    public void setOperationState(String v) { operationState = v; }
    public String getLastOperation() { return lastOperation; }
    public void setLastOperation(String v) { lastOperation = v; }
    public String getApprovalId() { return approvalId; }
    public void setApprovalId(String v) { approvalId = v; }
    public Boolean getApprovalDecision() { return approvalDecision; }
    public void setApprovalDecision(Boolean v) { approvalDecision = v; }
    public String getApproverId() { return approverId; }
    public void setApproverId(String v) { approverId = v; }
    public String getTraceId() { return traceId; }
    public void setTraceId(String v) { traceId = v; }
    public String getReportJson() { return reportJson; }
    public void setReportJson(String v) { reportJson = v; }
    public String getResponseJson() { return responseJson; }
    public void setResponseJson(String v) { responseJson = v; }
    public Long getVersion() { return version; }
    public void setVersion(Long v) { version = v; }
    public LocalDateTime getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(LocalDateTime v) { updatedAt = v; }
}
