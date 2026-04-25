package com.routechain.v2.routing;

import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.Test;

import java.net.InetSocketAddress;
import java.time.Duration;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class OsrmTableClientTest {

    @Test
    void parsesDurationsDistancesAndSnappedPoints() throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/table/v1/driving/106.0,10.0;106.1,10.1;106.2,10.2", exchange -> {
            byte[] body = ("""
                    {"code":"Ok",
                     "sources":[{"name":"A","distance":3.0,"location":[106.0001,10.0001]}],
                     "destinations":[{"name":"B","distance":4.0,"location":[106.1001,10.1001]},{"name":"C","distance":5.0,"location":[106.2001,10.2001]}],
                     "durations":[[0.0,120.5]],
                     "distances":[[0.0,1550.0]]}
                    """).getBytes(java.nio.charset.StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, body.length);
            exchange.getResponseBody().write(body);
            exchange.close();
        });
        server.start();
        try {
            OsrmTableClient client = new OsrmTableClient("http://127.0.0.1:" + server.getAddress().getPort(), Duration.ofSeconds(1), Duration.ofSeconds(1), new DurationMatrixCache());

            DurationMatrix matrix = client.fetchMatrix(
                    List.of(stop("source", 10.0, 106.0)),
                    List.of(stop("dest-1", 10.1, 106.1), stop("dest-2", 10.2, 106.2)));

            assertEquals("osrm-table", matrix.provider());
            assertEquals(0, matrix.nullDurationCount());
            assertEquals(120.5, matrix.durationSeconds(0, 1), 1e-9);
            assertEquals(1550.0, matrix.distanceMeters(0, 1), 1e-9);
            assertEquals(10.0001, matrix.sources().getFirst().snappedLatitude(), 1e-9);
            assertEquals(106.2001, matrix.destinations().get(1).snappedLongitude(), 1e-9);
            assertTrue(matrix.degradeReasons().isEmpty());
        } finally {
            server.stop(0);
        }
    }

    @Test
    void preservesNullCellsAndCachesByCoordinateSet() throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        int[] calls = {0};
        server.createContext("/table/v1/driving/106.0,10.0;106.1,10.1", exchange -> {
            calls[0]++;
            byte[] body = ("""
                    {"code":"Ok",
                     "sources":[{"name":"A","distance":0.0,"location":[106.0,10.0]}],
                     "destinations":[{"name":"B","distance":0.0,"location":[106.1,10.1]}],
                     "durations":[[null]],
                     "distances":[[42.0]]}
                    """).getBytes(java.nio.charset.StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, body.length);
            exchange.getResponseBody().write(body);
            exchange.close();
        });
        server.start();
        try {
            DurationMatrixCache cache = new DurationMatrixCache();
            OsrmTableClient client = new OsrmTableClient("http://127.0.0.1:" + server.getAddress().getPort(), Duration.ofSeconds(1), Duration.ofSeconds(1), cache);
            List<RouteStop> sources = List.of(stop("source", 10.0, 106.0));
            List<RouteStop> destinations = List.of(stop("dest", 10.1, 106.1));

            DurationMatrix first = client.fetchMatrix(sources, destinations);
            DurationMatrix second = client.fetchMatrix(sources, destinations);

            assertNull(first.durationSeconds(0, 0));
            assertEquals(1, first.nullDurationCount());
            assertEquals(42.0, second.distanceMeters(0, 0), 1e-9);
            assertEquals(1, calls[0]);
            assertEquals(1, cache.hitCount());
            assertEquals(1, cache.missCount());
            assertEquals(2, cache.requestCount());
            assertEquals(0.5, cache.hitRate(), 1e-9);
        } finally {
            server.stop(0);
        }
    }

    private RouteStop stop(String id, double lat, double lon) {
        return new RouteStop(id, lat, lon, "test", "zone", 0.0);
    }
}
