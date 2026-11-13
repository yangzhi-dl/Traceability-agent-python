package com.example.tracegateway;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.JsonNode;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.util.UUID;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

/** MVC returns an async Mono; database operations are delegated off event-loop threads. */
@RestController
@RequestMapping("/api/v1/trace")
public class DefectTraceController {
    private final TraceWorkflow workflow;

    public DefectTraceController(TraceWorkflow workflow) { this.workflow = workflow; }

    public record DiagnoseRequest(
            @JsonProperty("work_order_id") @Pattern(regexp = "[A-Za-z0-9_-]{1,64}") @NotBlank String workOrderId,
            @JsonProperty("batch_no") @NotBlank @Size(max = 80) String batchNo,
            @JsonProperty("request_freeze") boolean requestFreeze) { }

    public record ResumeRequest(
            @JsonProperty("work_order_id") @Pattern(regexp = "[A-Za-z0-9_-]{1,64}") @NotBlank String workOrderId,
            @JsonProperty("approval_id") @NotBlank @Size(max = 100) String approvalId,
            @NotNull Boolean approved) { }

    @PostMapping("/diagnose")
    @PreAuthorize("hasAnyRole('quality_engineer','supervisor')")
    public Mono<JsonNode> diagnose(@Valid @RequestBody DiagnoseRequest request, @AuthenticationPrincipal Jwt jwt) {
        return workflow.diagnose(request, Actor.from(jwt), UUID.randomUUID().toString());
    }

    @PostMapping("/resume")
    @PreAuthorize("hasRole('supervisor')")
    public Mono<JsonNode> resume(@Valid @RequestBody ResumeRequest request, @AuthenticationPrincipal Jwt jwt) {
        return workflow.resume(request, Actor.from(jwt), UUID.randomUUID().toString());
    }

    @GetMapping("/work-orders/{id}")
    public Mono<JsonNode> find(@PathVariable String id, @AuthenticationPrincipal Jwt jwt) {
        return workflow.find(id, Actor.from(jwt));
    }
}
