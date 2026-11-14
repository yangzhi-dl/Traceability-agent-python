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

/** 所有身份头均来自已验证的 JWT，绝不从用户请求头直接透传。 */
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
        // 写操作不做透明重试；由调用方用相同的工单/审批 ID 重试。
        return request(path, actor, traceId).bodyValue(body).retrieve()
                .onStatus(s -> s.isError(), response -> response.releaseBody().thenReturn(
                        new ResponseStatusException(response.statusCode(), "Python trace request failed")))
                .bodyToMono(JsonNode.class).timeout(Duration.ofMinutes(15));
    }

    /** Python 目前只发一个终结性结果事件，而非逐 token 流。 */
    public Flux<ServerSentEvent<JsonNode>> diagnoseEvents(
            DefectTraceController.DiagnoseRequest body, Actor actor, String traceId) {
        return request("/api/v1/trace/diagnose/stream", actor, traceId)
                .accept(MediaType.TEXT_EVENT_STREAM).bodyValue(body).retrieve()
                .bodyToFlux(new ParameterizedTypeReference<ServerSentEvent<JsonNode>>() { })
                .timeout(Duration.ofMinutes(15));
    }
}
