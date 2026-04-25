package com.routechain.v2.routing;

import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.Test;

import java.net.InetSocketAddress;
import java.time.Duration;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class HttpTomTomRoutingProviderTest {

    @Test
    void parsesTomTomPolylineRoute() throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/routing/1/calculateRoute/10.0,106.0:10.1,106.1/json", exchange -> {
            byte[] body = ("""
                    {"routes":[{"summary":{"lengthInMeters":1450,"travelTimeInSeconds":320,"trafficDelayInSeconds":20},"legs":[{"points":[{"latitude":10.0,"longitude":106.0},{"latitude":10.05,"longitude":106.05},{"latitude":10.1,"longitude":106.1}]}]}]}
                    """).getBytes(java.nio.charset.StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, body.length);
            exchange.getResponseBody().write(body);
            exchange.close();
        });
        server.start();
        try {
            RoutingProvider fallback = new SyntheticRoutingProvider(new BestPathRouter(new SyntheticRoadGraphProvider(), new RouteCostFunction()));
            HttpTomTomRoutingProvider provider = new HttpTomTomRoutingProvider(
                    "http://127.0.0.1:" + server.getAddress().getPort(),
                    "test-key",
                    Duration.ofSeconds(1),
                    Duration.ofSeconds(1),
                    new RouteCostFunction(),
                    fallback);

            RoutingRouteResult result = provider.route(new BestPathRequest(
                    new RouteStop("from", 10.0, 106.0, "driver", "zone", 0.0),
                    new RouteStop("to", 10.1, 106.1, "pickup", "zone", 0.0),
                    "traffic",
                    "clear",
                    15));

            assertEquals("tomtom-routing", result.provider());
            assertEquals("tomtom-road-polyline", result.geometryKind());
            assertEquals(3, result.polyline().size());
            assertEquals("tomtom-road-polyline", result.legVector().geometryKind());
            assertTrue(result.legVector().distanceMeters() > 0.0);
        } finally {
            server.stop(0);
        }
    }
}
