package com.routefood.app.driver.model

import org.json.JSONArray
import org.json.JSONObject

data class DriverLatLng(
    val lat: Double,
    val lng: Double
) {
    companion object {
        fun fromJson(json: JSONObject?): DriverLatLng? {
            if (json == null) return null
            return DriverLatLng(json.optDouble("lat"), json.optDouble("lng"))
        }
    }
}

data class DriverRouteStep(
    val index: Int,
    val label: String,
    val type: String,
    val orderId: String,
    val title: String,
    val location: DriverLatLng
) {
    val isPickup: Boolean get() = type.equals("pickup", ignoreCase = true)

    companion object {
        fun fromJson(json: JSONObject): DriverRouteStep {
            return DriverRouteStep(
                index = json.optInt("index"),
                label = json.optString("label", "S${json.optInt("index") + 1}"),
                type = json.optString("type", "step"),
                orderId = json.optString("orderId", json.optString("order_id", "")),
                title = json.optString("title", "Route step"),
                location = DriverLatLng.fromJson(json.optJSONObject("location")) ?: DriverLatLng(10.776, 106.704)
            )
        }
    }
}

data class DriverRoutePlan(
    val schemaVersion: String,
    val summary: String,
    val sequence: List<DriverRouteStep>,
    val distanceMeters: Int,
    val etaSeconds: Int,
    val geometryAvailable: Boolean,
    val geometry: List<DriverLatLng> = emptyList()
) {
    companion object {
        fun fromJson(json: JSONObject?): DriverRoutePlan {
            if (json == null) return fallback()
            val sequenceJson = json.optJSONArray("sequence") ?: JSONArray()
            val steps = buildList {
                for (index in 0 until sequenceJson.length()) {
                    val stepJson = sequenceJson.optJSONObject(index) ?: continue
                    add(DriverRouteStep.fromJson(stepJson))
                }
            }
            return DriverRoutePlan(
                schemaVersion = json.optString("schemaVersion", "mobile-route-plan/v1"),
                summary = json.optString("summary", steps.joinToString(" -> ") { it.label }.ifBlank { "P1 -> D1" }),
                sequence = steps.ifEmpty { fallback().sequence },
                distanceMeters = json.optInt("distanceMeters", 8200),
                etaSeconds = json.optInt("etaSeconds", 1840),
                geometryAvailable = json.optBoolean("geometryAvailable", false),
                geometry = parseGeometry(json)
            )
        }

        private fun parseGeometry(json: JSONObject): List<DriverLatLng> {
            val geometryJson = json.optJSONArray("geometry") ?: json.optJSONArray("polyline") ?: return emptyList()
            return buildList {
                for (index in 0 until geometryJson.length()) {
                    val objectPoint = geometryJson.optJSONObject(index)
                    if (objectPoint != null) {
                        DriverLatLng.fromJson(objectPoint)?.let { add(it) }
                        continue
                    }
                    val arrayPoint = geometryJson.optJSONArray(index) ?: continue
                    if (arrayPoint.length() >= 2) {
                        val first = arrayPoint.optDouble(0)
                        val second = arrayPoint.optDouble(1)
                        if (first in -90.0..90.0 && second in -180.0..180.0) {
                            add(DriverLatLng(first, second))
                        } else {
                            add(DriverLatLng(second, first))
                        }
                    }
                }
            }
        }

        fun fallback() = DriverRoutePlan(
            schemaVersion = "mobile-route-plan/v1",
            summary = "P1 -> P2 -> P3 -> P4 -> D4 -> D2 -> D3 -> D1",
            sequence = listOf(
                DriverRouteStep(0, "P1", "pickup", "O1001", "Pickup O1001 - Com ga Q1", DriverLatLng(10.7741, 106.7038)),
                DriverRouteStep(1, "P2", "pickup", "O1002", "Pickup O1002 - Bun bo Hue Mua", DriverLatLng(10.7767, 106.7065)),
                DriverRouteStep(2, "P3", "pickup", "O1003", "Pickup O1003 - Tra sua May", DriverLatLng(10.7749, 106.7067)),
                DriverRouteStep(3, "P4", "pickup", "O1004", "Pickup O1004 - Banh mi 24h", DriverLatLng(10.7773, 106.7066)),
                DriverRouteStep(4, "D4", "dropoff", "O1004", "Dropoff O1004", DriverLatLng(10.7833, 106.7143)),
                DriverRouteStep(5, "D2", "dropoff", "O1002", "Dropoff O1002", DriverLatLng(10.7940, 106.7203)),
                DriverRouteStep(6, "D3", "dropoff", "O1003", "Dropoff O1003", DriverLatLng(10.7899, 106.7224)),
                DriverRouteStep(7, "D1", "dropoff", "O1001", "Dropoff O1001", DriverLatLng(10.7942, 106.7218))
            ),
            distanceMeters = 9400,
            etaSeconds = 2160,
            geometryAvailable = false,
            geometry = emptyList()
        )
    }
}

data class CoreDecisionSummary(
    val decision: String,
    val reason: String,
    val batchScore: Double?,
    val savingsPercent: Int?,
    val detourMinutes: Int?
) {
    companion object {
        fun fromJson(json: JSONObject?, dispatchMode: String, fallbackUsed: Boolean): CoreDecisionSummary {
            return CoreDecisionSummary(
                decision = json?.optString("decision")?.takeIf { it.isNotBlank() } ?: dispatchMode.ifBlank { "demo_dispatch" },
                reason = json?.optString("reason")?.takeIf { it.isNotBlank() }
                    ?: if (fallbackUsed) "Fallback deterministic route because core result was unavailable." else "Core selected this route from the frozen dispatch snapshot.",
                batchScore = json?.takeIf { it.has("batchScore") }?.optDouble("batchScore"),
                savingsPercent = json?.takeIf { it.has("savingsPercent") }?.optInt("savingsPercent"),
                detourMinutes = json?.takeIf { it.has("detourMinutes") }?.optInt("detourMinutes")
            )
        }
    }
}

data class DriverAssignmentDemo(
    val id: String,
    val assignmentCode: String,
    val driverCode: String,
    val status: String,
    val orderIds: List<String>,
    val currentStepIndex: Int,
    val routePlan: DriverRoutePlan,
    val driverLocationAtAssignment: DriverLatLng,
    val traceId: String,
    val dispatchMode: String,
    val fallbackUsed: Boolean,
    val degradeReasons: List<String>,
    val decisionSummary: CoreDecisionSummary
) {
    val currentStep: DriverRouteStep? get() = routePlan.sequence.getOrNull(currentStepIndex)
    val isCompleted: Boolean get() = status == "completed" || currentStepIndex >= routePlan.sequence.size

    companion object {
        fun fromJson(json: JSONObject): DriverAssignmentDemo {
            val orderIdsJson = json.optJSONArray("order_ids") ?: JSONArray()
            val orders = buildList {
                for (index in 0 until orderIdsJson.length()) add(orderIdsJson.optString(index))
            }
            val degradeJson = json.optJSONArray("degrade_reasons") ?: JSONArray()
            val degrade = buildList {
                for (index in 0 until degradeJson.length()) add(degradeJson.optString(index))
            }
            val dispatchMode = json.optString("dispatch_mode", "demo_dispatch")
            val fallbackUsed = json.optBoolean("fallback_used", false)
            return DriverAssignmentDemo(
                id = json.optString("id"),
                assignmentCode = json.optString("assignment_code", "A-DEMO"),
                driverCode = json.optString("driver_code", "D1"),
                status = json.optString("status", "assigned"),
                orderIds = orders,
                currentStepIndex = json.optInt("current_step_index", 0),
                routePlan = DriverRoutePlan.fromJson(json.optJSONObject("route_plan")),
                driverLocationAtAssignment = DriverLatLng.fromJson(json.optJSONObject("driver_location_at_assignment")) ?: DriverLatLng(10.776, 106.704),
                traceId = json.optString("trace_id", "demo-trace"),
                dispatchMode = dispatchMode,
                fallbackUsed = fallbackUsed,
                degradeReasons = degrade,
                decisionSummary = CoreDecisionSummary.fromJson(json.optJSONObject("decision_summary"), dispatchMode, fallbackUsed)
            )
        }

        fun sample() = DriverAssignmentDemo(
            id = "demo-assignment-local",
            assignmentCode = "A9001",
            driverCode = "D1",
            status = "assigned",
            orderIds = listOf("O1001", "O1002", "O1003", "O1004"),
            currentStepIndex = 0,
            routePlan = DriverRoutePlan.fallback(),
            driverLocationAtAssignment = DriverLatLng(10.776, 106.704),
            traceId = "local-demo-core-trace",
            dispatchMode = "DISPATCH_BATCH",
            fallbackUsed = false,
            degradeReasons = emptyList(),
            decisionSummary = CoreDecisionSummary(
                decision = "DISPATCH_BATCH",
                reason = "Core chose nearby pickups first, then non-sequential dropoffs to reduce zigzag.",
                batchScore = 0.91,
                savingsPercent = 23,
                detourMinutes = 5
            )
        )
    }
}
