package com.example.tracegateway;

import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.ClientRequest;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

import static org.assertj.core.api.Assertions.assertThat;

class PythonClientTest {
    @Test
    void usesTrustedIdentityAndExactPythonRoute() {
        AtomicReference<ClientRequest> sent = new AtomicReference<>();
        WebClient.Builder builder = WebClient.builder().exchangeFunction(request -> {
            sent.set(request);
            return Mono.just(ClientResponse.create(HttpStatus.OK).header("Content-Type", MediaType.APPLICATION_JSON_VALUE)
                    .body("{\"status\":\"WAITING_APPROVAL\"}").build());
        });
        PythonAgentWebClient client = new PythonAgentWebClient(builder, "http://python:8000", "test-secret");
        client.diagnose(new DefectTraceController.DiagnoseRequest("WO-1", "FG-20261001-001", true),
                new Actor("plant-a", "alice", "quality_engineer"), "trace-1").block();
        assertThat(sent.get().url().getPath()).isEqualTo("/api/v1/trace/diagnose");
        assertThat(sent.get().headers().getFirst("X-User-Role")).isEqualTo("quality_engineer");
        assertThat(sent.get().headers().getFirst("X-Tenant-Id")).isEqualTo("plant-a");
        assertThat(sent.get().headers().getFirst("X-Gateway-Token")).isEqualTo("test-secret");
    }
}
