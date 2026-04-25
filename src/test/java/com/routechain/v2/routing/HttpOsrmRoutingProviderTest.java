package com.routechain.v2.routing;

import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.Test;

import java.net.InetSocketAddress;
import java.time.Duration;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class HttpOsrmRoutingProviderTest {

    @Test
    void parsesOsrmGeoJsonRoute() throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/route/v1/driving/106.0,10.0;106.1,10.1", exchange -> {
            byte[] body = ("""
                    {"code":"Ok","routes":[{"distance":1550.0,"duration":360.0,"geometry":{"type":"LineString","coordinates":[[106.0,10.0],[106.05,10.04],[106.1,10.1]]}}]}
                    """).getBytes(java.nio.charset.StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, body.length);
            exchange.getResponseBody().write(body);
            exchange.close();
        });
        server.start();
        try {
            RoutingProvider fallback = new SyntheticRoutingProvider(new BestPathRouter(new SyntheticRoadGraphProvider(), new RouteCostFunction()));
            HttpOsrmRoutingProvider provider = new HttpOsrmRoutingProvider(
                    "http://127.0.0.1:" + server.getAddress().getPort(),
                    Duration.ofSeconds(1),
                    Duration.ofSeconds(1),
                    new RouteCostFunction(),
                    fallback);

            RoutingRouteResult result = provider.route(new BestPathRequest(
                    new RouteStop("from", 10.0, 106.0, "driver", "zone", 0.0),
                    new RouteStop("to", 10.1, 106.1, "pickup", "zone", 0.0),
                    "traffic",
                    "clear",
                    15,
                    "road-refinement"));

            assertEquals("osrm-routing", result.provider());
            assertEquals("osrm-road-polyline", result.geometryKind());
            assertEquals(3, result.polyline().size());
            assertEquals("osrm-road-polyline", result.legVector().geometryKind());
            assertTrue(result.legVector().distanceMeters() > 0.0);
            assertTrue(result.legVector().travelTimeSeconds() > 0.0);
        } finally {
            server.stop(0);
        }
    }
}
