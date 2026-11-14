package com.example.tracegateway;

import java.util.List;
import org.redisson.Redisson;
import org.redisson.api.RedissonClient;
import org.redisson.config.Config;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.JwtClaimValidator;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class GatewayConfiguration {
    @Bean(destroyMethod = "shutdown")
    RedissonClient redisson(@Value("${gateway.redis-address}") String address) {
        Config config = new Config();
        config.useSingleServer().setAddress(address);
        config.setLockWatchdogTimeout(30_000);
        return Redisson.create(config);
    }

    @Bean
    JwtDecoder jwtDecoder(@Value("${gateway.jwt-issuer}") String issuer,
                          @Value("${gateway.jwt-jwk-uri}") String jwkUri,
                          @Value("${gateway.jwt-audience}") String audience) {
        NimbusJwtDecoder decoder = NimbusJwtDecoder.withJwkSetUri(jwkUri).build();
        JwtClaimValidator<List<String>> audienceValidator =
                new JwtClaimValidator<>("aud", values -> values != null && values.contains(audience));
        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(issuer), audienceValidator));
        return decoder;
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        JwtGrantedAuthoritiesConverter roles = new JwtGrantedAuthoritiesConverter();
        roles.setAuthoritiesClaimName("roles");
        roles.setAuthorityPrefix("ROLE_");
        JwtAuthenticationConverter converter = new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(roles);
        return http.csrf(csrf -> csrf.disable()) // 无状态 Bearer API，不依赖 Cookie 认证
                .sessionManagement(s -> s.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(a -> a.anyRequest().authenticated())
                .oauth2ResourceServer(o -> o.jwt(j -> j.jwtAuthenticationConverter(converter)))
                .build();
    }
}
