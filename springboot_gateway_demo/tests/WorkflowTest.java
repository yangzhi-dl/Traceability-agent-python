package com.example.tracegateway;

import com.baomidou.mybatisplus.core.conditions.Wrapper;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Duration;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.redisson.api.RBucket;
import org.redisson.api.RLock;
import org.redisson.api.RedissonClient;
import org.redisson.client.codec.StringCodec;
import org.redisson.misc.CompletableFutureWrapper;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.timeout;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class WorkflowTest {
    private final ObjectMapper json = new ObjectMapper();
    private final Actor engineer = new Actor("plant-a", "alice", "quality_engineer");
    private final Actor supervisor = new Actor("plant-a", "bob", "supervisor");
    private final DefectTraceController.DiagnoseRequest request =
            new DefectTraceController.DiagnoseRequest("WO-1", "FG-20261001-001", true);
    private PythonAgentWebClient python;
    private RLock lock;
    private TraceWorkflow service;
    private AtomicReference<WorkOrderEntity> stored;

    @BeforeEach
    @SuppressWarnings("unchecked")
    void setup() {
        WorkOrderMapper mapper = mock(WorkOrderMapper.class);
        python = mock(PythonAgentWebClient.class);
        RedissonClient redis = mock(RedissonClient.class);
        lock = mock(RLock.class);
        when(redis.getLock(anyString())).thenReturn(lock);
        when(lock.tryLockAsync(eq(0L), eq(-1L), eq(TimeUnit.SECONDS), anyLong()))
                .thenAnswer(i -> new CompletableFutureWrapper<>(true));
        when(lock.unlockAsync(anyLong())).thenAnswer(i -> new CompletableFutureWrapper<Void>((Void) null));
        doReturn(mock(RBucket.class)).when(redis).getBucket(anyString(), eq(StringCodec.INSTANCE));
        stored = new AtomicReference<>();
        when(mapper.selectOne(any(Wrapper.class))).thenAnswer(i -> stored.get());
        when(mapper.insert(any(WorkOrderEntity.class))).thenAnswer(i -> {
            WorkOrderEntity row = i.getArgument(0); row.setId(1L); stored.set(row); return 1;
        });
        when(mapper.update(any(WorkOrderEntity.class), any(Wrapper.class))).thenAnswer(i -> {
            stored.set(i.getArgument(0)); return 1;
        });
        service = new TraceWorkflow(mapper, python, redis, json);
    }

    private JsonNode response(String status) {
        return json.createObjectNode().put("thread_id", "plant-a:WO-1").put("status", status)
                .put("approval_id", "approval-1").set("report", "COMPLETED".equals(status)
                        ? json.createObjectNode().put("work_order_id", "WO-1") : json.nullNode());
    }

    @Test
    void diagnosesWaitsApprovesPersistsAndReplaysOnce() {
        when(python.diagnose(any(), any(), anyString())).thenReturn(Mono.just(response("WAITING_APPROVAL")));
        when(python.resume(any(), any(), anyString())).thenReturn(Mono.just(response("COMPLETED")));
        assertThat(service.diagnose(request, engineer, "t1").block().path("status").asText()).isEqualTo("WAITING_APPROVAL");
        assertThat(stored.get().getReportJson()).isNull();
        DefectTraceController.ResumeRequest approval = new DefectTraceController.ResumeRequest("WO-1", "approval-1", true);
        assertThat(service.resume(approval, supervisor, "t2").block().path("status").asText()).isEqualTo("COMPLETED");
        service.resume(approval, supervisor, "t3").block();
        assertThat(stored.get().getReportJson()).contains("WO-1");
        assertThat(stored.get().getApproverId()).isEqualTo("bob");
        verify(python, times(1)).resume(any(), any(), anyString());
        verify(lock, times(3)).unlockAsync(anyLong());
    }

    @Test
    void releasesLockOnRemoteFailureAndAllowsSameRequestRetry() {
        when(python.diagnose(any(), any(), anyString())).thenReturn(Mono.error(new IllegalStateException("network")),
                Mono.just(response("WAITING_APPROVAL")));
        StepVerifier.create(service.diagnose(request, engineer, "t1")).expectError(IllegalStateException.class).verify();
        assertThat(stored.get().getOperationState()).isEqualTo("RETRYABLE_ERROR");
        assertThat(service.diagnose(request, engineer, "t2").block().path("status").asText()).isEqualTo("WAITING_APPROVAL");
        verify(lock, times(2)).unlockAsync(anyLong());
    }

    @Test
    void rejectsUnprivilegedApprovalAndConflictingDecision() {
        when(python.diagnose(any(), any(), anyString())).thenReturn(Mono.just(response("WAITING_APPROVAL")));
        when(python.resume(any(), any(), anyString())).thenReturn(Mono.error(new IllegalStateException("network")));
        service.diagnose(request, engineer, "t1").block();
        DefectTraceController.ResumeRequest approval = new DefectTraceController.ResumeRequest("WO-1", "approval-1", true);
        StepVerifier.create(service.resume(approval, engineer, "t2")).expectErrorMatches(
                e -> e instanceof ResponseStatusException r && r.getStatusCode() == HttpStatus.FORBIDDEN).verify();
        StepVerifier.create(service.resume(approval, supervisor, "t3")).expectError(IllegalStateException.class).verify();
        StepVerifier.create(service.resume(new DefectTraceController.ResumeRequest("WO-1", "approval-1", false), supervisor, "t4"))
                .expectErrorMatches(e -> e instanceof ResponseStatusException r && r.getStatusCode() == HttpStatus.CONFLICT).verify();
    }

    @Test
    void rejectsCrossThreadResponse() {
        WorkOrderEntity row = new WorkOrderEntity(); row.setTenantId("plant-a"); row.setWorkOrderId("WO-1");
        JsonNode wrong = json.createObjectNode().put("thread_id", "plant-b:WO-1").put("status", "PARTIAL");
        assertThatThrownBy(() -> TraceWorkflow.validateResponse(row, wrong)).isInstanceOf(ResponseStatusException.class);
    }

    @Test
    void releasesLockWhenHttpSubscriberCancels() {
        when(python.diagnose(any(), any(), anyString())).thenReturn(Mono.never());
        StepVerifier.create(service.diagnose(request, engineer, "cancel-trace"))
                .thenAwait(Duration.ofMillis(200)).thenCancel().verify();
        verify(lock, timeout(1000)).unlockAsync(anyLong());
    }
}
