package com.routechain.api;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import com.routechain.domain.WeatherProfile;
import com.routechain.v2.DispatchV2CompatibleCore;
import com.routechain.v2.DispatchV2Request;
import com.routechain.v2.DispatchV2Result;
import com.routechain.v2.TestDispatchV2Factory;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import java.time.Instant;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class DispatchV2ControllerTest {
    MockMvc mockMvc;

    ObjectMapper objectMapper = new ObjectMapper().registerModule(new JavaTimeModule());

    DispatchV2CompatibleCore dispatchCore;

    @BeforeEach
    void setUp() {
        dispatchCore = mock(DispatchV2CompatibleCore.class);
        mockMvc = MockMvcBuilders.standaloneSetup(new DispatchV2Controller(dispatchCore)).build();
    }

    @Test
    void dispatchReturnsCoreResult() throws Exception {
        DispatchV2Request request = TestDispatchV2Factory.requestWithOrdersAndDriver();
        when(dispatchCore.dispatch(any())).thenReturn(DispatchV2Result.fallback(request.traceId()));

        mockMvc.perform(post("/api/dispatch/v2")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.schemaVersion").value("dispatch-v2-result/v1"))
                .andExpect(jsonPath("$.traceId").value(request.traceId()))
                .andExpect(jsonPath("$.fallbackUsed").value(true));
    }

    @Test
    void dispatchFallsBackWhenCoreThrows() throws Exception {
        DispatchV2Request request = TestDispatchV2Factory.requestWithOrdersAndDriver();
        when(dispatchCore.dispatch(any())).thenThrow(new IllegalStateException("core unavailable"));

        mockMvc.perform(post("/api/dispatch/v2")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.traceId").value(request.traceId()))
                .andExpect(jsonPath("$.fallbackUsed").value(true))
                .andExpect(jsonPath("$.degradeReasons[0]").value("dispatch-v2-disabled"));
    }

    @Test
    void dispatchRejectsUnsupportedSchemaVersion() throws Exception {
        DispatchV2Request request = new DispatchV2Request(
                "dispatch-v2-request/v0",
                "trace-invalid-schema",
                java.util.List.of(),
                java.util.List.of(),
                java.util.List.of(),
                WeatherProfile.CLEAR,
                Instant.parse("2026-04-26T10:00:00Z"));

        mockMvc.perform(post("/api/dispatch/v2")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isBadRequest());
    }
}
