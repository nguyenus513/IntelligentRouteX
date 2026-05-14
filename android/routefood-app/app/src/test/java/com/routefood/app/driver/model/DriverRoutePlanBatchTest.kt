package com.routefood.app.driver.model

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class DriverRoutePlanBatchTest {
    @Test
    fun parsesLargeBatchAssignmentForDriverOfferAndStopWorkflow() {
        val assignment = DriverAssignmentDemo.fromJson(largeBatchAssignmentJson())

        assertEquals("DISPATCH_LARGE_WAVE_CORE", assignment.dispatchMode)
        assertFalse(assignment.fallbackUsed)
        assertEquals(6, assignment.orderIds.size)
        assertEquals(12, assignment.routePlan.sequence.size)
        assertEquals("P1 -> P2 -> P3 -> P4 -> P5 -> P6 -> D6 -> D5 -> D4 -> D3 -> D2 -> D1", assignment.routePlan.summary)
        assertEquals("P1", assignment.currentStep?.label)
        assertTrue(assignment.routePlan.sequence.take(6).all { it.isPickup })
        assertTrue(assignment.routePlan.sequence.drop(6).all { !it.isPickup })
        assertTrue(pickupBeforeDropoff(assignment.routePlan.sequence, assignment.orderIds))
    }

    private fun pickupBeforeDropoff(sequence: List<DriverRouteStep>, orderIds: List<String>): Boolean {
        return orderIds.all { orderId ->
            val pickup = sequence.indexOfFirst { it.orderId == orderId && it.isPickup }
            val dropoff = sequence.indexOfFirst { it.orderId == orderId && !it.isPickup }
            pickup >= 0 && dropoff >= 0 && pickup < dropoff
        }
    }

    private fun largeBatchAssignmentJson(): JSONObject {
        val orderIds = JSONArray()
        val sequence = JSONArray()
        for (index in 1..6) {
            orderIds.put("O10$index")
            sequence.put(step(index - 1, "P$index", "pickup", "O10$index"))
        }
        for (index in 6 downTo 1) {
            sequence.put(step(12 - index, "D$index", "dropoff", "O10$index"))
        }
        return JSONObject()
            .put("id", "assignment-large-1")
            .put("assignment_code", "LW1")
            .put("driver_code", "D_REAL")
            .put("status", "assigned")
            .put("order_ids", orderIds)
            .put("current_step_index", 0)
            .put("trace_id", "demo-large-wave-test")
            .put("dispatch_mode", "DISPATCH_LARGE_WAVE_CORE")
            .put("fallback_used", false)
            .put("driver_location_at_assignment", JSONObject().put("lat", 10.776).put("lng", 106.704))
            .put("decision_summary", JSONObject().put("decision", "DISPATCH_LARGE_WAVE_CORE").put("reason", "Core large-wave batch"))
            .put("route_plan", JSONObject()
                .put("schemaVersion", "mobile-route-plan/v1")
                .put("summary", "P1 -> P2 -> P3 -> P4 -> P5 -> P6 -> D6 -> D5 -> D4 -> D3 -> D2 -> D1")
                .put("sequence", sequence)
                .put("distanceMeters", 11800)
                .put("etaSeconds", 3600)
                .put("geometryAvailable", false))
    }

    private fun step(index: Int, label: String, type: String, orderId: String): JSONObject {
        return JSONObject()
            .put("index", index)
            .put("label", label)
            .put("type", type)
            .put("orderId", orderId)
            .put("title", "$label $orderId")
            .put("location", JSONObject().put("lat", 10.77 + index * 0.001).put("lng", 106.70 + index * 0.001))
    }
}
