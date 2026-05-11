package com.routefood.app.driver

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AccountCircle
import androidx.compose.material.icons.filled.AttachMoney
import androidx.compose.material.icons.filled.ChatBubble
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.CameraAlt
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Layers
import androidx.compose.material.icons.filled.LocationOn
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Route
import androidx.compose.material.icons.filled.Schedule
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material.icons.filled.WorkspacePremium
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Pause
import androidx.compose.material.icons.filled.Navigation
import androidx.compose.material.icons.filled.ArrowUpward
import androidx.compose.material.icons.filled.TurnRight
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Divider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.viewmodel.compose.viewModel
import com.routefood.app.compose.core.designsystem.Leaf
import com.routefood.app.compose.core.designsystem.PillShape
import com.routefood.app.compose.core.designsystem.RouteFoodTheme
import com.routefood.app.core.map.MapLibreRouteView
import com.routefood.app.core.map.MapRoutePoint
import com.routefood.app.core.map.MapRouteState
import com.routefood.app.driver.model.DriverAssignmentDemo
import com.routefood.app.driver.model.DriverLatLng
import com.routefood.app.driver.model.DriverRouteStep
import kotlinx.coroutines.delay
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sin
import kotlin.math.sqrt

private class DriverMapController {
    var mapView: MapLibreRouteView? = null
    fun fitRoute() = mapView?.fitRoute()
    fun zoomIn() = mapView?.zoomIn()
    fun zoomOut() = mapView?.zoomOut()
}

private enum class DriverTab { Home, Earnings, Orders, Planner, Profile }
private enum class DriverOverlay { RouteDetail, IntelligentRoute }

class DriverDemoActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent { RouteFoodTheme { DriverDemoApp() } }
    }
}

@Composable
fun DriverDemoApp(viewModel: DriverDemoViewModel = viewModel()) {
    val state by viewModel.state.collectAsState()
    val mapController = remember { DriverMapController() }
    var selectedTab by remember { mutableStateOf(DriverTab.Home) }
    var overlay by remember { mutableStateOf<DriverOverlay?>(null) }
    Scaffold(
        containerColor = DriverBg,
        bottomBar = { if (state.phase != DriverPhase.ActiveTrip && overlay == null) DriverBottomNav(selectedTab) { selectedTab = it } }
    ) { padding ->
        Box(Modifier.fillMaxSize().padding(padding)) {
            if (selectedTab == DriverTab.Home || state.phase == DriverPhase.ActiveTrip) {
                DriverMapSurface(state.assignment, state.simulatedDriverLocation, state.roadGeometry, state.driverHeadingDeg, state.phase == DriverPhase.ActiveTrip, mapController, Modifier.fillMaxSize())
            } else {
                DriverTabScreen(selectedTab, state.assignment, Modifier.fillMaxSize())
            }
            if (state.phase == DriverPhase.ActiveTrip) {
                NavigationTopInstruction(state, Modifier.align(Alignment.TopCenter).padding(top = 16.dp, start = 8.dp, end = 8.dp))
                NavigationDriverPuck(
                    headingDegrees = state.driverHeadingDeg.toFloat(),
                    modifier = Modifier
                        .align(Alignment.Center)
                        .padding(bottom = 96.dp)
                )
                NavigationMapControls(
                    modifier = Modifier.align(Alignment.CenterEnd).padding(end = 10.dp, bottom = 52.dp),
                    onZoomIn = mapController::zoomIn,
                    onZoomOut = mapController::zoomOut,
                    onFit = mapController::fitRoute
                )
            } else if (selectedTab == DriverTab.Home) {
                DriverTopStatus(state, Modifier.align(Alignment.TopCenter), onRefresh = viewModel::refreshNow)
                MapControls(Modifier.align(Alignment.CenterEnd).padding(end = 16.dp), onRefresh = viewModel::refreshNow)
            }
            if (selectedTab == DriverTab.Home || state.phase == DriverPhase.ActiveTrip) {
                DriverPrimaryPanel(
                    state = state,
                    onGoOnline = viewModel::goOnline,
                    onGoOffline = viewModel::goOffline,
                    onLoadLocalDemo = viewModel::loadLocalCoreDemo,
                    onAccept = viewModel::acceptAssignment,
                    onReject = viewModel::rejectAssignment,
                    onCompleteStep = viewModel::completeCurrentStep,
                    onToggleSimulation = viewModel::toggleDrivingSimulation,
                    onRouteDetail = { overlay = DriverOverlay.RouteDetail },
                    onIntelligentRoute = { overlay = DriverOverlay.IntelligentRoute },
                    modifier = Modifier.align(Alignment.BottomCenter).padding(start = 8.dp, end = 8.dp, bottom = if (state.phase == DriverPhase.ActiveTrip) 10.dp else 14.dp)
                )
            }
            overlay?.let { activeOverlay ->
                DriverOverlayScreen(activeOverlay, state.assignment, onClose = { overlay = null }, Modifier.fillMaxSize())
            }
        }
    }
}

@Composable
private fun NavigationDriverPuck(headingDegrees: Float, modifier: Modifier = Modifier) {
    Box(modifier.size(64.dp), contentAlignment = Alignment.Center) {
        Box(
            Modifier
                .size(60.dp)
                .clip(CircleShape)
                .background(Color(0xFF18D674).copy(alpha = 0.16f))
                .border(1.dp, Color.White.copy(alpha = 0.42f), CircleShape)
        )
        Box(
            Modifier
                .size(38.dp)
                .clip(CircleShape)
                .background(Leaf)
                .border(3.dp, Color.White, CircleShape),
            contentAlignment = Alignment.Center
        ) {
            Icon(
                Icons.Default.Navigation,
                contentDescription = "Driver direction marker",
                tint = Color(0xFF052E1A),
                modifier = Modifier
                    .size(24.dp)
                    .rotate(headingDegrees)
            )
        }
    }
}

private fun driverHeadingDegrees(state: DriverDemoUiState): Float {
    val assignment = state.assignment ?: return 0f
    val driver = state.simulatedDriverLocation ?: assignment.driverLocationAtAssignment
    val route = state.roadGeometry
    if (route.size >= 2) {
        val driverPoint = driver.lat to driver.lng
        val projection = projectDriverOnRoute(driverPoint, route)
        val next = route.drop(projection.second).firstOrNull { distanceMeters(projection.first, it.lat to it.lng) > 8.0 }
        if (next != null) return bearingDegrees(projection.first, next.lat to next.lng).toFloat()
    }
    val currentStep = assignment.currentStep
    return currentStep?.let { bearingDegrees(driver.lat to driver.lng, it.location.lat to it.location.lng).toFloat() } ?: 0f
}

private fun projectDriverOnRoute(
    driver: Pair<Double, Double>,
    route: List<DriverLatLng>
): Pair<Pair<Double, Double>, Int> {
    var bestPoint = route.first().lat to route.first().lng
    var bestEndIndex = 1
    var bestDistance = distanceMeters(bestPoint, driver)
    for (index in 0 until route.lastIndex) {
        val projected = projectPointOnSegment(driver, route[index].lat to route[index].lng, route[index + 1].lat to route[index + 1].lng)
        val distance = distanceMeters(projected, driver)
        if (distance < bestDistance) {
            bestPoint = projected
            bestEndIndex = index + 1
            bestDistance = distance
        }
    }
    return bestPoint to bestEndIndex
}

private fun projectPointOnSegment(
    point: Pair<Double, Double>,
    start: Pair<Double, Double>,
    end: Pair<Double, Double>
): Pair<Double, Double> {
    val metersPerLng = 111_320.0 * cos(Math.toRadians(point.first))
    val sx = (start.second - point.second) * metersPerLng
    val sy = (start.first - point.first) * 111_320.0
    val ex = (end.second - point.second) * metersPerLng
    val ey = (end.first - point.first) * 111_320.0
    val dx = ex - sx
    val dy = ey - sy
    val lengthSquared = dx * dx + dy * dy
    if (lengthSquared == 0.0) return start
    val t = (((-sx) * dx) + ((-sy) * dy)) / lengthSquared
    val clamped = t.coerceIn(0.0, 1.0)
    val px = sx + clamped * dx
    val py = sy + clamped * dy
    return (point.first + py / 111_320.0) to (point.second + px / metersPerLng)
}

private fun distanceMeters(a: Pair<Double, Double>, b: Pair<Double, Double>): Double {
    val latMeters = (a.first - b.first) * 111_320.0
    val lngMeters = (a.second - b.second) * 111_320.0 * cos(Math.toRadians((a.first + b.first) / 2.0))
    return sqrt((latMeters * latMeters) + (lngMeters * lngMeters))
}

private fun bearingDegrees(from: Pair<Double, Double>, to: Pair<Double, Double>): Double {
    val fromLat = Math.toRadians(from.first)
    val toLat = Math.toRadians(to.first)
    val deltaLng = Math.toRadians(to.second - from.second)
    val y = sin(deltaLng) * cos(toLat)
    val x = cos(fromLat) * sin(toLat) - sin(fromLat) * cos(toLat) * cos(deltaLng)
    return (Math.toDegrees(atan2(y, x)) + 360.0) % 360.0
}

@Composable
private fun NavigationTopInstruction(state: DriverDemoUiState, modifier: Modifier = Modifier) {
    val assignment = state.assignment
    val step = assignment?.currentStep
    if (step == null) return
    val instruction = state.navigationInstructions.getOrNull(state.activeInstructionIndex)
    val mainText = instruction?.text ?: if (step.isPickup) "Đang tới điểm lấy ${step.label}" else "Đang tới điểm giao ${step.label}"
    val nextInstruction = state.navigationInstructions.getOrNull(state.activeInstructionIndex + 1)?.text ?: "Tiếp theo: ${step.label}"
    Column(modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(18.dp),
            colors = CardDefaults.cardColors(containerColor = DriverSurface.copy(alpha = .94f)),
            elevation = CardDefaults.cardElevation(defaultElevation = 8.dp)
        ) {
            Row(Modifier.padding(horizontal = 14.dp, vertical = 11.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Box(Modifier.size(38.dp).clip(CircleShape).background(Leaf), contentAlignment = Alignment.Center) {
                    Icon(Icons.Default.ArrowUpward, null, tint = Color(0xFF03100B), modifier = Modifier.size(24.dp))
                }
                Column(Modifier.weight(1f)) {
                    Text(mainText, color = Color.White, fontSize = 18.sp, fontWeight = FontWeight.Black, maxLines = 2, overflow = TextOverflow.Ellipsis)
                    Text(step.title.substringAfter(" - ").ifBlank { step.title }, color = DriverTextMuted, fontSize = 12.sp, fontWeight = FontWeight.Bold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
                Box(Modifier.size(42.dp).clip(CircleShape).background(Color.White.copy(alpha = .10f)), contentAlignment = Alignment.Center) {
                    Icon(Icons.Default.Navigation, null, tint = Color(0xFF2DD4BF), modifier = Modifier.size(24.dp))
                }
            }
        }
        Card(
            modifier = Modifier.fillMaxWidth(.72f),
            shape = RoundedCornerShape(14.dp),
            colors = CardDefaults.cardColors(containerColor = DriverSurface.copy(alpha = .90f)),
            elevation = CardDefaults.cardElevation(defaultElevation = 6.dp)
        ) {
            Row(Modifier.padding(horizontal = 12.dp, vertical = 7.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(7.dp)) {
                Text("Sau đó", color = Color.White, fontWeight = FontWeight.Black, fontSize = 12.sp)
                Icon(Icons.Default.TurnRight, null, tint = Color(0xFF2DD4BF), modifier = Modifier.size(18.dp))
                Text(nextInstruction, color = DriverTextMuted, fontWeight = FontWeight.Bold, fontSize = 12.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
        }
    }
}

@Composable
private fun DriverTopStatus(state: DriverDemoUiState, modifier: Modifier = Modifier, onRefresh: () -> Unit) {
    Row(
        modifier.padding(horizontal = 14.dp, vertical = 46.dp).fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        Card(
            modifier = Modifier.weight(1f),
            shape = RoundedCornerShape(24.dp),
            colors = CardDefaults.cardColors(containerColor = DriverSurface.copy(alpha = .94f)),
            elevation = CardDefaults.cardElevation(defaultElevation = 8.dp)
        ) {
            Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Box(Modifier.size(12.dp).clip(CircleShape).background(if (state.online) Leaf else Color(0xFF9CA3AF)))
                Column(Modifier.weight(1f)) {
                    Text(if (state.online) "Driver D1 online" else "Driver D1 offline", color = DriverText, fontWeight = FontWeight.Black, fontSize = 15.sp)
                    Text(state.lastUpdatedLabel, color = DriverTextMuted, fontSize = 12.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
                if (state.loading) Text("Sync", color = Leaf, fontWeight = FontWeight.Bold, fontSize = 12.sp)
            }
        }
        Box(Modifier.size(48.dp).clip(CircleShape).background(DriverSurface.copy(alpha = .94f)).border(1.dp, DriverStroke, CircleShape).clickable { onRefresh() }, contentAlignment = Alignment.Center) {
            Icon(Icons.Default.Refresh, null, tint = DriverText)
        }
    }
}

@Composable
private fun MapControls(modifier: Modifier = Modifier, onRefresh: () -> Unit) {
    Column(modifier, verticalArrangement = Arrangement.spacedBy(12.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        DriverMapButton { Icon(Icons.Default.LocationOn, null, tint = DriverText) }
        DriverMapButton { Icon(Icons.Default.Layers, null, tint = Leaf) }
        DriverMapButton(onClick = onRefresh) { Icon(Icons.Default.Refresh, null, tint = DriverText) }
    }
}

@Composable
private fun DriverMapButton(onClick: () -> Unit = {}, content: @Composable () -> Unit) {
    Box(
        Modifier.size(46.dp).clip(CircleShape).background(DriverSurface.copy(alpha = .90f)).border(1.dp, DriverStroke, CircleShape).clickable { onClick() },
        contentAlignment = Alignment.Center
    ) { content() }
}

@Composable
private fun DriverPrimaryPanel(
    state: DriverDemoUiState,
    onGoOnline: () -> Unit,
    onGoOffline: () -> Unit,
    onLoadLocalDemo: () -> Unit,
    onAccept: () -> Unit,
    onReject: () -> Unit,
    onCompleteStep: () -> Unit,
    onToggleSimulation: () -> Unit,
    onRouteDetail: () -> Unit,
    onIntelligentRoute: () -> Unit,
    modifier: Modifier = Modifier
) {
    Column(modifier, verticalArrangement = Arrangement.spacedBy(10.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        when (state.phase) {
            DriverPhase.Offline -> OfflinePanel(onGoOnline, onLoadLocalDemo)
            DriverPhase.Idle -> IdlePanel(onGoOffline, onLoadLocalDemo)
            DriverPhase.Offer -> AssignmentOfferPanel(state.assignment, state.error, onAccept, onReject, onRouteDetail, onIntelligentRoute)
            DriverPhase.ActiveTrip -> ActiveTripPanel(state, state.error, onCompleteStep, onToggleSimulation)
        }
        if (state.phase != DriverPhase.ActiveTrip) DriverQuickActions()
    }
}

@Composable
private fun NavigationMapControls(
    modifier: Modifier = Modifier,
    onZoomIn: () -> Unit,
    onZoomOut: () -> Unit,
    onFit: () -> Unit
) {
    Column(modifier, verticalArrangement = Arrangement.spacedBy(10.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        DriverMapButton(onClick = onZoomIn) { Text("+", color = DriverText, fontSize = 24.sp, fontWeight = FontWeight.Black) }
        DriverMapButton(onClick = onZoomOut) { Text("−", color = DriverText, fontSize = 24.sp, fontWeight = FontWeight.Black) }
        DriverMapButton(onClick = onFit) { Icon(Icons.Default.LocationOn, null, tint = Leaf) }
    }
}

@Composable
private fun OfflinePanel(onGoOnline: () -> Unit, onLoadLocalDemo: () -> Unit) {
    Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Button(
            onClick = onGoOnline,
            shape = PillShape,
            colors = ButtonDefaults.buttonColors(containerColor = Leaf),
            contentPadding = PaddingValues(horizontal = 26.dp, vertical = 14.dp)
        ) { Text("Go Online", color = Color(0xFF03100B), fontWeight = FontWeight.Black, fontSize = 16.sp) }
        OutlinedButton(onClick = onLoadLocalDemo, shape = PillShape, colors = ButtonDefaults.outlinedButtonColors(contentColor = DriverText)) { Text("Load Core Demo") }
        InfoCard("Shift starts at 08:00 PM", "Batch mode is ready • Food, Parcel, COD enabled")
    }
}

@Composable
private fun IdlePanel(onGoOffline: () -> Unit, onLoadLocalDemo: () -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        InfoCard("Searching intelligent batches", "Waiting for route-compatible orders near your current zone.")
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            OutlinedButton(onClick = onGoOffline, shape = PillShape, modifier = Modifier.weight(1f), colors = ButtonDefaults.outlinedButtonColors(contentColor = DriverText)) { Text("Go Offline") }
            Button(onClick = onLoadLocalDemo, shape = PillShape, modifier = Modifier.weight(1f), colors = ButtonDefaults.buttonColors(containerColor = Leaf)) { Text("Demo Route", color = Color(0xFF03100B), fontWeight = FontWeight.Black) }
        }
    }
}

@Composable
private fun AssignmentOfferPanel(
    assignment: DriverAssignmentDemo?,
    error: String?,
    onAccept: () -> Unit,
    onReject: () -> Unit,
    onRouteDetail: () -> Unit,
    onIntelligentRoute: () -> Unit
) {
    if (assignment == null) return
    val stops = assignment.routePlan.sequence.size
    val estimatedPay = 42000 + assignment.orderIds.size * 13500 + max(0, stops - 2) * 5500
    val distanceKm = assignment.routePlan.distanceMeters / 1000.0
    val etaMin = max(1, assignment.routePlan.etaSeconds / 60)
    DriverSheetCard {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            CoreBadge(assignment)
            Column(Modifier.weight(1f)) {
                Text(if (assignment.orderIds.size > 1) "Batch Order Available" else "New Delivery Request", color = DriverText, fontWeight = FontWeight.Black, fontSize = 22.sp)
                Text("${assignment.orderIds.size} orders • $stops stops • ${assignment.assignmentCode}", color = DriverTextMuted, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            Box(Modifier.clip(PillShape).background(Color(0xFFE94335).copy(alpha = .18f)).padding(horizontal = 9.dp, vertical = 5.dp)) {
                Text("15s", color = Color(0xFFFF6B5F), fontWeight = FontWeight.Black, fontSize = 12.sp)
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
            OfferMetric("${String.format("%,d", estimatedPay)}đ", "Estimated earning", Modifier.weight(1f))
            OfferMetric(String.format("%.1f km", distanceKm), "Road distance", Modifier.weight(1f))
            OfferMetric("${etaMin}m", "ETA", Modifier.weight(1f))
        }
        CoreDecisionPanel(assignment)
        RouteStepPreview(assignment)
        BatchStopList(assignment)
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            OutlinedButton(onClick = onRouteDetail, shape = PillShape, modifier = Modifier.weight(1f).height(44.dp), colors = ButtonDefaults.outlinedButtonColors(contentColor = DriverText)) { Text("Route Detail", fontSize = 12.sp, fontWeight = FontWeight.Bold) }
            OutlinedButton(onClick = onIntelligentRoute, shape = PillShape, modifier = Modifier.weight(1f).height(44.dp), colors = ButtonDefaults.outlinedButtonColors(contentColor = Leaf)) { Text("Why this route?", fontSize = 12.sp, fontWeight = FontWeight.Bold) }
        }
        ErrorText(error)
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            OutlinedButton(onClick = onReject, shape = PillShape, modifier = Modifier.weight(1f).height(54.dp), colors = ButtonDefaults.outlinedButtonColors(contentColor = DriverText)) { Text("Decline", fontWeight = FontWeight.Bold) }
            Button(onClick = onAccept, shape = PillShape, modifier = Modifier.weight(1f).height(54.dp), colors = ButtonDefaults.buttonColors(containerColor = Leaf)) {
                Text(if (assignment.orderIds.size > 1) "Accept Batch" else "Accept", color = Color(0xFF03100B), fontWeight = FontWeight.Black)
            }
        }
    }
}

@Composable
private fun OfferMetric(value: String, label: String, modifier: Modifier = Modifier) {
    Card(modifier = modifier, shape = RoundedCornerShape(18.dp), colors = CardDefaults.cardColors(containerColor = Color.White.copy(alpha = .07f))) {
        Column(Modifier.padding(horizontal = 10.dp, vertical = 10.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(value, color = DriverText, fontWeight = FontWeight.Black, fontSize = 16.sp, maxLines = 1)
            Text(label, color = DriverTextMuted, fontSize = 10.sp, maxLines = 1)
        }
    }
}

@Composable
private fun ActiveTripPanel(
    state: DriverDemoUiState,
    error: String?,
    onCompleteStep: () -> Unit,
    onToggleSimulation: () -> Unit
) {
    val assignment = state.assignment
    if (assignment == null) return
    val currentStep = assignment.currentStep
    NavigationBottomSheet(state, assignment, currentStep, error, onCompleteStep, onToggleSimulation)
}

@Composable
private fun NavigationBottomSheet(
    state: DriverDemoUiState,
    assignment: DriverAssignmentDemo,
    currentStep: DriverRouteStep?,
    error: String?,
    onCompleteStep: () -> Unit,
    onToggleSimulation: () -> Unit
) {
    val remainingMinutes = max(1, (state.remainingDurationSeconds.takeIf { it > 0 } ?: (assignment.routePlan.etaSeconds / max(1, assignment.routePlan.sequence.size - assignment.currentStepIndex))) / 60)
    val remainingKm = max(.1, (state.remainingDistanceMeters.takeIf { it > 0 } ?: (assignment.routePlan.distanceMeters / max(1, assignment.routePlan.sequence.size - assignment.currentStepIndex))) / 1000.0)
    if (currentStep == null) {
        BatchCompletedPanel(assignment)
        return
    }
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(topStart = 24.dp, topEnd = 24.dp, bottomStart = 8.dp, bottomEnd = 8.dp),
        colors = CardDefaults.cardColors(containerColor = Color(0xFF101010).copy(alpha = .94f)),
        elevation = CardDefaults.cardElevation(defaultElevation = 14.dp)
    ) {
        Column(Modifier.padding(horizontal = 14.dp, vertical = 10.dp), verticalArrangement = Arrangement.spacedBy(7.dp)) {
            Box(Modifier.width(48.dp).height(3.dp).clip(PillShape).background(Color.White.copy(alpha = .32f)).align(Alignment.CenterHorizontally))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.clip(PillShape).background(Color.White.copy(alpha = .08f)).padding(horizontal = 9.dp, vertical = 4.dp)) {
                    Text("Batch ${assignment.assignmentCode}", color = DriverTextMuted, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                }
                Box(Modifier.clip(PillShape).background(Leaf.copy(alpha = .14f)).padding(horizontal = 9.dp, vertical = 4.dp)) {
                    Text("${assignment.orderIds.size} orders • ${assignment.routePlan.sequence.size} stops", color = Leaf, fontSize = 11.sp, fontWeight = FontWeight.Black)
                }
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Row(verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text("${remainingMinutes} min", color = Color(0xFF22C55E), fontWeight = FontWeight.Black, fontSize = 26.sp)
                        Text(String.format("%.1f km", remainingKm), color = Color.White.copy(alpha = .76f), fontSize = 14.sp, fontWeight = FontWeight.Bold)
                    }
                    Text("${if (currentStep.isPickup) "Pickup" else "Dropoff"} • ${state.simulatedSpeedKmh} km/h • ${state.trafficLabel}", color = Color.White.copy(alpha = .58f), fontSize = 12.sp, fontWeight = FontWeight.Bold, maxLines = 1)
                }
                Box(Modifier.size(48.dp).clip(CircleShape).background(Color.White.copy(alpha = .13f)).clickable { onCompleteStep() }, contentAlignment = Alignment.Center) {
                    Text(currentStep.label, color = Color.White, fontWeight = FontWeight.Black)
                }
                Spacer(Modifier.width(8.dp))
                Button(
                    onClick = onToggleSimulation,
                    shape = CircleShape,
                    colors = ButtonDefaults.buttonColors(containerColor = if (state.simulationRunning) Color(0xFF262626) else Color(0xFFE94335)),
                    contentPadding = PaddingValues(0.dp),
                    modifier = Modifier.size(58.dp)
                ) { Text(if (state.simulationRunning) "Pause" else "Start", color = Color.White, fontWeight = FontWeight.Black, fontSize = 12.sp) }
            }
            StepProgressBar(assignment, dark = true)
            ErrorText(error)
        }
    }
}

@Composable
private fun BatchCompletedPanel(assignment: DriverAssignmentDemo) {
    val earning = 42000 + assignment.orderIds.size * 13500 + max(0, assignment.routePlan.sequence.size - 2) * 5500
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(topStart = 30.dp, topEnd = 30.dp, bottomStart = 8.dp, bottomEnd = 8.dp),
        colors = CardDefaults.cardColors(containerColor = DriverSurface.copy(alpha = .98f)),
        elevation = CardDefaults.cardElevation(defaultElevation = 18.dp)
    ) {
        Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(13.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            Icon(Icons.Default.WorkspacePremium, null, tint = Leaf, modifier = Modifier.size(34.dp))
            Text("Hoàn thành đơn ghép!", color = DriverText, fontWeight = FontWeight.Black, fontSize = 20.sp)
            Text("${String.format("%,d", earning)}đ", color = Leaf, fontWeight = FontWeight.Black, fontSize = 34.sp)
            Text("${assignment.orderIds.size} đơn hàng đã giao • Route efficiency 91%", color = DriverTextMuted, fontSize = 13.sp)
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
                OfferMetric("58.000đ", "Cước cơ bản", Modifier.weight(1f))
                OfferMetric("12.000đ", "Batch bonus", Modifier.weight(1f))
                OfferMetric("4.000đ", "Phí chờ", Modifier.weight(1f))
            }
        }
    }
}

@Composable
private fun DriverSheetCard(content: @Composable ColumnScope.() -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(30.dp),
        colors = CardDefaults.cardColors(containerColor = DriverSurface.copy(alpha = .97f)),
        elevation = CardDefaults.cardElevation(defaultElevation = 12.dp)
    ) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp), content = content)
    }
}

@Composable
private fun CoreBadge(assignment: DriverAssignmentDemo) {
    val color = if (assignment.fallbackUsed) Color(0xFFF59E0B) else Leaf
    Box(Modifier.clip(PillShape).background(color.copy(alpha = .13f)).padding(horizontal = 10.dp, vertical = 7.dp)) {
        Text(if (assignment.fallbackUsed) "Fallback" else "Core", color = color, fontWeight = FontWeight.Black, fontSize = 12.sp)
    }
}

@Composable
private fun CoreDecisionPanel(assignment: DriverAssignmentDemo, compact: Boolean = false) {
    Card(shape = RoundedCornerShape(22.dp), colors = CardDefaults.cardColors(containerColor = DriverSurface2.copy(alpha = .92f))) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(7.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Icon(if (assignment.fallbackUsed) Icons.Default.Warning else Icons.Default.Route, null, tint = if (assignment.fallbackUsed) Color(0xFFF59E0B) else Leaf, modifier = Modifier.size(18.dp))
                Text("AI Route Reason", color = DriverText, fontWeight = FontWeight.Black, fontSize = 14.sp)
            }
            Text("${assignment.dispatchMode} • Trace ${assignment.traceId.takeLast(10)}", color = DriverTextMuted, fontSize = 12.sp, maxLines = 1)
            if (!compact) Text(assignment.decisionSummary.reason, color = DriverText, fontSize = 13.sp)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                assignment.decisionSummary.batchScore?.let { MetricPill("Score ${String.format("%.2f", it)}") }
                assignment.decisionSummary.savingsPercent?.let { MetricPill("Save $it%") }
                assignment.decisionSummary.detourMinutes?.let { MetricPill("Detour ${it}m") }
            }
        }
    }
}

@Composable
private fun MetricPill(text: String) {
    Box(Modifier.clip(PillShape).background(Color.White.copy(alpha = .08f)).padding(horizontal = 9.dp, vertical = 5.dp)) {
        Text(text, color = Leaf, fontWeight = FontWeight.Bold, fontSize = 11.sp)
    }
}

@Composable
private fun RouteStepPreview(assignment: DriverAssignmentDemo) {
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
        assignment.routePlan.sequence.forEachIndexed { index, step ->
            Box(
                Modifier.size(if (index == assignment.currentStepIndex) 38.dp else 32.dp).clip(CircleShape)
                    .background(if (step.isPickup) Leaf else Color(0xFFFF7A1A)),
                contentAlignment = Alignment.Center
            ) { Text(step.label, color = Color.White, fontSize = 11.sp, fontWeight = FontWeight.Black) }
            if (index < assignment.routePlan.sequence.lastIndex) Divider(Modifier.width(16.dp), color = Color(0xFFDDE7E0))
        }
    }
}

@Composable
private fun BatchStopList(assignment: DriverAssignmentDemo) {
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        assignment.routePlan.sequence.take(5).forEach { step ->
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(9.dp)) {
                Box(Modifier.size(22.dp).clip(CircleShape).background(if (step.isPickup) Color(0xFF1E88E5) else Leaf), contentAlignment = Alignment.Center) {
                    Text(step.label, color = Color.White, fontWeight = FontWeight.Black, fontSize = 9.sp)
                }
                Text(step.title.substringAfter(" - ").ifBlank { step.title }, color = DriverText, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                val badge = when {
                    !step.isPickup && step.label.endsWith("2") -> "COD"
                    !step.isPickup && step.label.endsWith("3") -> "OTP"
                    else -> null
                }
                if (badge != null) Box(Modifier.clip(PillShape).background(if (badge == "COD") Color(0xFFFFB020).copy(alpha = .18f) else Color(0xFF2D7DFF).copy(alpha = .18f)).padding(horizontal = 7.dp, vertical = 3.dp)) {
                    Text(badge, color = if (badge == "COD") Color(0xFFFFC857) else Color(0xFF78A8FF), fontSize = 9.sp, fontWeight = FontWeight.Black)
                }
            }
        }
    }
}

@Composable
private fun NavigationInstructionCard(assignment: DriverAssignmentDemo, step: DriverRouteStep) {
    val nextStep = assignment.routePlan.sequence.getOrNull(assignment.currentStepIndex + 1)
    val remainingMeters = max(180, assignment.routePlan.distanceMeters / max(1, assignment.routePlan.sequence.size - assignment.currentStepIndex))
    val remainingMinutes = max(2, assignment.routePlan.etaSeconds / 60 / max(1, assignment.routePlan.sequence.size - assignment.currentStepIndex))
    Card(shape = RoundedCornerShape(24.dp), colors = CardDefaults.cardColors(containerColor = Color(0xFF101916))) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Box(Modifier.size(50.dp).clip(CircleShape).background(if (step.isPickup) Leaf else Color(0xFFFF7A1A)), contentAlignment = Alignment.Center) {
                    Icon(Icons.Default.Navigation, null, tint = Color.White, modifier = Modifier.size(26.dp))
                }
                Column(Modifier.weight(1f)) {
                    Text("${remainingMeters}m", color = Color.White, fontWeight = FontWeight.Black, fontSize = 28.sp)
                    Text(if (step.isPickup) "Head to pickup point ${step.label}" else "Head to customer dropoff ${step.label}", color = Color.White.copy(alpha = .78f), fontSize = 13.sp)
                }
                Box(Modifier.size(42.dp).clip(CircleShape).background(Color.White.copy(alpha = .12f)), contentAlignment = Alignment.Center) {
                    Text(step.label, color = Color.White, fontWeight = FontWeight.Black)
                }
            }
            Divider(color = Color.White.copy(alpha = .12f))
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Box(Modifier.size(42.dp).clip(CircleShape).background(if (step.isPickup) Leaf else Color(0xFFFF7A1A)), contentAlignment = Alignment.Center) {
                    Text(step.label, color = Color.White, fontWeight = FontWeight.Black)
                }
                Column(Modifier.weight(1f)) {
                    Text(if (step.isPickup) "Pickup" else "Dropoff", color = Color.White.copy(alpha = .62f), fontSize = 12.sp, fontWeight = FontWeight.Bold)
                    Text(step.title, color = Color.White, fontWeight = FontWeight.Black, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text("ETA $remainingMinutes min${nextStep?.let { " • next ${it.label}" } ?: ""}", color = Color.White.copy(alpha = .66f), fontSize = 12.sp)
                }
            }
        }
    }
}

@Composable
private fun CurrentStepCard(step: DriverRouteStep) {
    Card(shape = RoundedCornerShape(22.dp), colors = CardDefaults.cardColors(containerColor = DriverSurface2)) {
        Row(Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Box(Modifier.size(42.dp).clip(CircleShape).background(if (step.isPickup) Leaf else Color(0xFFFF7A1A)), contentAlignment = Alignment.Center) {
                Text(step.label, color = Color.White, fontWeight = FontWeight.Black)
            }
            Column(Modifier.weight(1f)) {
                Text(if (step.isPickup) "Pickup" else "Dropoff", color = DriverTextMuted, fontSize = 12.sp, fontWeight = FontWeight.Bold)
                Text(step.title, color = DriverText, fontWeight = FontWeight.Black, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
        }
    }
}

@Composable
private fun StepProgressBar(assignment: DriverAssignmentDemo, dark: Boolean = false) {
    Row(horizontalArrangement = Arrangement.spacedBy(5.dp), modifier = Modifier.fillMaxWidth()) {
        assignment.routePlan.sequence.forEachIndexed { index, _ ->
            Box(
                Modifier.weight(1f).height(7.dp).clip(PillShape)
                    .background(if (index <= assignment.currentStepIndex) Leaf else if (dark) Color.White.copy(alpha = .18f) else Color(0xFFE2E8E3))
            )
        }
    }
}

@Composable
private fun InfoCard(title: String, subtitle: String) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(24.dp),
        colors = CardDefaults.cardColors(containerColor = DriverSurface.copy(alpha = .96f)),
        elevation = CardDefaults.cardElevation(defaultElevation = 8.dp)
    ) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(title, fontWeight = FontWeight.Black, color = DriverText)
            Text(subtitle, color = DriverTextMuted, fontSize = 12.sp)
        }
    }
}

@Composable
private fun ErrorText(error: String?) {
    if (!error.isNullOrBlank()) Text(error, color = Color(0xFFB42318), fontSize = 12.sp, maxLines = 2, overflow = TextOverflow.Ellipsis)
}

@Composable
private fun DriverQuickActions() {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(22.dp),
        colors = CardDefaults.cardColors(containerColor = DriverSurface.copy(alpha = .96f)),
        elevation = CardDefaults.cardElevation(defaultElevation = 8.dp)
    ) {
        Row(Modifier.padding(horizontal = 10.dp, vertical = 12.dp), horizontalArrangement = Arrangement.SpaceBetween) {
            DriverActionTile("Services", Icons.Default.Route)
            DriverActionTile("Destination", Icons.Default.LocationOn)
            DriverActionTile("Auto", Icons.Default.CheckCircle)
            DriverActionTile("Planner", Icons.Default.Schedule)
        }
    }
}

@Composable
private fun DriverActionTile(label: String, icon: androidx.compose.ui.graphics.vector.ImageVector) {
    Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.width(78.dp)) {
        Box(Modifier.size(42.dp).clip(CircleShape).background(Color.White.copy(alpha = .08f)), contentAlignment = Alignment.Center) {
            Icon(icon, null, tint = DriverText, modifier = Modifier.size(19.dp))
        }
        Text(label, color = DriverText, fontSize = 11.sp, fontWeight = FontWeight.Bold, maxLines = 1)
    }
}

@Composable
private fun DriverBottomNav(selectedTab: DriverTab, onSelect: (DriverTab) -> Unit) {
    Surface(color = DriverSurface.copy(alpha = .98f), shadowElevation = 10.dp) {
        Row(Modifier.fillMaxWidth().height(72.dp).padding(horizontal = 8.dp), horizontalArrangement = Arrangement.SpaceAround, verticalAlignment = Alignment.CenterVertically) {
            BottomNavItem("Home", Icons.Default.Home, selected = selectedTab == DriverTab.Home) { onSelect(DriverTab.Home) }
            BottomNavItem("Earnings", Icons.Default.AttachMoney, selected = selectedTab == DriverTab.Earnings) { onSelect(DriverTab.Earnings) }
            BottomNavItem("Orders", Icons.Default.ChatBubble, selected = selectedTab == DriverTab.Orders) { onSelect(DriverTab.Orders) }
            BottomNavItem("Planner", Icons.Default.Schedule, selected = selectedTab == DriverTab.Planner) { onSelect(DriverTab.Planner) }
            BottomNavItem("Profile", Icons.Default.AccountCircle, selected = selectedTab == DriverTab.Profile) { onSelect(DriverTab.Profile) }
        }
    }
}

@Composable
private fun BottomNavItem(label: String, icon: androidx.compose.ui.graphics.vector.ImageVector, selected: Boolean = false, onClick: () -> Unit) {
    Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(4.dp), modifier = Modifier.clip(RoundedCornerShape(18.dp)).clickable { onClick() }.padding(horizontal = 8.dp, vertical = 4.dp)) {
        Icon(icon, null, tint = if (selected) Leaf else DriverTextMuted, modifier = Modifier.size(21.dp))
        Text(label, color = if (selected) Leaf else DriverTextMuted, fontSize = 10.sp, fontWeight = if (selected) FontWeight.Black else FontWeight.SemiBold)
    }
}

@Composable
private fun DriverTabScreen(tab: DriverTab, assignment: DriverAssignmentDemo?, modifier: Modifier = Modifier) {
    Column(
        modifier.background(Brush.verticalGradient(listOf(Color(0xFF06100E), DriverBg))).padding(horizontal = 18.dp, vertical = 34.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp)
    ) {
        Text(tabTitle(tab), color = DriverText, fontSize = 28.sp, fontWeight = FontWeight.Black)
        Text(tabSubtitle(tab), color = DriverTextMuted, fontSize = 13.sp)
        when (tab) {
            DriverTab.Earnings -> EarningsScreen()
            DriverTab.Orders -> OrdersScreen(assignment)
            DriverTab.Planner -> PlannerScreen()
            DriverTab.Profile -> ProfileScreen()
            DriverTab.Home -> Unit
        }
    }
}

private fun tabTitle(tab: DriverTab): String = when (tab) {
    DriverTab.Home -> "Home"
    DriverTab.Earnings -> "Earnings"
    DriverTab.Orders -> "Orders"
    DriverTab.Planner -> "Planner"
    DriverTab.Profile -> "Profile"
}

private fun tabSubtitle(tab: DriverTab): String = when (tab) {
    DriverTab.Home -> "Map-first driver workspace"
    DriverTab.Earnings -> "Thu nhập, thưởng ghép đơn và ví tài xế"
    DriverTab.Orders -> "Đơn đang chạy, lịch sử và vấn đề cần xử lý"
    DriverTab.Planner -> "Ca làm, vùng nóng và dự báo nhu cầu"
    DriverTab.Profile -> "Hồ sơ, hiệu suất, giấy tờ và an toàn"
}

@Composable
private fun EarningsScreen() {
    DriverStatHero("328.000đ", "Today earnings", "8 orders • 2 batch orders • 5h 42m online")
    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        OfferMetric("48.000đ", "Batch bonus", Modifier.weight(1f))
        OfferMetric("12.000đ", "Waiting fee", Modifier.weight(1f))
        OfferMetric("16.000đ", "Tips", Modifier.weight(1f))
    }
    DriverListCard("Earnings Breakdown", listOf("Base fare 180.000đ", "Distance fare 72.000đ", "Rain + peak bonus 42.000đ", "COD balance clear"))
    DriverListCard("Smart Forecast", listOf("Stay online 2h more: 180.000đ - 240.000đ", "Best zone: District 2", "Best order type: Batch Food"))
}

@Composable
private fun OrdersScreen(assignment: DriverAssignmentDemo?) {
    DriverStatHero("Current Batch", assignment?.assignmentCode ?: "No active batch", assignment?.routePlan?.summary ?: "No active route now")
    DriverListCard("Active Orders", assignment?.routePlan?.sequence?.map { "${it.label} • ${it.title}" } ?: listOf("No active orders"))
    DriverListCard("Issue Queue", listOf("Customer not reachable • Under review", "Restaurant delay • Compensation eligible", "Proof pending • 1 photo required"))
}

@Composable
private fun PlannerScreen() {
    DriverStatHero("08:00 PM - 11:00 PM", "Booked shift tonight", "District 1 • Expected demand High • +15% bonus")
    DriverListCard("Hot Hours", listOf("18:00 - 21:00 • Very High", "11:00 - 13:00 • Lunch peak", "Rain bonus active if weather changes"))
    DriverListCard("Demand Forecast", listOf("Best zone: Vinhomes Grand Park", "Popular: Food + Grocery", "Suggested mode: Auto accept batch <= 3 orders"))
}

@Composable
private fun ProfileScreen() {
    DriverStatHero("4.92 ★", "Minh Driver", "1,248 completed orders • Active account")
    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        OfferMetric("94%", "On-time", Modifier.weight(1f))
        OfferMetric("72%", "Batch accept", Modifier.weight(1f))
        OfferMetric("88%", "Efficiency", Modifier.weight(1f))
    }
    DriverListCard("Account", listOf("Documents approved", "Vehicle: Honda Air Blade", "COD balance clear", "Safety center ready"))
}

@Composable
private fun DriverStatHero(value: String, title: String, subtitle: String) {
    Card(shape = RoundedCornerShape(28.dp), colors = CardDefaults.cardColors(containerColor = DriverSurface.copy(alpha = .96f))) {
        Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(7.dp)) {
            Text(title, color = DriverTextMuted, fontSize = 13.sp, fontWeight = FontWeight.Bold)
            Text(value, color = Leaf, fontSize = 32.sp, fontWeight = FontWeight.Black)
            Text(subtitle, color = DriverText, fontSize = 13.sp)
        }
    }
}

@Composable
private fun DriverListCard(title: String, items: List<String>) {
    Card(shape = RoundedCornerShape(24.dp), colors = CardDefaults.cardColors(containerColor = DriverSurface.copy(alpha = .92f))) {
        Column(Modifier.padding(15.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(title, color = DriverText, fontSize = 16.sp, fontWeight = FontWeight.Black)
            items.forEach { item ->
                Row(horizontalArrangement = Arrangement.spacedBy(9.dp), verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(8.dp).clip(CircleShape).background(Leaf))
                    Text(item, color = DriverTextMuted, fontSize = 13.sp, modifier = Modifier.weight(1f))
                }
            }
        }
    }
}

@Composable
private fun DriverOverlayScreen(overlay: DriverOverlay, assignment: DriverAssignmentDemo?, onClose: () -> Unit, modifier: Modifier = Modifier) {
    Box(modifier.background(Color.Black.copy(alpha = .72f)).padding(14.dp), contentAlignment = Alignment.Center) {
        Card(shape = RoundedCornerShape(30.dp), colors = CardDefaults.cardColors(containerColor = DriverSurface.copy(alpha = .98f))) {
            Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(if (overlay == DriverOverlay.RouteDetail) "Chi tiết tuyến" else "Vì sao tuyến này?", color = DriverText, fontWeight = FontWeight.Black, fontSize = 24.sp)
                        Text(assignment?.assignmentCode ?: "No assignment", color = DriverTextMuted, fontSize = 12.sp)
                    }
                    OutlinedButton(onClick = onClose, shape = PillShape, colors = ButtonDefaults.outlinedButtonColors(contentColor = DriverText)) { Text("Đóng") }
                }
                if (overlay == DriverOverlay.RouteDetail) RouteDetailOverlayContent(assignment) else IntelligentRouteOverlayContent(assignment)
            }
        }
    }
}

@Composable
private fun RouteDetailOverlayContent(assignment: DriverAssignmentDemo?) {
    val routePlan = assignment?.routePlan
    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        OfferMetric(String.format("%.1f km", (routePlan?.distanceMeters ?: 0) / 1000.0), "Khoảng cách", Modifier.weight(1f))
        OfferMetric("${max(1, (routePlan?.etaSeconds ?: 60) / 60)}m", "Thời gian", Modifier.weight(1f))
        OfferMetric("120.000đ", "COD cần thu", Modifier.weight(1f))
    }
    DriverMiniRouteMap(assignment)
    DriverListCard("Stop Sequence", routePlan?.sequence?.map { "${it.label} • ${if (it.isPickup) "Pickup" else "Dropoff"} • ${it.title}" } ?: listOf("No route"))
}

@Composable
private fun IntelligentRouteOverlayContent(assignment: DriverAssignmentDemo?) {
    val reasons = listOf(
        "Giảm 4.8 km so với giao riêng lẻ",
        "Ưu tiên đơn đồ nóng trước để giữ chất lượng",
        "Các điểm giao nằm cùng hành lang di chuyển",
        "Tránh candidate zigzag và pickup xa",
        "Road matrix OSRM dùng trước khi chốt sequence"
    )
    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        OfferMetric("92/100", "Batch Score", Modifier.weight(1f))
        OfferMetric("91%", "Efficiency", Modifier.weight(1f))
        OfferMetric("Low", "Delay risk", Modifier.weight(1f))
    }
    assignment?.let { CoreDecisionPanel(it) }
    DriverListCard("IntelligentX optimized this batch by", reasons)
    DriverListCard("Rejected candidates", listOf("Opposite direction • score 0.18", "Far pickup • score 0.24", "Zigzag risk • score 0.31"))
}

@Composable
private fun DriverMiniRouteMap(assignment: DriverAssignmentDemo?) {
    Card(shape = RoundedCornerShape(24.dp), colors = CardDefaults.cardColors(containerColor = Color(0xFF071412))) {
        Box(Modifier.fillMaxWidth().height(170.dp)) {
            DriverCoreMap(assignment, assignment?.driverLocationAtAssignment, false, Modifier.fillMaxSize())
        }
    }
}

@Composable
private fun DriverMapSurface(
    assignment: DriverAssignmentDemo?,
    simulatedDriverLocation: DriverLatLng?,
    roadGeometry: List<DriverLatLng>,
    driverHeadingDeg: Double,
    navigationMode: Boolean,
    mapController: DriverMapController,
    modifier: Modifier = Modifier
) {
    if (assignment != null) {
        var mapReady by remember(assignment.id) { mutableStateOf(false) }
        LaunchedEffect(assignment.id) {
            delay(450)
            mapReady = true
        }
        if (mapReady) {
            RealOsmDriverMap(assignment, simulatedDriverLocation, roadGeometry, driverHeadingDeg, mapController, modifier)
        } else {
            mapController.mapView = null
            DriverCoreMap(assignment, simulatedDriverLocation, navigationMode, modifier)
        }
    } else {
        mapController.mapView = null
        DriverCoreMap(assignment, simulatedDriverLocation, navigationMode, modifier)
    }
}

@Composable
private fun RealOsmDriverMap(
    assignment: DriverAssignmentDemo,
    simulatedDriverLocation: DriverLatLng?,
    roadGeometry: List<DriverLatLng>,
    driverHeadingDeg: Double,
    mapController: DriverMapController,
    modifier: Modifier = Modifier
) {
    val driver = (simulatedDriverLocation ?: assignment.driverLocationAtAssignment).toMapRoutePoint("DR", "driver", "Driver ${assignment.driverCode}")
    val stops = assignment.routePlan.sequence.map { step ->
        step.location.toMapRoutePoint(step.label, step.type, step.title)
    }
    val routeState = MapRouteState(
        driver = driver,
        stops = stops,
        polyline = if (roadGeometry.size >= 2) roadGeometry.map { it.lat to it.lng } else emptyList(),
        activeStepIndex = assignment.currentStepIndex,
        geometryAvailable = roadGeometry.size >= 2,
        followDriver = simulatedDriverLocation != null,
        driverHeadingDeg = driverHeadingDeg
    )
    AndroidView(
        modifier = modifier.background(NavMapBg),
        factory = { context -> MapLibreRouteView(context).also { mapController.mapView = it } },
        update = { mapView ->
            mapController.mapView = mapView
            mapView.updateRoute(routeState)
        }
    )
}

private fun DriverLatLng.toMapRoutePoint(label: String, type: String, title: String): MapRoutePoint = MapRoutePoint(label, type, lat, lng, title)

@Composable
private fun DriverCoreMap(assignment: DriverAssignmentDemo?, simulatedDriverLocation: DriverLatLng?, navigationMode: Boolean, modifier: Modifier = Modifier) {
    val driver = simulatedDriverLocation ?: assignment?.driverLocationAtAssignment ?: DriverLatLng(10.776, 106.704)
    val steps = assignment?.routePlan?.sequence.orEmpty()
    val activeStep = assignment?.currentStep
    Canvas(modifier.background(if (navigationMode) NavMapBg else DriverMapBg)) {
        val width = size.width
        val height = size.height
        drawRect(Brush.verticalGradient(listOf(Color(0xFF071412), Color(0xFF0B1B18), Color(0xFF050808))))
        repeat(9) { index ->
            val x = width * (index + 1) / 10f
            drawLine(Color(0xFF315650).copy(alpha = if (navigationMode) .35f else .28f), Offset(x, 0f), Offset(x, height), strokeWidth = 2f)
        }
        repeat(13) { index ->
            val y = height * (index + 1) / 14f
            drawLine(Color(0xFF315650).copy(alpha = if (navigationMode) .35f else .28f), Offset(0f, y), Offset(width, y), strokeWidth = 2f)
        }
        drawOrganicRoads(width, height, navigationMode)
        if (steps.isNotEmpty()) {
            val routePoints = listOf(driver) + steps.map { it.location }
            val path = Path()
            routePoints.forEachIndexed { index, point ->
                val mapped = point.toCanvas(width, height)
                if (index == 0) path.moveTo(mapped.x, mapped.y) else path.lineTo(mapped.x, mapped.y)
            }
            drawPath(path, color = if (navigationMode) Color(0xFF00D4FF) else Leaf, style = Stroke(width = if (navigationMode) 15f else 9f))
            drawPath(path, color = if (navigationMode) Color(0xFF4CE7FF) else Color.White.copy(alpha = .72f), style = Stroke(width = if (navigationMode) 7f else 3f))
            activeStep?.let { step ->
                val driverPoint = driver.toCanvas(width, height)
                val targetPoint = step.location.toCanvas(width, height)
                drawLine(if (navigationMode) Color(0xFF03101B) else Color(0xFF101916), driverPoint, targetPoint, strokeWidth = if (navigationMode) 18f else 12f)
                drawLine(if (navigationMode) Color(0xFF00D4FF) else Color(0xFFFFD166), driverPoint, targetPoint, strokeWidth = if (navigationMode) 9f else 5f)
            }
        }
        drawDriverArrow(driver.toCanvas(width, height), isNavigating = activeStep != null)
        steps.forEachIndexed { index, step ->
            drawMapMarker(
                step.location.toCanvas(width, height),
                step.label,
                if (step.isPickup) Leaf else Color(0xFFFF7A1A),
                isActive = assignment != null && index == assignment.currentStepIndex
            )
        }
        if (!navigationMode) drawContextLabel(if (steps.isEmpty()) "IntelligentX Driver Map" else "Live route from IntelligentRouteX route_plan", Offset(28f, 82f), textColor = DriverTextMuted)
    }
}

private fun androidx.compose.ui.graphics.drawscope.DrawScope.drawOrganicRoads(width: Float, height: Float, navigationMode: Boolean = false) {
    val road = if (navigationMode) Color(0xFF556B85) else Color(0xFF365E57)
    repeat(7) { index ->
        val y = height * (.18f + index * .095f)
        drawLine(road.copy(alpha = if (navigationMode) .48f else .7f), Offset(0f, y), Offset(width, y + if (index % 2 == 0) 120f else -80f), strokeWidth = if (navigationMode) 8f else 5f)
    }
    repeat(5) { index ->
        val x = width * (.12f + index * .19f)
        drawLine(road.copy(alpha = if (navigationMode) .42f else .55f), Offset(x, 0f), Offset(x + 140f, height), strokeWidth = if (navigationMode) 7f else 4f)
    }
}

private fun androidx.compose.ui.graphics.drawscope.DrawScope.drawMapMarker(center: Offset, label: String, color: Color, isActive: Boolean) {
    if (isActive) drawCircle(color.copy(alpha = .18f), radius = 42f, center = center)
    drawCircle(Color.White, radius = if (isActive) 28f else 24f, center = center)
    drawCircle(color, radius = if (isActive) 22f else 18f, center = center)
    drawContextLabel(label, center + Offset(-15f, 8f), textColor = Color.White, size = if (isActive) 25f else 21f)
}

private fun androidx.compose.ui.graphics.drawscope.DrawScope.drawDriverArrow(center: Offset, isNavigating: Boolean) {
    if (isNavigating) drawCircle(Color(0xFF1677FF).copy(alpha = .16f), radius = 52f, center = center)
    val path = Path().apply {
        moveTo(center.x, center.y - 31f)
        lineTo(center.x + 27f, center.y + 25f)
        lineTo(center.x, center.y + 13f)
        lineTo(center.x - 27f, center.y + 25f)
        close()
    }
    drawPath(path, Color.White)
    drawPath(path, Color(0xFF1677FF))
    drawContextLabel("DR", center + Offset(-17f, 8f), textColor = Color.White, size = 21f)
}

private fun androidx.compose.ui.graphics.drawscope.DrawScope.drawContextLabel(text: String, offset: Offset, textColor: Color = DriverInk, size: Float = 30f) {
    drawContext.canvas.nativeCanvas.drawText(text, offset.x, offset.y, android.graphics.Paint().apply {
        isAntiAlias = true
        color = textColor.toArgbCompat()
        textSize = size
        isFakeBoldText = true
    })
}

private fun DriverLatLng.toCanvas(width: Float, height: Float): Offset {
    val minLat = 10.70
    val maxLat = 10.83
    val minLng = 106.62
    val maxLng = 106.76
    val nx = ((lng - minLng) / (maxLng - minLng)).coerceIn(.06, .94)
    val ny = ((maxLat - lat) / (maxLat - minLat)).coerceIn(.10, .90)
    return Offset((nx * width).toFloat(), (ny * height).toFloat())
}

private fun Color.toArgbCompat(): Int = android.graphics.Color.argb(
    (alpha * 255).toInt(),
    (red * 255).toInt(),
    (green * 255).toInt(),
    (blue * 255).toInt()
)

private val DriverInk = Color(0xFF141A17)
private val MutedDriver = Color(0xFF66746D)
private val DriverBg = Color(0xFF050808)
private val DriverMapBg = Color(0xFF07100F)
private val DriverSurface = Color(0xFF101716)
private val DriverSurface2 = Color(0xFF16211F)
private val DriverStroke = Color.White.copy(alpha = .12f)
private val DriverText = Color.White
private val DriverTextMuted = Color(0xFF9CAAAA)
private val NavGreen = Color(0xFF00796B)
private val NavMapBg = Color(0xFF07121F)
