package com.example.tracegateway;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.Jwt;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class ActorTest {
    @Test
    void mapsOnlyVerifiedClaimsAndChoosesStrongestRole() {
        Jwt jwt = Jwt.withTokenValue("test").header("alg", "RS256").subject("alice")
                .claim("tenant_id", "factory-a")
                .claim("roles", List.of("viewer", "quality_engineer", "supervisor")).build();
        assertThat(Actor.from(jwt)).isEqualTo(new Actor("factory-a", "alice", "supervisor"));
    }

    @Test
    void rejectsMissingTenantAndUnknownRoles() {
        Jwt jwt = Jwt.withTokenValue("test").header("alg", "RS256").subject("alice")
                .claim("roles", List.of("admin")).build();
        assertThatThrownBy(() -> Actor.from(jwt)).hasMessageContaining("identity");
    }
}
