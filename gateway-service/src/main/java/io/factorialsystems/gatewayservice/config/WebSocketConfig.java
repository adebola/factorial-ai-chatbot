package io.factorialsystems.gatewayservice.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.web.reactive.socket.client.ReactorNettyWebSocketClient;
import org.springframework.web.reactive.socket.client.WebSocketClient;
import reactor.netty.http.client.HttpClient;
import reactor.netty.http.client.WebsocketClientSpec;

/**
 * WebSocket frame-size override.
 *
 * <p>Spring Cloud Gateway proxies the agent-chat WebSocket from the browser to
 * chat-service ({@code /ws/agent/**}). Both Reactor Netty's default server-side
 * frame limit and the {@code ReactorNettyWebSocketClient}'s default
 * {@code maxFramePayloadLength} are <strong>65536 bytes (64 KB)</strong>. The
 * chat-service "welcome" frame contains the entire conversation history when a
 * session is resumed, and that payload regularly exceeds 64 KB for any session
 * with more than ~30 messages of structured tool-call output.
 *
 * <p>When the proxied frame exceeds the default limit, the gateway closes the
 * upstream socket mid-frame, the chat-service handler sees a
 * {@code WebSocketDisconnect} immediately after sending the welcome, and the
 * browser observes the WebSocket flipping connected → disconnected within a
 * few milliseconds.
 *
 * <p>This bean overrides the default {@link WebSocketClient} that
 * {@code WebsocketRoutingFilter} uses for the upstream leg, raising the
 * frame-payload limit to 1 MiB. {@code @Primary} ensures it wins over the
 * auto-configured default.
 *
 * <p>The corresponding server-side limit (browser → gateway) is governed by
 * Reactor Netty's {@code WebsocketServerSpec}, configured globally via the
 * Netty server factory. Spring Boot exposes this via
 * {@code server.netty.idle-timeout} and friends, but the frame-payload limit
 * is configured here too — see the {@code httpServer} customizer if a separate
 * server-side override becomes necessary. In practice the welcome frame is
 * outbound from the upstream, so the client-side limit is the binding one.
 */
@Configuration
public class WebSocketConfig {

    /** 1 MiB. Sessions with hundreds of messages still fit comfortably. */
    private static final int MAX_FRAME_PAYLOAD_LENGTH = 1024 * 1024;

    @Bean
    @Primary
    public WebSocketClient gatewayWebSocketClient() {
        // ReactorNettyWebSocketClient takes a Supplier<WebsocketClientSpec.Builder>
        // (not the built spec); SCG calls .build() internally each time it
        // upgrades a connection.
        return new ReactorNettyWebSocketClient(
                HttpClient.create(),
                () -> WebsocketClientSpec.builder().maxFramePayloadLength(MAX_FRAME_PAYLOAD_LENGTH));
    }
}
