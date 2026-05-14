package com.routefood.app.driver

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.routefood.app.core.map.OsrmRouteClient.NavigationInstruction
import com.routefood.app.core.map.routing.CompositeRoutingProvider
import com.routefood.app.core.map.routing.OsrmRoutingProvider
import com.routefood.app.core.map.routing.RoutingProvider
import com.routefood.app.core.supabase.SupabaseRealtimeClient
import com.routefood.app.data.model.GeoPoint
import com.routefood.app.driver.data.DriverDemoRepository
import com.routefood.app.driver.model.DriverAssignmentDemo
import com.routefood.app.driver.model.DriverLatLng
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlin.math.atan2
import kotlin.math.asin
import kotlin.math.cos
import kotlin.math.max
import kotlin.math.min
import kotlin.math.pow
import kotlin.math.sin
import kotlin.math.sqrt

data class DriverDemoUiState(
    val online: Boolean = false,
    val loading: Boolean = false,
    val assignment: DriverAssignmentDemo? = null,
    val error: String? = null,
    val lastUpdatedLabel: String = "Local demo ready",
    val showLocalDemo: Boolean = true,
    val simulationRunning: Boolean = false,
    val simulatedDriverLocation: DriverLatLng? = null,
    val roadGeometry: List<DriverLatLng> = emptyList(),
    val roadGeometryLoading: Boolean = false,
    val roadGeometryLabel: String = "Estimated route",
    val navigationInstructions: List<NavigationInstruction> = emptyList(),
    val activeInstructionIndex: Int = 0,
    val simulatedSpeedKmh: Int = 0,
    val trafficLabel: String = "Normal traffic",
    val remainingDistanceMeters: Int = 0,
    val remainingDurationSeconds: Int = 0,
    val driverHeadingDeg: Double = 0.0,
    val demoReplayMultiplier: Double = 2.0,
    val routeProgressIndex: Int = 0,
    val routeProgressMeters: Double = 0.0,
    val driverProjectedLocation: DriverLatLng? = null,
    val currentLegIndex: Int = 0,
    val currentLegEndMeters: Double = 0.0,
    val completedGeometry: List<DriverLatLng> = emptyList(),
    val remainingGeometry: List<DriverLatLng> = emptyList(),
    val snappedWaypoints: List<DriverSnappedWaypointUi> = emptyList(),
    val snapWarnings: List<String> = emptyList(),
    val maxSnapDistanceMeters: Double = 0.0,
    val cameraMode: NavigationCameraMode = NavigationCameraMode.OVERVIEW,
    val stopWorkflow: DriverStopWorkflow = DriverStopWorkflow.NAVIGATING,
    val waitingSeconds: Int = 0
) {
    val phase: DriverPhase
        get() = when {
            !online -> DriverPhase.Offline
            assignment == null -> DriverPhase.Idle
            assignment.status == "assigned" -> DriverPhase.Offer
            assignment.status == "accepted" || assignment.status == "in_progress" -> DriverPhase.ActiveTrip
            else -> DriverPhase.Idle
        }
}

enum class DriverPhase { Offline, Idle, Offer, ActiveTrip }

enum class NavigationCameraMode { OVERVIEW, FOLLOWING, MANUAL, OFF_ROUTE }

enum class DriverStopWorkflow { NAVIGATING, PICKUP_ARRIVED, PICKUP_WAITING, DROPOFF_ARRIVED, PROOF_REQUIRED, CUSTOMER_UNREACHABLE }

data class DriverSnappedWaypointUi(
    val label: String,
    val raw: DriverLatLng,
    val snapped: DriverLatLng,
    val distanceMeters: Double,
    val roadName: String
)

class DriverDemoViewModel(
    private val repository: DriverDemoRepository = DriverDemoRepository(),
    private val routingProvider: RoutingProvider = CompositeRoutingProvider(
        OsrmRoutingProvider(),
        OsrmRoutingProvider(com.routefood.app.BuildConfig.PUBLIC_OSRM_BASE_URL)
    )
) : ViewModel() {
    private val _state = MutableStateFlow(DriverDemoUiState())
    val state: StateFlow<DriverDemoUiState> = _state.asStateFlow()
    private var pollJob: Job? = null
    private var simulationJob: Job? = null
    private var simulationGeometryIndex: Int = 0
    private var simulationProgressMeters: Double = 0.0
    private var routeLegEndMeters: List<Double> = emptyList()
    private var routeLegEndIndices: List<Int> = emptyList()
    private var routeBaseStepIndex: Int = 0
    private var trafficHoldTicks: Int = 0
    private var simulatedAlongLocation: DriverLatLng? = null
    private var realtimeRefreshJob: Job? = null
    private val realtimeClient = SupabaseRealtimeClient(
        scope = viewModelScope,
        onStatus = { label -> _state.update { it.copy(lastUpdatedLabel = label) } },
        onDatabaseChange = { table -> scheduleRealtimeRefresh(table) }
    )

    fun goOnline() {
        _state.update { it.copy(online = true, loading = true, error = null) }
        startPolling()
    }

    fun goOffline() {
        pollJob?.cancel()
        realtimeClient.disconnect()
        realtimeRefreshJob?.cancel()
        simulationJob?.cancel()
        resetNavigationSimulation()
        _state.update { it.copy(online = false, loading = false, assignment = null, error = null, lastUpdatedLabel = "Offline", simulationRunning = false, simulatedDriverLocation = null, roadGeometry = emptyList(), roadGeometryLoading = false, roadGeometryLabel = "Estimated route", navigationInstructions = emptyList(), simulatedSpeedKmh = 0, trafficLabel = "Normal traffic", driverHeadingDeg = 0.0, routeProgressIndex = 0, routeProgressMeters = 0.0, driverProjectedLocation = null, currentLegIndex = 0, currentLegEndMeters = 0.0, completedGeometry = emptyList(), remainingGeometry = emptyList(), snappedWaypoints = emptyList(), snapWarnings = emptyList(), maxSnapDistanceMeters = 0.0, cameraMode = NavigationCameraMode.OVERVIEW, stopWorkflow = DriverStopWorkflow.NAVIGATING, waitingSeconds = 0) }
    }

    fun loadLocalCoreDemo() {
        _state.update {
            it.copy(
                online = true,
                loading = false,
                assignment = DriverAssignmentDemo.sample(),
                error = null,
                lastUpdatedLabel = "Local IntelligentRouteX demo",
                simulationRunning = false,
                simulatedDriverLocation = DriverAssignmentDemo.sample().driverLocationAtAssignment,
                simulatedSpeedKmh = 0,
                trafficLabel = "Normal traffic",
                stopWorkflow = DriverStopWorkflow.NAVIGATING,
                waitingSeconds = 0
            )
        }
        refreshRoadGeometry()
    }

    fun acceptAssignment() {
        val assignment = _state.value.assignment ?: return
        if (assignment.id == DriverAssignmentDemo.sample().id) {
            resetNavigationSimulation()
            _state.update {
                it.copy(
                    assignment = assignment.copy(status = "accepted"),
                    simulatedDriverLocation = assignment.driverLocationAtAssignment,
                    lastUpdatedLabel = "Accepted ${assignment.assignmentCode}",
                    stopWorkflow = DriverStopWorkflow.NAVIGATING,
                    waitingSeconds = 0
                )
            }
            refreshRoadGeometry()
            return
        }
        viewModelScope.launch {
            _state.update { it.copy(loading = true, error = null) }
            repository.acceptAssignment(assignment.id)
                .onSuccess {
                    resetNavigationSimulation()
                    _state.update {
                        it.copy(
                            loading = false,
                            assignment = assignment.copy(status = "accepted"),
                            simulatedDriverLocation = assignment.driverLocationAtAssignment,
                            lastUpdatedLabel = "Accepted ${assignment.assignmentCode}",
                            stopWorkflow = DriverStopWorkflow.NAVIGATING,
                            waitingSeconds = 0
                        )
                    }
                    refreshRoadGeometry()
                }
                .onFailure { error -> _state.update { it.copy(loading = false, error = error.message) } }
        }
    }

    fun rejectAssignment() {
        val assignment = _state.value.assignment ?: return
        viewModelScope.launch {
            _state.update { it.copy(loading = true, error = null) }
            repository.rejectAssignment(assignment.id)
                .onSuccess {
                    _state.update { it.copy(loading = false, assignment = null, lastUpdatedLabel = "Rejected ${assignment.assignmentCode}") }
                }
                .onFailure { error -> _state.update { it.copy(loading = false, error = error.message) } }
        }
    }

    fun completeCurrentStep() {
        val assignment = _state.value.assignment ?: return
        if (assignment.id == DriverAssignmentDemo.sample().id) {
            advanceLocalStep()
            return
        }
        viewModelScope.launch {
            _state.update { it.copy(loading = true, error = null) }
            repository.advanceAssignment(assignment.id)
                .onSuccess {
                    val nextIndex = assignment.currentStepIndex + 1
                    val completed = nextIndex >= assignment.routePlan.sequence.size
                    _state.update {
                        it.copy(
                            loading = false,
                            assignment = assignment.copy(
                                status = if (completed) "completed" else "in_progress",
                                currentStepIndex = nextIndex.coerceAtMost(assignment.routePlan.sequence.size)
                            ),
                            lastUpdatedLabel = if (completed) "Completed ${assignment.assignmentCode}" else "Advanced to step ${nextIndex + 1}"
                        )
                    }
                }
                .onFailure { error -> _state.update { it.copy(loading = false, error = error.message) } }
        }
    }

    fun refreshNow() {
        if (!_state.value.online) return
        viewModelScope.launch { pollOnce() }
    }

    fun toggleDrivingSimulation() {
        val assignment = _state.value.assignment ?: return
        if (_state.value.stopWorkflow != DriverStopWorkflow.NAVIGATING) {
            _state.update { it.copy(lastUpdatedLabel = "Confirm current stop before continuing") }
            return
        }
        if (assignment.status == "assigned") {
            _state.update { it.copy(assignment = assignment.copy(status = "accepted"), simulatedDriverLocation = assignment.driverLocationAtAssignment) }
        }
        if (_state.value.simulationRunning) {
            simulationJob?.cancel()
            _state.update { it.copy(simulationRunning = false, lastUpdatedLabel = "Simulation paused") }
            return
        }
        alignSimulationIndexToCurrentLocation()
        _state.update { it.copy(simulationRunning = true, error = null, lastUpdatedLabel = "Navigation simulation running", cameraMode = NavigationCameraMode.FOLLOWING) }
        simulationJob = viewModelScope.launch {
            while (_state.value.simulationRunning) {
                delay(SIMULATION_TICK_MS)
                advanceAlongRoadGeometry()
                if (_state.value.assignment?.isCompleted == true) {
                    _state.update { it.copy(simulationRunning = false, simulatedSpeedKmh = 0, trafficLabel = "Route completed", lastUpdatedLabel = "Route completed") }
                    break
                }
            }
        }
    }

    fun markOrderNotReady() {
        _state.update {
            it.copy(
                simulationRunning = false,
                simulatedSpeedKmh = 0,
                stopWorkflow = DriverStopWorkflow.PICKUP_WAITING,
                waitingSeconds = 0,
                trafficLabel = "Restaurant delay",
                lastUpdatedLabel = "Order not ready - waiting at merchant"
            )
        }
    }

    fun continueWaiting() {
        _state.update {
            val nextSeconds = it.waitingSeconds + 180
            it.copy(
                waitingSeconds = nextSeconds,
                lastUpdatedLabel = "Waiting ${nextSeconds / 60} min at merchant"
            )
        }
    }

    fun confirmPickedUp() {
        if (_state.value.assignment?.currentStep?.isPickup != true) return
        advanceLocalStep()
    }

    fun requestProof() {
        _state.update {
            it.copy(
                simulationRunning = false,
                simulatedSpeedKmh = 0,
                stopWorkflow = DriverStopWorkflow.PROOF_REQUIRED,
                lastUpdatedLabel = "Proof required before completing delivery"
            )
        }
    }

    fun markCustomerUnreachable() {
        _state.update {
            it.copy(
                simulationRunning = false,
                simulatedSpeedKmh = 0,
                stopWorkflow = DriverStopWorkflow.CUSTOMER_UNREACHABLE,
                waitingSeconds = 0,
                lastUpdatedLabel = "Customer unreachable - start contact timer"
            )
        }
    }

    fun confirmDelivered() {
        if (_state.value.assignment?.currentStep?.isPickup == true) return
        advanceLocalStep()
    }

    private fun advanceLocalStep() {
        val state = _state.value
        val assignment = state.assignment ?: return
        val currentStep = assignment.currentStep ?: run {
            _state.update { it.copy(simulationRunning = false) }
            return
        }
        val currentRoadPoint = state.driverProjectedLocation
            ?: state.simulatedDriverLocation
            ?: simulatedAlongLocation
            ?: assignment.driverLocationAtAssignment
        val nextIndex = assignment.currentStepIndex + 1
        val completed = nextIndex >= assignment.routePlan.sequence.size
        val nextLegOffset = (nextIndex - routeBaseStepIndex).coerceAtLeast(0)
        val remainingMeters = if (completed) 0 else remainingDistanceMeters(state.roadGeometry, simulationGeometryIndex).toInt()
        _state.update {
            it.copy(
                loading = false,
                assignment = assignment.copy(
                    status = if (completed) "completed" else "in_progress",
                    currentStepIndex = nextIndex.coerceAtMost(assignment.routePlan.sequence.size)
                ),
                simulatedDriverLocation = currentRoadPoint,
                driverProjectedLocation = currentRoadPoint,
                simulationRunning = false,
                simulatedSpeedKmh = 0,
                remainingDistanceMeters = remainingMeters,
                remainingDurationSeconds = if (completed) 0 else max(30, it.remainingDurationSeconds),
                trafficLabel = if (completed) "Route completed" else "Ready for ${assignment.routePlan.sequence.getOrNull(nextIndex)?.label ?: "next stop"}",
                currentLegIndex = nextLegOffset,
                currentLegEndMeters = routeLegEndMeters.getOrNull(nextLegOffset) ?: it.currentLegEndMeters,
                stopWorkflow = DriverStopWorkflow.NAVIGATING,
                waitingSeconds = 0,
                lastUpdatedLabel = if (completed) "Arrived final stop" else "${currentStep.label} confirmed • ready to navigate to ${assignment.routePlan.sequence.getOrNull(nextIndex)?.label ?: "next stop"}"
            )
        }
        if (!completed) refreshRoadGeometry()
    }

    private fun advanceAlongRoadGeometry() {
        val state = _state.value
        val assignment = state.assignment ?: return
        val geometry = state.roadGeometry
        if (state.stopWorkflow != DriverStopWorkflow.NAVIGATING) {
            _state.update { it.copy(simulationRunning = false, simulatedSpeedKmh = 0) }
            return
        }
        if (geometry.size < 2) {
            refreshRoadGeometry()
            _state.update { it.copy(simulationRunning = false, simulatedSpeedKmh = 0, lastUpdatedLabel = "Preparing road route") }
            return
        }
        val currentStep = assignment.currentStep ?: run {
            _state.update { it.copy(simulationRunning = false, simulatedSpeedKmh = 0) }
            return
        }
        val speedKmh = realisticSpeedKmh(simulationGeometryIndex)
        if (speedKmh == 0) {
            _state.update { it.copy(simulatedSpeedKmh = 0, trafficLabel = trafficLabelForIndex(simulationGeometryIndex), lastUpdatedLabel = "Waiting: ${trafficLabelForIndex(simulationGeometryIndex)}") }
            return
        }
        val previousLocation = state.simulatedDriverLocation ?: simulatedAlongLocation ?: geometry[simulationGeometryIndex]
        val location = advanceAlongPolyline(geometry, speedKmh, state.demoReplayMultiplier)
        val heading = smoothHeading(state.driverHeadingDeg, headingForLocation(previousLocation, location, geometry, simulationGeometryIndex))
        val routeProgress = splitGeometryAtProgress(geometry, simulationGeometryIndex, location)
        val remainingDistance = remainingDistanceMeters(geometry, simulationGeometryIndex)
        val activeInstruction = activeInstructionIndex(location, state.navigationInstructions, remainingDistance)
        val remainingDuration = max(30, (remainingDistance / max(1.0, speedKmh / 3.6)).toInt())
        val currentLegEndMeters = routeLegEndMeters.getOrNull(assignment.currentStepIndex - routeBaseStepIndex)
            ?: routeDistanceMeters(geometry)
        val currentLegEndIndex = routeLegEndIndices.getOrNull(assignment.currentStepIndex - routeBaseStepIndex)
            ?: geometry.lastIndex
        val arrivedCurrentStop = simulationProgressMeters >= currentLegEndMeters - ARRIVAL_THRESHOLD_METERS ||
            simulationGeometryIndex >= currentLegEndIndex.coerceAtMost(geometry.lastIndex)
        if (arrivedCurrentStop) {
            val arrivalLocation = geometry.getOrNull(currentLegEndIndex.coerceIn(0, geometry.lastIndex)) ?: location
            simulationGeometryIndex = max(simulationGeometryIndex, currentLegEndIndex.coerceIn(0, geometry.lastIndex))
            simulationProgressMeters = max(simulationProgressMeters, currentLegEndMeters)
            simulatedAlongLocation = arrivalLocation
            val arrivedProgress = splitGeometryAtProgress(geometry, simulationGeometryIndex, arrivalLocation)
            _state.update {
                it.copy(
                    simulatedDriverLocation = arrivalLocation,
                    driverProjectedLocation = arrivalLocation,
                    routeProgressIndex = simulationGeometryIndex,
                    routeProgressMeters = simulationProgressMeters,
                    currentLegIndex = assignment.currentStepIndex - routeBaseStepIndex,
                    currentLegEndMeters = currentLegEndMeters,
                    completedGeometry = arrivedProgress.first,
                    remainingGeometry = arrivedProgress.second,
                    simulationRunning = false,
                    simulatedSpeedKmh = 0,
                    trafficLabel = "Arrived ${currentStep.label}",
                    driverHeadingDeg = heading,
                    activeInstructionIndex = activeInstruction,
                    remainingDistanceMeters = 0,
                    remainingDurationSeconds = 0,
                    stopWorkflow = if (currentStep.isPickup) DriverStopWorkflow.PICKUP_ARRIVED else DriverStopWorkflow.DROPOFF_ARRIVED,
                    waitingSeconds = 0,
                    lastUpdatedLabel = "Arrived ${currentStep.label}"
                )
            }
            return
        }
        _state.update {
            it.copy(
                simulatedDriverLocation = location,
                driverProjectedLocation = location,
                routeProgressIndex = simulationGeometryIndex,
                routeProgressMeters = simulationProgressMeters,
                currentLegIndex = assignment.currentStepIndex - routeBaseStepIndex,
                currentLegEndMeters = currentLegEndMeters,
                completedGeometry = routeProgress.first,
                remainingGeometry = routeProgress.second,
                simulatedSpeedKmh = speedKmh,
                trafficLabel = trafficLabelForSpeed(speedKmh),
                driverHeadingDeg = heading,
                activeInstructionIndex = activeInstruction,
                remainingDistanceMeters = remainingDistance.toInt(),
                remainingDurationSeconds = remainingDuration,
                lastUpdatedLabel = "${speedKmh} km/h • ${trafficLabelForSpeed(speedKmh)}"
            )
        }
    }

    private fun realisticSpeedKmh(index: Int): Int {
        if (trafficHoldTicks > 0) {
            trafficHoldTicks--
            return 0
        }
        if (index > 0 && index % 37 == 0) {
            trafficHoldTicks = 3
            return 0
        }
        if (index > 0 && index % 53 == 0) {
            trafficHoldTicks = 5
            return 0
        }
        val wave = sin(index / 5.0) * 10.0 + sin(index / 13.0) * 7.0
        val congestionPenalty = if ((index / 23) % 3 == 1) 12 else 0
        return (40 + wave - congestionPenalty).toInt().coerceIn(8, 60)
    }

    private fun trafficLabelForIndex(index: Int): String = if (index % 53 == 0) "Heavy traffic" else "Traffic light"

    private fun trafficLabelForSpeed(speedKmh: Int): String = when {
        speedKmh <= 12 -> "Crawling traffic"
        speedKmh <= 28 -> "Busy street"
        speedKmh <= 45 -> "Normal traffic"
        else -> "Clear road"
    }

    private fun alignSimulationIndexToCurrentLocation() {
        val location = _state.value.driverProjectedLocation ?: _state.value.simulatedDriverLocation ?: return
        val geometry = _state.value.roadGeometry
        if (geometry.isEmpty()) return
        val nearestIndex = geometry.indices.minByOrNull { index -> distanceMeters(location, geometry[index]) } ?: 0
        simulationGeometryIndex = max(simulationGeometryIndex, nearestIndex)
        simulationProgressMeters = max(simulationProgressMeters, cumulativeDistanceUntil(geometry, simulationGeometryIndex))
        simulatedAlongLocation = location
    }

    private fun resetNavigationSimulation() {
        simulationGeometryIndex = 0
        simulationProgressMeters = 0.0
        routeLegEndMeters = emptyList()
        routeLegEndIndices = emptyList()
        routeBaseStepIndex = 0
        trafficHoldTicks = 0
        simulatedAlongLocation = null
    }

    private fun advanceAlongPolyline(geometry: List<DriverLatLng>, speedKmh: Int, replayMultiplier: Double): DriverLatLng {
        var current = simulatedAlongLocation ?: geometry[simulationGeometryIndex]
        var budgetMeters = max(0.6, speedKmh / 3.6 * (SIMULATION_TICK_MS / 1000.0) * replayMultiplier)
            .coerceAtMost(MAX_ADVANCE_METERS_PER_TICK)
        while (budgetMeters > 0.0 && simulationGeometryIndex < geometry.lastIndex) {
            val next = geometry[simulationGeometryIndex + 1]
            val segmentMeters = distanceMeters(current, next)
            if (segmentMeters <= budgetMeters || segmentMeters < 0.5) {
                current = next
                simulationGeometryIndex++
                simulationProgressMeters += segmentMeters
                budgetMeters -= segmentMeters
            } else {
                val ratio = budgetMeters / segmentMeters
                current = DriverLatLng(
                    current.lat + (next.lat - current.lat) * ratio,
                    current.lng + (next.lng - current.lng) * ratio
                )
                simulationProgressMeters += budgetMeters
                budgetMeters = 0.0
            }
        }
        simulatedAlongLocation = current
        return current
    }

    private fun activeInstructionIndex(location: DriverLatLng, instructions: List<NavigationInstruction>, remainingDistanceMeters: Double): Int {
        if (instructions.isEmpty()) return 0
        val candidateIndices = instructions.indices.filter { index ->
            val type = instructions[index].type.lowercase()
            remainingDistanceMeters <= 180.0 || (type != "arrive" && type != "destination")
        }.ifEmpty { instructions.indices.toList() }
        return candidateIndices.minByOrNull { index ->
            val instruction = instructions[index]
            distanceMeters(location, DriverLatLng(instruction.latitude, instruction.longitude))
        } ?: 0
    }

    private fun remainingDistanceMeters(geometry: List<DriverLatLng>, startIndex: Int): Double {
        var sum = 0.0
        for (index in startIndex until geometry.lastIndex) {
            sum += distanceMeters(geometry[index], geometry[index + 1])
        }
        return sum
    }

    private fun routeDistanceMeters(geometry: List<DriverLatLng>): Double = cumulativeDistanceUntil(geometry, geometry.lastIndex)

    private fun cumulativeDistanceUntil(geometry: List<DriverLatLng>, endIndex: Int): Double {
        if (geometry.size < 2) return 0.0
        var sum = 0.0
        val safeEnd = endIndex.coerceIn(0, geometry.lastIndex)
        for (index in 0 until safeEnd) {
            sum += distanceMeters(geometry[index], geometry[index + 1])
        }
        return sum
    }

    private fun computeLegBoundaries(
        geometry: List<DriverLatLng>,
        waypointCount: Int,
        legDistances: List<Double> = emptyList()
    ): Pair<List<Int>, List<Double>> {
        if (geometry.isEmpty() || waypointCount <= 1) return emptyList<Int>() to emptyList()
        val legCount = waypointCount - 1
        if (legDistances.size == legCount && legDistances.all { it > 0.0 }) {
            val endMeters = legDistances.runningFold(0.0) { total, legDistance -> total + legDistance }.drop(1)
            val endIndices = endMeters.map { targetMeters -> geometryIndexAtDistance(geometry, targetMeters) }
            return endIndices to endMeters
        }
        val endIndices = (1..legCount).map { leg ->
            ((geometry.lastIndex.toDouble() * leg) / legCount).toInt().coerceIn(0, geometry.lastIndex)
        }
        val endMeters = endIndices.map { index -> cumulativeDistanceUntil(geometry, index) }
        return endIndices to endMeters
    }

    private fun geometryIndexAtDistance(geometry: List<DriverLatLng>, targetMeters: Double): Int {
        if (geometry.size < 2) return 0
        var traveled = 0.0
        for (index in 0 until geometry.lastIndex) {
            traveled += distanceMeters(geometry[index], geometry[index + 1])
            if (traveled >= targetMeters) return index + 1
        }
        return geometry.lastIndex
    }

    private fun splitGeometryAtProgress(
        geometry: List<DriverLatLng>,
        progressIndex: Int,
        projectedLocation: DriverLatLng
    ): Pair<List<DriverLatLng>, List<DriverLatLng>> {
        if (geometry.size < 2) return emptyList<DriverLatLng>() to emptyList()
        val safeIndex = progressIndex.coerceIn(0, geometry.lastIndex)
        val completed = (geometry.take(safeIndex + 1) + projectedLocation).distinctConsecutive()
        val remainingStart = (safeIndex + 1).coerceAtMost(geometry.size)
        val remaining = (listOf(projectedLocation) + geometry.drop(remainingStart)).distinctConsecutive()
        return completed to remaining
    }

    private fun List<DriverLatLng>.distinctConsecutive(): List<DriverLatLng> {
        if (isEmpty()) return this
        val result = mutableListOf<DriverLatLng>()
        forEach { point ->
            val previous = result.lastOrNull()
            if (previous == null || distanceMeters(previous, point) > 0.25) result.add(point)
        }
        return result
    }

    private fun headingForLocation(
        previousLocation: DriverLatLng,
        currentLocation: DriverLatLng,
        geometry: List<DriverLatLng>,
        currentIndex: Int
    ): Double {
        if (distanceMeters(previousLocation, currentLocation) > 1.0) {
            return bearingDegrees(previousLocation, currentLocation)
        }
        val next = geometry.drop((currentIndex + 1).coerceAtMost(geometry.lastIndex)).firstOrNull {
            distanceMeters(currentLocation, it) > 5.0
        }
        return next?.let { bearingDegrees(currentLocation, it) } ?: _state.value.driverHeadingDeg
    }

    private fun smoothHeading(current: Double, target: Double): Double {
        val delta = ((((target - current) % 360.0) + 540.0) % 360.0) - 180.0
        return (current + delta * 0.35 + 360.0) % 360.0
    }

    private fun distanceMeters(a: DriverLatLng, b: DriverLatLng): Double {
        val radius = 6_371_000.0
        val dLat = Math.toRadians(b.lat - a.lat)
        val dLng = Math.toRadians(b.lng - a.lng)
        val lat1 = Math.toRadians(a.lat)
        val lat2 = Math.toRadians(b.lat)
        val h = sin(dLat / 2).pow(2.0) + cos(lat1) * cos(lat2) * sin(dLng / 2).pow(2.0)
        return 2 * radius * asin(min(1.0, sqrt(h)))
    }

    private fun bearingDegrees(from: DriverLatLng, to: DriverLatLng): Double {
        val fromLat = Math.toRadians(from.lat)
        val toLat = Math.toRadians(to.lat)
        val deltaLng = Math.toRadians(to.lng - from.lng)
        val y = sin(deltaLng) * cos(toLat)
        val x = cos(fromLat) * sin(toLat) - sin(fromLat) * cos(toLat) * cos(deltaLng)
        return (Math.toDegrees(atan2(y, x)) + 360.0) % 360.0
    }

    private fun startPolling() {
        pollJob?.cancel()
        pollJob = viewModelScope.launch {
            pollOnce()
        }
        realtimeClient.connectDemoRun(
            demoRunId = DriverDemoRepository.DEFAULT_DEMO_RUN_ID,
            tables = listOf("assignments", "orders", "drivers")
        )
    }

    private fun scheduleRealtimeRefresh(table: String) {
        realtimeRefreshJob?.cancel()
        realtimeRefreshJob = viewModelScope.launch {
            delay(200)
            pollOnce(silent = true, source = table)
        }
    }

    private suspend fun pollOnce(silent: Boolean = false, source: String = "Supabase") {
        if (!silent) _state.update { it.copy(loading = true, error = null) }
        repository.fetchActiveAssignment()
            .onSuccess { assignment ->
                _state.update {
                    val current = it.assignment
                    val resolvedAssignment = when {
                        assignment == null -> current?.takeIf { existing -> existing.id == DriverAssignmentDemo.sample().id }
                        current != null && current.id == assignment.id && current.status in ACTIVE_STATUSES && assignment.status == "assigned" -> current
                        current != null && current.id == DriverAssignmentDemo.sample().id && current.status in ACTIVE_STATUSES -> current
                        else -> assignment
                    }
                    it.copy(
                        loading = false,
                        assignment = resolvedAssignment,
                        error = null,
                        lastUpdatedLabel = if (resolvedAssignment == null) {
                            "Waiting for IntelligentRouteX assignment"
                        } else if (resolvedAssignment === current && current.status in ACTIVE_STATUSES) {
                            "Navigation active ${current.assignmentCode}"
                        } else {
                            "Realtime $source ${resolvedAssignment.assignmentCode}"
                        }
                    )
                }
            }
            .onFailure { error ->
                _state.update {
                    it.copy(
                        loading = false,
                        error = error.message,
                        assignment = it.assignment ?: DriverAssignmentDemo.sample(),
                        lastUpdatedLabel = "Using local fallback demo"
                    )
                }
                refreshRoadGeometry()
            }
    }

    private fun refreshRoadGeometry() {
        val assignment = _state.value.assignment ?: return
        val remainingSteps = assignment.routePlan.sequence.drop(assignment.currentStepIndex)
        if (remainingSteps.isEmpty()) {
            _state.update { it.copy(roadGeometry = emptyList(), roadGeometryLoading = false, roadGeometryLabel = "Route completed") }
            return
        }
        val driverPoint = _state.value.driverProjectedLocation
            ?: _state.value.simulatedDriverLocation
            ?: assignment.driverLocationAtAssignment
        val currentStep = remainingSteps.first()
        val waypointLabels = buildList {
            add("DR")
            add(currentStep.label)
        }
        val currentLegWaypoints = buildList {
            add(GeoPoint(driverPoint.lat, driverPoint.lng))
            add(GeoPoint(currentStep.location.lat, currentStep.location.lng))
        }
        viewModelScope.launch(Dispatchers.IO) {
            _state.update {
                it.copy(
                    simulationRunning = false,
                    simulatedSpeedKmh = 0,
                    roadGeometry = emptyList(),
                    completedGeometry = emptyList(),
                    remainingGeometry = emptyList(),
                    roadGeometryLoading = true,
                    roadGeometryLabel = "Fetching current leg to ${currentStep.label}"
                )
            }
            runCatching { routingProvider.routeFixedOrder(currentLegWaypoints) }
                .onSuccess { result ->
                    val points = result.coordinates
                    val geometry = points.map { point -> DriverLatLng(point.latitude(), point.longitude()) }
                    val initialProjected = geometry.firstOrNull() ?: driverPoint
                    routeBaseStepIndex = assignment.currentStepIndex
                    val legBoundaries = computeLegBoundaries(geometry, currentLegWaypoints.size, result.legDistanceMeters)
                    routeLegEndIndices = legBoundaries.first
                    routeLegEndMeters = legBoundaries.second
                    simulationGeometryIndex = 0
                    simulationProgressMeters = 0.0
                    simulatedAlongLocation = initialProjected
                    val routeProgress = if (geometry.size >= 2) splitGeometryAtProgress(geometry, 0, initialProjected) else emptyList<DriverLatLng>() to emptyList()
                    val remainingMeters = result.distanceMeters.toInt()
                    val remainingSeconds = result.durationSeconds.toInt()
                    val qualityLabel = "${result.provider} • snap ${result.quality.snapMaxDistanceMeters.toInt()}m"
                    val snapped = result.snappedWaypoints.mapIndexed { index, waypoint ->
                        DriverSnappedWaypointUi(
                            label = waypointLabels.getOrElse(index) { "W$index" },
                            raw = DriverLatLng(waypoint.raw.latitude(), waypoint.raw.longitude()),
                            snapped = DriverLatLng(waypoint.snapped.latitude(), waypoint.snapped.longitude()),
                            distanceMeters = waypoint.distanceMeters,
                            roadName = waypoint.roadName
                        )
                    }
                    _state.update {
                        it.copy(
                            roadGeometry = geometry,
                            simulatedDriverLocation = initialProjected,
                            driverProjectedLocation = initialProjected,
                            routeProgressIndex = 0,
                            routeProgressMeters = 0.0,
                            currentLegIndex = 0,
                            currentLegEndMeters = routeLegEndMeters.firstOrNull() ?: remainingMeters.toDouble(),
                            completedGeometry = routeProgress.first,
                            remainingGeometry = routeProgress.second,
                            snappedWaypoints = snapped,
                            snapWarnings = result.quality.warnings,
                            maxSnapDistanceMeters = result.quality.snapMaxDistanceMeters,
                            navigationInstructions = result.instructions,
                            activeInstructionIndex = 0,
                            remainingDistanceMeters = remainingMeters,
                            remainingDurationSeconds = remainingSeconds,
                            roadGeometryLoading = false,
                            roadGeometryLabel = if (result.instructions.isEmpty()) "Leg ${currentStep.label} • $qualityLabel" else "Turn-by-turn to ${currentStep.label} • $qualityLabel",
                            cameraMode = NavigationCameraMode.OVERVIEW
                        )
                    }
                }
                .onFailure {
                    _state.update {
                        it.copy(
                            roadGeometryLoading = false,
                            roadGeometryLabel = if (it.roadGeometry.size >= 2) {
                                "Keeping last road route - OSRM refreshing"
                            } else {
                                "No road geometry - OSRM unavailable"
                            }
                        )
                    }
                }
        }
    }

    companion object {
        private const val SIMULATION_TICK_MS = 250L
        private const val MAX_ADVANCE_METERS_PER_TICK = 8.0
        private const val ARRIVAL_THRESHOLD_METERS = 10.0
        private val ACTIVE_STATUSES = setOf("accepted", "in_progress")
    }

    override fun onCleared() {
        pollJob?.cancel()
        realtimeRefreshJob?.cancel()
        realtimeClient.disconnect()
        super.onCleared()
    }
}
