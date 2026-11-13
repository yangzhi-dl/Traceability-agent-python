package com.example.tracegateway;

import com.fasterxml.jackson.databind.JsonNode;
import java.time.Duration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

/** All identity headers are derived from a verified JWT, never forwarded from user headers. */
@Component
public class PythonAgentWebClient {
    private final WebClient client;
    private final String gatewayToken;

    public PythonAgentWebClient(WebClient.Builder builder,
            @Value("${gateway.python-url}") String url,
            @Value("${gateway.shared-token}") String token) {
        if (token.isBlank()) {
            throw new IllegalArgumentException("gateway shared token must not be blank");
        }
        client = builder.baseUrl(url).codecs(c -> c.defaultCodecs().maxInMemorySize(2 * 1024 * 1024)).build();
        gatewayToken = token;
    }

    private WebClient.RequestBodySpec request(String path, Actor actor, String traceId) {
        return client.post().uri(path).contentType(MediaType.APPLICATION_JSON)
                .header("X-Gateway-Token", gatewayToken)
                .header("X-Tenant-Id", actor.tenantId()).header("X-User-Id", actor.userId())
                .header("X-User-Role", actor.role()).header("X-Trace-Id", traceId);
    }

    public Mono<JsonNode> diagnose(DefectTraceController.DiagnoseRequest body, Actor actor, String traceId) {
        return invoke("/api/v1/trace/diagnose", body, actor, traceId);
    }

    public Mono<JsonNode> resume(DefectTraceController.ResumeRequest body, Actor actor, String traceId) {
        return invoke("/api/v1/trace/resume", body, actor, traceId);
    }

    private Mono<JsonNode> invoke(String path, Object body, Actor actor, String traceId) {
        // No transparent retry of a write. The caller retries the same order/approval ID.
        return request(path, actor, traceId).bodyValue(body).retrieve()
                .onStatus(s -> s.isError(), response -> response.releaseBody().thenReturn(
                        new ResponseStatusException(response.statusCode(), "Python trace request failed")))
                .bodyToMono(JsonNode.class).timeout(Duration.ofMinutes(15));
    }

    /** Python currently emits one terminal result event, not a token stream. */
    public Flux<ServerSentEvent<JsonNode>> diagnoseEvents(
            DefectTraceController.DiagnoseRequest body, Actor actor, String traceId) {
        return request("/api/v1/trace/diagnose/stream", actor, traceId)
                .accept(MediaType.TEXT_EVENT_STREAM).bodyValue(body).retrieve()
                .bodyToFlux(new ParameterizedTypeReference<ServerSentEvent<JsonNode>>() { })
                .timeout(Duration.ofMinutes(15));
    }
}
