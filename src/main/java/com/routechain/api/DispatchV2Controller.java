package com.routechain.api;

import com.routechain.v2.DispatchV2CompatibleCore;
import com.routechain.v2.DispatchV2Request;
import com.routechain.v2.DispatchV2Result;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/dispatch/v2")
public class DispatchV2Controller {
    private final DispatchV2CompatibleCore dispatchCore;

    public DispatchV2Controller(DispatchV2CompatibleCore dispatchCore) {
        this.dispatchCore = dispatchCore;
    }

    @PostMapping
    public ResponseEntity<DispatchV2Result> dispatch(@RequestBody DispatchV2Request request) {
        validate(request);
        try {
            return ResponseEntity.ok(dispatchCore.dispatch(request));
        } catch (RuntimeException exception) {
            return ResponseEntity.ok(DispatchV2Result.fallback(request.traceId()));
        }
    }

    private void validate(DispatchV2Request request) {
        if (request == null) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "dispatch request body is required");
        }
        if (!"dispatch-v2-request/v1".equals(request.schemaVersion())) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "unsupported dispatch request schemaVersion");
        }
        if (request.traceId() == null || request.traceId().isBlank()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "traceId is required");
        }
        if (request.openOrders() == null) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "openOrders is required");
        }
        if (request.availableDrivers() == null) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "availableDrivers is required");
        }
        if (request.regions() == null) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "regions is required");
        }
        if (request.weatherProfile() == null) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "weatherProfile is required");
        }
        if (request.decisionTime() == null) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "decisionTime is required");
        }
    }
}
