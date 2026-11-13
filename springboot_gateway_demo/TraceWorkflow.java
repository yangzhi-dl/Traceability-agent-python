package com.example.tracegateway;

import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.UpdateWrapper;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Duration;
import java.time.LocalDateTime;
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.Supplier;
import org.redisson.api.RBucket;
import org.redisson.api.RLock;
import org.redisson.api.RedissonClient;
import org.redisson.client.codec.StringCodec;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Service
public class TraceWorkflow {
    private static final AtomicLong OWNERS = new AtomicLong();
    private static final Set<String> TERMINAL = Set.of("COMPLETED", "PARTIAL", "DENIED", "REJECTED");
    private final WorkOrderMapper mapper;
    private final PythonAgentWebClient python;
    private final RedissonClient redis;
    private final ObjectMapper json;

    public TraceWorkflow(WorkOrderMapper mapper, PythonAgentWebClient python, RedissonClient redis, ObjectMapper json) {
        this.mapper = mapper;
        this.python = python;
        this.redis = redis;
        this.json = json;
    }

    private record Lease(RLock lock, long owner) { }

    /** Explicit owner ID remains stable across Reactor scheduler/thread changes. */
    private <T> Mono<T> withLock(String tenant, String order, Supplier<Mono<T>> work) {
        return Mono.defer(() -> {
            RLock lock = redis.getLock("trace:gateway:" + tenant + ":" + order);
            long owner = OWNERS.incrementAndGet();
            Mono<Lease> acquire = Mono.fromCompletionStage(lock.tryLockAsync(0, -1, TimeUnit.SECONDS, owner))
                    .flatMap(ok -> ok ? Mono.just(new Lease(lock, owner)) : Mono.error(conflict("Work order is busy")));
            // -1 lease delegates renewal to the Redisson watchdog. Cleanup runs on every terminal path.
            return Mono.usingWhen(acquire, ignored -> Mono.defer(work),
                    this::unlock, (lease, error) -> unlock(lease), this::unlock);
        });
    }

    private Mono<Void> unlock(Lease lease) {
        return Mono.fromCompletionStage(lease.lock().unlockAsync(lease.owner())).then();
    }

    private <T> Mono<T> db(Supplier<T> action) {
        return Mono.fromCallable(action::get).subscribeOn(Schedulers.boundedElastic());
    }

    public Mono<JsonNode> diagnose(DefectTraceController.DiagnoseRequest request, Actor actor, String traceId) {
        if (!Set.of("quality_engineer", "supervisor").contains(actor.role())) {
            return Mono.error(new ResponseStatusException(HttpStatus.FORBIDDEN, "Diagnosis role denied"));
        }
        return withLock(actor.tenantId(), request.workOrderId(), () -> db(() -> {
            WorkOrderEntity row = lookup(actor.tenantId(), request.workOrderId());
            if (row != null) {
                owner(row, actor);
                if (!row.getBatchNo().equals(request.batchNo()) || row.getRequestFreeze() != request.requestFreeze()) {
                    throw conflict("Work order already has different parameters");
                }
                return row;
            }
            row = new WorkOrderEntity();
            row.setTenantId(actor.tenantId()); row.setWorkOrderId(request.workOrderId());
            row.setOwnerId(actor.userId()); row.setBatchNo(request.batchNo()); row.setRequestFreeze(request.requestFreeze());
            row.setStatus("NEW"); row.setOperationState("IDLE"); row.setVersion(0L);
            row.setUpdatedAt(LocalDateTime.now()); mapper.insert(row);
            return row;
        }).flatMap(row -> {
            if (row.getResponseJson() != null) { return Mono.just(parse(row.getResponseJson())); }
            return db(() -> reserve(row, "DIAGNOSE", traceId)).flatMap(reserved ->
                    invokeAndSave(reserved, python.diagnose(request, actor, traceId)));
        }));
    }

    public Mono<JsonNode> resume(DefectTraceController.ResumeRequest request, Actor actor, String traceId) {
        if (!actor.role().equals("supervisor")) {
            return Mono.error(new ResponseStatusException(HttpStatus.FORBIDDEN, "Only supervisor may approve"));
        }
        return withLock(actor.tenantId(), request.workOrderId(), () -> db(() -> {
            WorkOrderEntity row = require(actor.tenantId(), request.workOrderId());
            if (!Objects.equals(row.getApprovalId(), request.approvalId())) { throw conflict("Approval ID mismatch"); }
            if (row.getApprovalDecision() != null && !row.getApprovalDecision().equals(request.approved())) {
                throw conflict("Approval decision is immutable");
            }
            if (TERMINAL.contains(row.getStatus()) && "RESUME".equals(row.getLastOperation())) { return row; }
            if (!"WAITING_APPROVAL".equals(row.getStatus())) { throw conflict("No pending approval"); }
            row.setApprovalDecision(request.approved()); row.setApproverId(actor.userId());
            return reserve(row, "RESUME", traceId); // decision committed before HTTP; retries must use same value
        }).flatMap(row -> TERMINAL.contains(row.getStatus())
                ? Mono.just(parse(row.getResponseJson()))
                : invokeAndSave(row, python.resume(request, actor, traceId))));
    }

    private WorkOrderEntity reserve(WorkOrderEntity row, String operation, String traceId) {
        row.setOperationState("RUNNING"); row.setLastOperation(operation); row.setTraceId(traceId);
        cas(row);
        return row;
    }

    private Mono<JsonNode> invokeAndSave(WorkOrderEntity row, Mono<JsonNode> invocation) {
        return invocation.switchIfEmpty(Mono.error(new ResponseStatusException(HttpStatus.BAD_GATEWAY, "Empty Python response")))
                .flatMap(response -> db(() -> {
                    validateResponse(row, response);
                    row.setStatus(response.path("status").asText()); row.setOperationState("IDLE");
                    if (!response.path("approval_id").isMissingNode() && !response.path("approval_id").isNull()) {
                        row.setApprovalId(response.path("approval_id").asText());
                    }
                    row.setResponseJson(response.toString());
                    if (!response.path("report").isMissingNode() && !response.path("report").isNull()) {
                        row.setReportJson(response.path("report").toString());
                    }
                    cas(row); cache(row, response.toString());
                    return response;
                })).onErrorResume(error -> db(() -> {
                    row.setOperationState("RETRYABLE_ERROR");
                    // Preserve previous WAITING_APPROVAL response so the exact decision can be retried.
                    try { cas(row); } catch (RuntimeException ignored) { /* original error remains authoritative */ }
                    return true;
                }).then(Mono.error(error)));
    }

    static void validateResponse(WorkOrderEntity row, JsonNode response) {
        String expected = row.getTenantId() + ":" + row.getWorkOrderId();
        String status = response.path("status").asText();
        if (!expected.equals(response.path("thread_id").asText())
                || !(TERMINAL.contains(status) || "WAITING_APPROVAL".equals(status))
                || ("WAITING_APPROVAL".equals(status) && response.path("approval_id").asText("").isBlank())
                || ("COMPLETED".equals(status) && !response.path("report").isObject())) {
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "Invalid Python protocol response");
        }
    }

    /** Atomic version predicate protects against stale writers after lock/network failure. */
    private void cas(WorkOrderEntity row) {
        long previous = row.getVersion();
        row.setVersion(previous + 1); row.setUpdatedAt(LocalDateTime.now());
        int changed = mapper.update(row, new UpdateWrapper<WorkOrderEntity>()
                .eq("id", row.getId()).eq("tenant_id", row.getTenantId()).eq("version", previous));
        if (changed != 1) { row.setVersion(previous); throw conflict("Concurrent work order update"); }
    }

    public Mono<JsonNode> find(String order, Actor actor) {
        return db(() -> {
            WorkOrderEntity row = require(actor.tenantId(), order);
            owner(row, actor); // authorize against database before consulting the cache
            if (row.getResponseJson() == null) { throw conflict("Diagnosis has no result yet; retry original request"); }
            try {
                RBucket<String> bucket = redis.getBucket(cacheKey(row), StringCodec.INSTANCE);
                String cached = bucket.get();
                if (cached != null) { return parse(cached); }
            } catch (RuntimeException ignored) { /* versioned cache is optional */ }
            return parse(row.getResponseJson());
        });
    }

    private WorkOrderEntity lookup(String tenant, String order) {
        return mapper.selectOne(new QueryWrapper<WorkOrderEntity>().eq("tenant_id", tenant).eq("work_order_id", order));
    }

    private WorkOrderEntity require(String tenant, String order) {
        WorkOrderEntity row = lookup(tenant, order);
        if (row == null) { throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Work order not found"); }
        return row;
    }

    private static void owner(WorkOrderEntity row, Actor actor) {
        if (!row.getOwnerId().equals(actor.userId()) && !actor.role().equals("supervisor")) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "Work order belongs to another user");
        }
    }

    private void cache(WorkOrderEntity row, String value) {
        try {
            RBucket<String> bucket = redis.getBucket(cacheKey(row), StringCodec.INSTANCE);
            bucket.set(value, Duration.ofSeconds(60));
        } catch (RuntimeException ignored) { /* Redis cache loss never invalidates an already committed report. */ }
    }

    private String cacheKey(WorkOrderEntity row) {
        return "trace:result:" + row.getTenantId() + ":" + row.getWorkOrderId() + ":" + row.getVersion();
    }

    private JsonNode parse(String value) {
        try { return json.readTree(value); }
        catch (JsonProcessingException exception) { throw new IllegalStateException("Invalid stored trace response", exception); }
    }

    private static ResponseStatusException conflict(String message) {
        return new ResponseStatusException(HttpStatus.CONFLICT, message);
    }
}
