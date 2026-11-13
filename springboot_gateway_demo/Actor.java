package com.example.tracegateway;

import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.server.ResponseStatusException;

public record Actor(String tenantId, String userId, String role) {
    public static Actor from(Jwt jwt) {
        String tenant = jwt.getClaimAsString("tenant_id");
        List<String> roles = jwt.getClaimAsStringList("roles");
        if (tenant == null || !tenant.matches("[A-Za-z0-9_-]{1,64}")
                || jwt.getSubject() == null || jwt.getSubject().isBlank() || roles == null) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "Invalid identity claims");
        }
        for (String role : List.of("supervisor", "quality_engineer", "viewer")) {
            if (roles.contains(role)) {
                return new Actor(tenant, jwt.getSubject(), role);
            }
        }
        throw new ResponseStatusException(HttpStatus.FORBIDDEN, "Invalid identity roles");
    }
}
