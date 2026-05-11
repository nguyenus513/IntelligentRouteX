package com.routefood.app.driver

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.routefood.app.core.map.OsrmRouteClient.NavigationInstruction
import com.routefood.app.core.map.routing.CompositeRoutingProvider
import com.routefood.app.core.map.routing.OsrmRoutingProvider
import com.routefood.app.core.map.routing.RoutingProvider
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
    val demoReplayMultiplier: Double = 10.0,
    val routeProgressIndex: Int = 0,
    val driverProjectedLocation: DriverLatLng? = null,
    val completedGeometry: List<DriverLatLng> = emptyList(),
    val remainingGeometry: List<DriverLatLng> = emptyList(),
    val snappedWaypoints: List<DriverSnappedWaypointUi> = emptyList(),
    val snapWarnings: List<String> = emptyList(),
    val maxSnapDistanceMeters: Double = 0.0,
    val cameraMode: NavigationCameraMode = NavigationCameraMode.OVERVIEW
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
    private var trafficHoldTicks: Int = 0
    private var simulatedAlongLocation: DriverLatLng? = null

    fun goOnline() {
        _state.update { it.copy(online = true, loading = true, error = null) }
        startPolling()
    }

    fun goOffline() {
        pollJob?.cancel()
        simulationJob?.cancel()
        resetNavigationSimulation()
        _state.update { it.copy(online = false, loading = false, assignment = null, error = null, lastUpdatedLabel = "Offline", simulationRunning = false, simulatedDriverLocation = null, roadGeometry = emptyList(), roadGeometryLoading = false, roadGeometryLabel = "Estimated route", navigationInstructions = emptyList(), simulatedSpeedKmh = 0, trafficLabel = "Normal traffic", driverHeadingDeg = 0.0, routeProgressIndex = 0, driverProjectedLocation = null, completedGeometry = emptyList(), remainingGeometry = emptyList(), snappedWaypoints = emptyList(), snapWarnings = emptyList(), maxSnapDistanceMeters = 0.0, cameraMode = NavigationCameraMode.OVERVIEW) }
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
                trafficLabel = "Normal traffic"
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
                    lastUpdatedLabel = "Accepted ${assignment.assignmentCode}"
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
                            lastUpdatedLabel = "Accepted ${assignment.assignmentCode}"
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

    private fun advanceLocalStep() {
        val assignment = _state.value.assignment ?: return
        val currentStep = assignment.currentStep ?: run {
            _state.update { it.copy(simulationRunning = false) }
            return
        }
        val nextIndex = assignment.currentStepIndex + 1
        val completed = nextIndex >= assignment.routePlan.sequence.size
        _state.update {
            it.copy(
                loading = false,
                assignment = assignment.copy(
                    status = if (completed) "completed" else "in_progress",
                    currentStepIndex = nextIndex.coerceAtMost(assignment.routePlan.sequence.size)
                ),
                simulatedDriverLocation = currentStep.location,
                simulationRunning = if (completed) false else it.simulationRunning,
                lastUpdatedLabel = if (completed) "Arrived final stop" else "Arrived ${currentStep.label}; navigating to step ${nextIndex + 1}"
            )
        }
    }

    private fun advanceAlongRoadGeometry() {
        val state = _state.value
        val assignment = state.assignment ?: return
        val geometry = state.roadGeometry
        if (geometry.size < 2) {
            advanceLocalStep()
            refreshRoadGeometry()
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
        val arrivedCurrentStop = distanceMeters(location, currentStep.location) <= 75.0 || simulationGeometryIndex >= geometry.lastIndex - 1
        if (arrivedCurrentStop) {
            _state.update {
                it.copy(
                    simulatedDriverLocation = currentStep.location,
                    driverProjectedLocation = location,
                    routeProgressIndex = simulationGeometryIndex,
                    completedGeometry = routeProgress.first,
                    remainingGeometry = routeProgress.second,
                    simulatedSpeedKmh = 0,
                    trafficLabel = "Arrived ${currentStep.label}",
                    driverHeadingDeg = heading,
                    activeInstructionIndex = activeInstruction,
                    remainingDistanceMeters = 0,
                    remainingDurationSeconds = 0,
                    lastUpdatedLabel = "Arrived ${currentStep.label}"
                )
            }
            resetNavigationSimulation()
            advanceLocalStep()
            if (_state.value.assignment?.isCompleted != true) refreshRoadGeometry()
            return
        }
        _state.update {
            it.copy(
                simulatedDriverLocation = location,
                driverProjectedLocation = location,
                routeProgressIndex = simulationGeometryIndex,
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
        val location = _state.value.simulatedDriverLocation ?: return
        val geometry = _state.value.roadGeometry
        if (geometry.isEmpty()) return
        simulationGeometryIndex = geometry.indices.minByOrNull { index -> distanceMeters(location, geometry[index]) } ?: 0
        simulatedAlongLocation = location
    }

    private fun resetNavigationSimulation() {
        simulationGeometryIndex = 0
        trafficHoldTicks = 0
        simulatedAlongLocation = null
    }

    private fun advanceAlongPolyline(geometry: List<DriverLatLng>, speedKmh: Int, replayMultiplier: Double): DriverLatLng {
        var current = simulatedAlongLocation ?: geometry[simulationGeometryIndex]
        var budgetMeters = max(0.6, speedKmh / 3.6 * (SIMULATION_TICK_MS / 1000.0) * replayMultiplier)
        while (budgetMeters > 0.0 && simulationGeometryIndex < geometry.lastIndex) {
            val next = geometry[simulationGeometryIndex + 1]
            val segmentMeters = distanceMeters(current, next)
            if (segmentMeters <= budgetMeters || segmentMeters < 0.5) {
                current = next
                simulationGeometryIndex++
                budgetMeters -= segmentMeters
            } else {
                val ratio = budgetMeters / segmentMeters
                current = DriverLatLng(
                    current.lat + (next.lat - current.lat) * ratio,
                    current.lng + (next.lng - current.lng) * ratio
                )
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
            while (true) {
                delay(2_000)
                pollOnce(silent = true)
            }
        }
    }

    private suspend fun pollOnce(silent: Boolean = false) {
        if (!silent) _state.update { it.copy(loading = true, error = null) }
        repository.fetchActiveAssignment()
            .onSuccess { assignment ->
                _state.update {
                    it.copy(
                        loading = false,
                        assignment = assignment ?: it.assignment?.takeIf { current -> current.id == DriverAssignmentDemo.sample().id },
                        error = null,
                        lastUpdatedLabel = if (assignment == null) "Waiting for IntelligentRouteX assignment" else "Synced ${assignment.assignmentCode}"
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
        val waypoints = buildList {
            val driver = _state.value.simulatedDriverLocation ?: assignment.driverLocationAtAssignment
            add(GeoPoint(driver.lat, driver.lng))
            remainingSteps.forEach { step -> add(GeoPoint(step.location.lat, step.location.lng)) }
        }
        val waypointLabels = buildList {
            add("DR")
            remainingSteps.forEach { step -> add(step.label) }
        }
        val currentLegWaypoints = buildList {
            val driver = _state.value.simulatedDriverLocation ?: assignment.driverLocationAtAssignment
            add(GeoPoint(driver.lat, driver.lng))
            remainingSteps.firstOrNull()?.let { step -> add(GeoPoint(step.location.lat, step.location.lng)) }
        }
        viewModelScope.launch(Dispatchers.IO) {
            _state.update { it.copy(roadGeometryLoading = true, roadGeometryLabel = "Fetching road route") }
            runCatching { routingProvider.routeFixedOrder(waypoints) }
                .recoverCatching { routingProvider.routeFixedOrder(currentLegWaypoints) }
                .onSuccess { result ->
                    val points = result.coordinates
                    val geometry = points.map { point -> DriverLatLng(point.latitude(), point.longitude()) }
                    val driver = _state.value.simulatedDriverLocation ?: assignment.driverLocationAtAssignment
                    val initialProjected = geometry.firstOrNull() ?: driver
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
                            driverProjectedLocation = initialProjected,
                            routeProgressIndex = 0,
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
                            roadGeometryLabel = if (result.instructions.isEmpty()) qualityLabel else "Turn-by-turn • $qualityLabel",
                            cameraMode = if (it.simulationRunning) NavigationCameraMode.FOLLOWING else NavigationCameraMode.OVERVIEW
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
    }

    override fun onCleared() {
        pollJob?.cancel()
        super.onCleared()
    }
}
