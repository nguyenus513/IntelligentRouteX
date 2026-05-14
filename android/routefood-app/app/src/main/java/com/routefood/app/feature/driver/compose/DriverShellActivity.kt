package com.routefood.app.feature.driver.compose

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material.icons.rounded.AccountBalance
import androidx.compose.material.icons.rounded.Assignment
import androidx.compose.material.icons.rounded.Call
import androidx.compose.material.icons.rounded.Chat
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.CrisisAlert
import androidx.compose.material.icons.rounded.DirectionsBike
import androidx.compose.material.icons.rounded.ErrorOutline
import androidx.compose.material.icons.rounded.GpsFixed
import androidx.compose.material.icons.rounded.HelpCenter
import androidx.compose.material.icons.rounded.Home
import androidx.compose.material.icons.rounded.LocalShipping
import androidx.compose.material.icons.rounded.LocationOn
import androidx.compose.material.icons.rounded.Notifications
import androidx.compose.material.icons.rounded.Payments
import androidx.compose.material.icons.rounded.Person
import androidx.compose.material.icons.rounded.PinDrop
import androidx.compose.material.icons.rounded.Route
import androidx.compose.material.icons.rounded.Security
import androidx.compose.material.icons.rounded.Settings
import androidx.compose.material.icons.rounded.SupportAgent
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.viewmodel.compose.viewModel
import com.routefood.app.core.map.MapLibreRouteView
import com.routefood.app.core.map.MapRoutePoint
import com.routefood.app.core.map.MapRouteState
import com.routefood.app.core.map.MapSnappedWaypoint
import com.routefood.app.driver.DriverDemoUiState
import com.routefood.app.driver.DriverDemoViewModel
import com.routefood.app.driver.DriverPhase

class DriverShellActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent { DriverApp() }
    }
}

private val GrabGreen = Color(0xFF00B14F)
private val GrabDark = Color(0xFF006C3A)
private val GrabBg = Color(0xFFF4F7F5)
private val CardWhite = Color.White
private val TextMain = Color(0xFF111827)
private val TextMuted = Color(0xFF667085)
private val Danger = Color(0xFFEF4444)

private enum class DriverTab(val label: String, val icon: ImageVector) {
    Home("Trang chủ", Icons.Rounded.Home), Orders("Đơn", Icons.Rounded.Assignment),
    Wallet("Ví", Icons.Rounded.Payments), Notifications("Thông báo", Icons.Rounded.Notifications), Profile("Tài khoản", Icons.Rounded.Person)
}
private enum class ScreenKind { HOME, OFFER, NAV, PICKUP, DROPOFF, WALLET, ORDERS, SUPPORT, PROFILE, NOTIFY, FORM }
private data class DriverScreen(val key: String, val title: String, val tab: DriverTab, val kind: ScreenKind, val mapFirst: Boolean = false, val cta: String = "Tiếp tục", val icon: ImageVector = Icons.Rounded.CheckCircle, val summary: String = "")

private fun sc(key: String, title: String, tab: DriverTab, kind: ScreenKind, map: Boolean = false, cta: String = "Tiếp tục", icon: ImageVector = Icons.Rounded.CheckCircle, summary: String = "") = DriverScreen(key, title, tab, kind, map, cta, icon, summary)
private val S = listOf(
    sc("home_offline","Bạn đang offline",DriverTab.Home,ScreenKind.HOME,true,"Bật nhận đơn",Icons.Rounded.GpsFixed,"Bật online để nhận batch từ core dispatch."),
    sc("home_online","Đang online",DriverTab.Home,ScreenKind.HOME,true,"Tắt nhận đơn",Icons.Rounded.GpsFixed,"Đang chờ core phân đơn phù hợp."),
    sc("hot_zone","Khu vực nóng",DriverTab.Home,ScreenKind.NAV,true,"Pin map",Icons.Rounded.PinDrop,"Heatmap đơn hàng quanh Bến Nghé, Landmark, Q3."),
    sc("gps_status","Trạng thái GPS",DriverTab.Home,ScreenKind.FORM,false,"Đã hiểu",Icons.Rounded.ErrorOutline,"Mạng/GPS/pin phải ổn định."),
    sc("offer","Batch mới từ Core",DriverTab.Orders,ScreenKind.OFFER,true,"Nhận batch",Icons.Rounded.LocalShipping,"Core đã chọn driver + thứ tự stop tối ưu."),
    sc("offer_detail","Chi tiết trước khi nhận",DriverTab.Orders,ScreenKind.OFFER,true,"Nhận batch",Icons.Rounded.Route,"Map preview điểm; core là nguồn ghép route."),
    sc("suggest_merge","Gợi ý ghép thêm",DriverTab.Orders,ScreenKind.OFFER,false,"Ghép đơn",Icons.Rounded.Route,"Đơn gần tuyến, thêm thu nhập, tăng ETA thấp."),
    sc("confirm_merge","Xác nhận ghép đơn",DriverTab.Orders,ScreenKind.OFFER,false,"Xác nhận",Icons.Rounded.CheckCircle,"Batch mới vẫn do core dispatch quyết định."),
    sc("trip_overview","Tổng quan chuyến",DriverTab.Orders,ScreenKind.NAV,true,"Bắt đầu chạy",Icons.Rounded.Route,"Stop list trong card, map chỉ vẽ leg hiện tại."),
    sc("nav_pickup","Đi tới điểm lấy",DriverTab.Orders,ScreenKind.NAV,true,"Tôi đã đến",Icons.Rounded.DirectionsBike,"Mũi tên driver + camera follow."),
    sc("pickup_arrived","Đã đến shop",DriverTab.Orders,ScreenKind.PICKUP,true,"Xác nhận đã đến",Icons.Rounded.LocationOn,"Dừng mô phỏng, kiểm tra đúng shop."),
    sc("pickup_collect","Nhận hàng",DriverTab.Orders,ScreenKind.PICKUP,false,"Đã nhận hàng",Icons.Rounded.CheckCircle,"Đối chiếu mã đơn, số túi, ghi chú món."),
    sc("pickup_issue","Lỗi lấy hàng",DriverTab.Orders,ScreenKind.SUPPORT,false,"Báo hỗ trợ",Icons.Rounded.ErrorOutline,"Shop đóng cửa, chờ lâu, sai địa chỉ, thiếu hàng."),
    sc("nav_dropoff","Đi tới khách",DriverTab.Orders,ScreenKind.NAV,true,"Tôi đã đến",Icons.Rounded.DirectionsBike,"Tên khách, gọi/chat, ghi chú giao."),
    sc("dropoff_arrived","Đã đến khách",DriverTab.Orders,ScreenKind.DROPOFF,true,"Hoàn tất giao",Icons.Rounded.LocationOn,"Call/message khách, kiểm tra instruction."),
    sc("delivery_success","Giao thành công",DriverTab.Orders,ScreenKind.DROPOFF,false,"Hoàn tất",Icons.Rounded.CheckCircle,"OTP/ảnh bằng chứng/COD nếu cần."),
    sc("delivery_failed","Giao thất bại",DriverTab.Orders,ScreenKind.SUPPORT,false,"Hoàn hàng",Icons.Rounded.CrisisAlert,"Không nghe máy, sai địa chỉ, hẹn giao lại."),
    sc("return_trip","Hoàn hàng",DriverTab.Orders,ScreenKind.NAV,true,"Điểm hoàn",Icons.Rounded.Route,"Route hoàn shop/kho nếu giao thất bại."),
    sc("batch_orders","Đơn trong chuyến",DriverTab.Orders,ScreenKind.ORDERS,false,"Xem hiện tại",Icons.Rounded.Assignment,"Trạng thái, COD, thu nhập từng đơn."),
    sc("reorder_route","Tối ưu tuyến",DriverTab.Orders,ScreenKind.NAV,true,"Tối ưu",Icons.Rounded.Route,"Driver yêu cầu; core quyết định thứ tự hợp lệ."),
    sc("order_detail","Chi tiết đơn",DriverTab.Orders,ScreenKind.ORDERS,false,"Mở timeline",Icons.Rounded.Assignment,"Mã đơn, shop, khách, hàng hóa, trạng thái."),
    sc("add_midtrip","Thêm đơn giữa chuyến",DriverTab.Orders,ScreenKind.OFFER,false,"Nhận thêm",Icons.Rounded.LocalShipping,"Core tìm đơn ghép gần tuyến hiện tại."),
    sc("wallet","Ví tài xế",DriverTab.Wallet,ScreenKind.WALLET,false,"Rút tiền",Icons.Rounded.AccountBalance,"Số dư, COD, bonus, phí nền tảng."),
    sc("transactions","Lịch sử giao dịch",DriverTab.Wallet,ScreenKind.WALLET,false,"Lọc hôm nay",Icons.Rounded.Payments,"Tiền đơn, thưởng, rút tiền, COD nộp về."),
    sc("daily_earning","Thu nhập ngày",DriverTab.Wallet,ScreenKind.WALLET,false,"Chi tiết",Icons.Rounded.Payments,"Tổng đơn, km, phí giao, thưởng, COD."),
    sc("withdraw","Rút tiền",DriverTab.Wallet,ScreenKind.FORM,false,"Xác nhận OTP",Icons.Rounded.AccountBalance,"Tài khoản ngân hàng, phí rút, OTP."),
    sc("cod_deposit","Nộp COD",DriverTab.Wallet,ScreenKind.FORM,false,"Đã nộp",Icons.Rounded.Payments,"QR chuyển khoản, cảnh báo quá hạn."),
    sc("history","Lịch sử đơn",DriverTab.Orders,ScreenKind.ORDERS,false,"Xem chuyến",Icons.Rounded.Assignment,"Đơn hoàn thành, hủy, hoàn, thu nhập."),
    sc("completed_trip","Chuyến đã hoàn thành",DriverTab.Orders,ScreenKind.ORDERS,true,"Xem route",Icons.Rounded.Route,"Tuyến, thời gian, thu nhập, đánh giá."),
    sc("performance","Hiệu suất",DriverTab.Profile,ScreenKind.PROFILE,false,"Xem tuần",Icons.Rounded.CheckCircle,"Tỷ lệ nhận, hủy, rating, đơn ghép."),
    sc("level","Cấp độ tài xế",DriverTab.Profile,ScreenKind.PROFILE,false,"Quyền lợi",Icons.Rounded.CheckCircle,"Đồng/Bạc/Vàng, điều kiện lên hạng."),
    sc("inbox","Inbox",DriverTab.Notifications,ScreenKind.NOTIFY,false,"Mở chat",Icons.Rounded.Chat,"Shop, khách, support."),
    sc("chat","Chat đơn hàng",DriverTab.Notifications,ScreenKind.NOTIFY,false,"Gửi tin",Icons.Rounded.Chat,"Tin nhắn mẫu, ảnh, vị trí."),
    sc("masked_call","Gọi ẩn số",DriverTab.Notifications,ScreenKind.NOTIFY,false,"Gọi",Icons.Rounded.Call,"Gọi khách/shop không lộ số thật."),
    sc("support","Trung tâm hỗ trợ",DriverTab.Profile,ScreenKind.SUPPORT,false,"Tạo ticket",Icons.Rounded.HelpCenter,"Đơn hàng, thanh toán, tài khoản, khẩn cấp."),
    sc("ticket","Ticket hỗ trợ",DriverTab.Profile,ScreenKind.SUPPORT,false,"Gửi ticket",Icons.Rounded.SupportAgent,"Chọn đơn, lý do, mô tả, ảnh."),
    sc("notification_center","Thông báo",DriverTab.Notifications,ScreenKind.NOTIFY,false,"Mở chi tiết",Icons.Rounded.Notifications,"Đơn mới, thưởng, COD, hệ thống."),
    sc("notification_detail","Chi tiết thông báo",DriverTab.Notifications,ScreenKind.NOTIFY,false,"Xem CTA",Icons.Rounded.Notifications,"Nội dung và hành động liên quan."),
    sc("profile","Hồ sơ tài xế",DriverTab.Profile,ScreenKind.PROFILE,false,"Cập nhật",Icons.Rounded.Person,"Rating, xe, giấy tờ, xác minh."),
    sc("personal_info","Thông tin cá nhân",DriverTab.Profile,ScreenKind.FORM,false,"Lưu",Icons.Rounded.Person,"Tên, email, số điện thoại, địa chỉ."),
    sc("vehicle","Phương tiện",DriverTab.Profile,ScreenKind.FORM,false,"Lưu xe",Icons.Rounded.DirectionsBike,"Loại xe, biển số, giấy tờ."),
    sc("bank","Tài khoản ngân hàng",DriverTab.Profile,ScreenKind.FORM,false,"Lưu ngân hàng",Icons.Rounded.AccountBalance,"Ngân hàng, số tài khoản, chủ tài khoản."),
    sc("settings","Cài đặt app",DriverTab.Profile,ScreenKind.PROFILE,false,"Mở bảo mật",Icons.Rounded.Settings,"Ngôn ngữ, âm thanh, rung, dark mode, định vị."),
    sc("security","Bảo mật",DriverTab.Profile,ScreenKind.FORM,false,"Đổi PIN",Icons.Rounded.Security,"PIN, Face ID, đăng xuất thiết bị."),
    sc("developer","Developer Demo Mode",DriverTab.Profile,ScreenKind.PROFILE,false,"Load demo",Icons.Rounded.Settings,"Reset world, OSRM debug, snap points, simulation speed."),
    sc("proof","Proof / OTP",DriverTab.Orders,ScreenKind.DROPOFF,false,"Xác minh",Icons.Rounded.CheckCircle,"Ảnh, OTP, ký nhận demo."),
    sc("unreachable","Không liên hệ được",DriverTab.Orders,ScreenKind.SUPPORT,false,"Bắt đầu timer",Icons.Rounded.CrisisAlert,"Call, message, timer, safe place/support."),
    sc("route_quality","Chất lượng batch",DriverTab.Orders,ScreenKind.ORDERS,true,"Fit batch",Icons.Rounded.Route,"Pickup cluster, dropoff corridor, detour saved.")
).associateBy { it.key }
private val roots = mapOf(DriverTab.Home to "home_online", DriverTab.Orders to "batch_orders", DriverTab.Wallet to "wallet", DriverTab.Notifications to "notification_center", DriverTab.Profile to "profile")

@Composable
private fun DriverApp(viewModel: DriverDemoViewModel = viewModel()) {
    val liveState by viewModel.state.collectAsState()
    val stack = remember { mutableStateListOf(S.getValue("home_offline")) }
    val current = stack.last()
    BackHandler(enabled = stack.size > 1) { stack.removeAt(stack.lastIndex) }
    LaunchedEffect(Unit) { viewModel.goOnline() }
    LaunchedEffect(liveState.phase) {
        if (stack.size == 1) stack[0] = when (liveState.phase) {
            DriverPhase.Offer -> S.getValue("offer")
            DriverPhase.ActiveTrip -> S.getValue("trip_overview")
            DriverPhase.Idle -> S.getValue("home_online")
            DriverPhase.Offline -> S.getValue("home_offline")
        }
    }
    MaterialTheme {
        Surface(Modifier.fillMaxSize(), color = GrabBg) {
            Box(Modifier.fillMaxSize()) {
                if (current.mapFirst) MapFirstScreen(current, stack, liveState, viewModel) else ContentScreen(current, stack, liveState, viewModel)
                if (stack.size == 1) BottomNav(current.tab, Modifier.align(Alignment.BottomCenter)) { tab -> stack.clear(); stack.add(S.getValue(roots.getValue(tab))) }
            }
        }
    }
}

@Composable
private fun MapFirstScreen(screen: DriverScreen, stack: MutableList<DriverScreen>, liveState: DriverDemoUiState, viewModel: DriverDemoViewModel) {
    Box(Modifier.fillMaxSize()) {
        RealDriverMap(liveState, Modifier.fillMaxSize())
        TopBar(screen.title, stack, Modifier.align(Alignment.TopCenter), showBack = stack.size > 1)
        FloatingMapTools(Modifier.align(Alignment.CenterEnd)) { stack.add(S.getValue("route_quality")) }
        BatchBottomCard(screen, liveState, Modifier.align(Alignment.BottomCenter), onPrimary = { handlePrimaryAction(screen, stack, liveState, viewModel) }, onSecondary = { viewModel.rejectAssignment(); stack.clear(); stack.add(S.getValue("home_online")) })
    }
}

@Composable
private fun RealDriverMap(liveState: DriverDemoUiState, modifier: Modifier = Modifier) {
    AndroidView(modifier = modifier, factory = { context -> MapLibreRouteView(context).apply { updateRoute(liveState.toMapRouteState()) } }, update = { it.updateRoute(liveState.toMapRouteState()) })
}

private fun DriverDemoUiState.toMapRouteState(): MapRouteState {
    val assignment = assignment
    val driver = (driverProjectedLocation ?: simulatedDriverLocation ?: assignment?.driverLocationAtAssignment)?.let { MapRoutePoint("DR", "driver", it.lat, it.lng, "Driver") }
    val current = assignment?.currentStep?.let { MapRoutePoint(it.label, it.type, it.location.lat, it.location.lng, it.title) }
    val route = (if (remainingGeometry.isNotEmpty()) remainingGeometry else roadGeometry).map { it.lat to it.lng }
    val done = completedGeometry.map { it.lat to it.lng }
    return MapRouteState(
        driver = driver,
        stops = listOfNotNull(current),
        remainingPolyline = route,
        completedPolyline = done,
        activeStepIndex = 0,
        geometryAvailable = roadGeometry.isNotEmpty(),
        followDriver = phase == DriverPhase.ActiveTrip,
        driverHeadingDeg = driverHeadingDeg,
        cameraMode = if (phase == DriverPhase.ActiveTrip) "FOLLOWING" else "OVERVIEW",
        snappedWaypoints = snappedWaypoints.map { MapSnappedWaypoint(it.label, it.raw.lat, it.raw.lng, it.snapped.lat, it.snapped.lng, it.distanceMeters) }
    )
}

@Composable
private fun TopBar(title: String, stack: MutableList<DriverScreen>, modifier: Modifier = Modifier, showBack: Boolean = true) {
    Row(modifier.fillMaxWidth().statusBarsPadding().padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
        if (showBack) {
            Surface(Modifier.size(44.dp).clickable { if (stack.size > 1) stack.removeAt(stack.lastIndex) }, shape = CircleShape, color = CardWhite, shadowElevation = 4.dp) { Box(contentAlignment = Alignment.Center) { Icon(Icons.AutoMirrored.Rounded.ArrowBack, "Back", tint = TextMain) } }
            Spacer(Modifier.width(10.dp))
        }
        Surface(shape = RoundedCornerShape(999.dp), color = CardWhite, shadowElevation = 4.dp) { Text(title, Modifier.padding(horizontal = 16.dp, vertical = 12.dp), color = TextMain, fontWeight = FontWeight.Black) }
    }
}

@Composable
private fun FloatingMapTools(modifier: Modifier, onPinMap: () -> Unit) {
    Column(modifier.padding(end = 14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        MapFab(Icons.Rounded.GpsFixed, "Định vị") {}
        MapFab(Icons.Rounded.PinDrop, "Pin map", onPinMap)
        MapFab(Icons.Rounded.HelpCenter, "Hỗ trợ") {}
    }
}

@Composable private fun MapFab(icon: ImageVector, label: String, onClick: () -> Unit) {
    Surface(Modifier.size(48.dp).clickable(onClick = onClick), shape = CircleShape, color = CardWhite, shadowElevation = 5.dp) { Box(contentAlignment = Alignment.Center) { Icon(icon, label, tint = GrabDark) } }
}

@Composable
private fun BatchBottomCard(screen: DriverScreen, liveState: DriverDemoUiState, modifier: Modifier, onPrimary: () -> Unit, onSecondary: () -> Unit) {
    val assignment = liveState.assignment
    val current = assignment?.currentStep
    Surface(modifier.fillMaxWidth().navigationBarsPadding().padding(horizontal = 12.dp, vertical = 10.dp), color = CardWhite, shape = RoundedCornerShape(topStart = 28.dp, topEnd = 28.dp, bottomStart = 24.dp, bottomEnd = 24.dp), shadowElevation = 10.dp) {
        Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(screen.icon, null, tint = GrabGreen, modifier = Modifier.size(30.dp)); Spacer(Modifier.width(10.dp))
                Column(Modifier.weight(1f)) {
                    Text(if (current != null) "${current.label} • ${current.title}" else screen.title, color = TextMain, fontSize = 18.sp, fontWeight = FontWeight.Black, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text(cardSubtitle(screen, liveState), color = TextMuted, fontSize = 13.sp, maxLines = 2, overflow = TextOverflow.Ellipsis)
                }
                StatusPill(liveState)
            }
            if (assignment != null) StopSequence(assignment.routePlan.sequence.mapIndexed { index, step -> Triple(step.label, step.type, index == assignment.currentStepIndex) })
            MetricsRow(liveState)
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Button(onClick = onSecondary, modifier = Modifier.weight(1f).height(52.dp), colors = ButtonDefaults.buttonColors(containerColor = GrabBg, contentColor = TextMain)) { Text("Bỏ qua") }
                Button(onClick = onPrimary, modifier = Modifier.weight(1.4f).height(52.dp), colors = ButtonDefaults.buttonColors(containerColor = GrabGreen)) { Text(screen.cta, fontWeight = FontWeight.Black) }
            }
        }
    }
}

private fun cardSubtitle(screen: DriverScreen, liveState: DriverDemoUiState): String = when {
    liveState.roadGeometryLoading -> "Đang tính đường tới stop hiện tại..."
    liveState.assignment != null -> liveState.roadGeometryLabel
    else -> screen.summary
}

@Composable private fun StatusPill(liveState: DriverDemoUiState) {
    val text = when (liveState.phase) { DriverPhase.Offline -> "OFF"; DriverPhase.Idle -> "ONLINE"; DriverPhase.Offer -> "OFFER"; DriverPhase.ActiveTrip -> "LIVE" }
    Surface(shape = RoundedCornerShape(999.dp), color = if (liveState.phase == DriverPhase.ActiveTrip) GrabGreen else GrabBg) { Text(text, Modifier.padding(horizontal = 10.dp, vertical = 6.dp), color = if (liveState.phase == DriverPhase.ActiveTrip) Color.White else GrabDark, fontSize = 11.sp, fontWeight = FontWeight.Black) }
}

@Composable private fun StopSequence(stops: List<Triple<String, String, Boolean>>) {
    Row(horizontalArrangement = Arrangement.spacedBy(7.dp)) { stops.take(6).forEach { stop -> Surface(shape = RoundedCornerShape(999.dp), color = if (stop.third) GrabGreen else GrabBg) { Text(stop.first, Modifier.padding(horizontal = 10.dp, vertical = 7.dp), color = if (stop.third) Color.White else TextMain, fontSize = 12.sp, fontWeight = FontWeight.Black) } } }
}

@Composable private fun MetricsRow(liveState: DriverDemoUiState) {
    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        Metric("ETA", "${(liveState.remainingDurationSeconds / 60).coerceAtLeast(1)} phút", Modifier.weight(1f))
        Metric("Còn lại", "${liveState.remainingDistanceMeters.coerceAtLeast(0)} m", Modifier.weight(1f))
        Metric("Tốc độ", "${liveState.simulatedSpeedKmh} km/h", Modifier.weight(1f))
    }
}

@Composable private fun Metric(label: String, value: String, modifier: Modifier = Modifier) {
    Column(modifier.clip(RoundedCornerShape(16.dp)).background(GrabBg).padding(10.dp), horizontalAlignment = Alignment.CenterHorizontally) { Text(label, color = TextMuted, fontSize = 11.sp); Text(value, color = TextMain, fontSize = 13.sp, fontWeight = FontWeight.Black) }
}

@Composable
private fun ContentScreen(screen: DriverScreen, stack: MutableList<DriverScreen>, liveState: DriverDemoUiState, viewModel: DriverDemoViewModel) {
    Column(Modifier.fillMaxSize().background(GrabBg).statusBarsPadding().navigationBarsPadding()) {
        TopBar(screen.title, stack, showBack = stack.size > 1)
        LazyColumn(Modifier.weight(1f), contentPadding = androidx.compose.foundation.layout.PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            item { HeroCard(screen, liveState) }
            item { when (screen.kind) {
                ScreenKind.PICKUP -> PickupWorkflow(liveState)
                ScreenKind.DROPOFF -> DropoffWorkflow(liveState)
                ScreenKind.WALLET -> WalletWorkflow()
                ScreenKind.ORDERS -> OrdersWorkflow(liveState, stack)
                ScreenKind.SUPPORT -> SupportWorkflow()
                ScreenKind.PROFILE -> ProfileWorkflow(stack)
                ScreenKind.NOTIFY -> NotifyWorkflow(stack)
                ScreenKind.FORM -> FormWorkflow(screen)
                else -> GenericWorkflow(screen)
            } }
            item { Button(onClick = { handlePrimaryAction(screen, stack, liveState, viewModel) }, Modifier.fillMaxWidth().height(54.dp), colors = ButtonDefaults.buttonColors(containerColor = GrabGreen)) { Text(screen.cta, fontWeight = FontWeight.Black) } }
        }
    }
}

@Composable private fun HeroCard(screen: DriverScreen, liveState: DriverDemoUiState) {
    Surface(color = CardWhite, shape = RoundedCornerShape(28.dp), shadowElevation = 2.dp) { Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) { Icon(screen.icon, null, tint = GrabGreen, modifier = Modifier.size(34.dp)); Spacer(Modifier.width(12.dp)); Column(Modifier.weight(1f)) { Text(screen.title, color = TextMain, fontSize = 22.sp, fontWeight = FontWeight.Black); Text(screen.summary, color = TextMuted) } }
        if (liveState.error != null) Text(liveState.error, color = Danger, fontWeight = FontWeight.Bold)
    } }
}

@Composable private fun PickupWorkflow(liveState: DriverDemoUiState) = InfoList(listOf("Shop" to (liveState.assignment?.currentStep?.title ?: "Cơm Gà Q1"), "Mã đơn" to "RF-1024", "Checklist" to "Đúng shop • đúng mã • đủ túi • đúng ghi chú", "Hành động" to "Đơn chưa sẵn sàng • Verify code • Đã nhận hàng"))
@Composable private fun DropoffWorkflow(liveState: DriverDemoUiState) = InfoList(listOf("Khách" to "Minh • 09xx xxx 164", "Địa chỉ" to (liveState.assignment?.currentStep?.title ?: "Office Tower B, Lobby"), "Ghi chú" to "Meet at door • gọi khi tới sảnh", "Bằng chứng" to "OTP / ảnh / COD nếu cần"))
@Composable private fun WalletWorkflow() = InfoList(listOf("Số dư" to "1.248.000đ", "Hôm nay" to "248.000đ • 6 chuyến", "COD" to "320.000đ cần nộp", "Breakdown" to "Base fare • batch bonus • tip • promotion"))
@Composable private fun SupportWorkflow() = InfoList(listOf("Khẩn cấp" to "Tai nạn/sự cố", "Đơn hàng" to "Shop đóng cửa, khách không nghe máy", "Thanh toán" to "COD, rút tiền, khấu trừ", "Ticket" to "Ảnh + mô tả + đơn liên quan"))
@Composable private fun FormWorkflow(screen: DriverScreen) = InfoList(listOf("Trạng thái" to "Sẵn sàng chỉnh sửa", "Touch target" to "48dp", "Lưu" to screen.cta))
@Composable private fun GenericWorkflow(screen: DriverScreen) = InfoList(listOf("Luồng" to screen.summary, "Nút nhanh" to "Pin map • Chat • Support", "Back" to "Mỗi trang có nút back rõ ràng"))

@Composable private fun OrdersWorkflow(liveState: DriverDemoUiState, stack: MutableList<DriverScreen>) {
    InfoList(listOf("Batch" to (liveState.assignment?.routePlan?.summary ?: "P1 → P2 → D2 → D1"), "Core chọn" to "Driver + orders + route sequence", "Chất lượng" to "Cluster tốt • corridor cùng hướng • detour thấp"))
    Spacer(Modifier.height(10.dp)); QuickRows(listOf("Điều hướng" to "nav_pickup", "Chi tiết đơn" to "order_detail", "Chất lượng batch" to "route_quality"), stack)
}

@Composable private fun ProfileWorkflow(stack: MutableList<DriverScreen>) {
    InfoList(listOf("Minh Driver" to "Rating 4.9 • Motorbike • Verified", "Giấy tờ" to "CCCD • GPLX • Đăng ký xe", "Cài đặt" to "Navigation • Notification • Developer"))
    Spacer(Modifier.height(10.dp)); QuickRows(listOf("Cài đặt" to "settings", "Bảo mật" to "security", "Developer Demo" to "developer"), stack)
}

@Composable private fun NotifyWorkflow(stack: MutableList<DriverScreen>) = QuickRows(listOf("Batch matching found" to "route_quality", "Core đã tối ưu tuyến" to "notification_detail", "COD cần nộp" to "cod_deposit", "Support phản hồi" to "ticket"), stack)

@Composable private fun InfoList(rows: List<Pair<String, String>>) { Column(verticalArrangement = Arrangement.spacedBy(10.dp)) { rows.forEach { InfoRow(it.first, it.second) } } }
@Composable private fun InfoRow(label: String, value: String) {
    Surface(color = CardWhite, shape = RoundedCornerShape(18.dp), shadowElevation = 1.dp) { Row(Modifier.fillMaxWidth().padding(14.dp), verticalAlignment = Alignment.CenterVertically) { Text(label, Modifier.width(110.dp), color = TextMuted, fontWeight = FontWeight.Bold); Text(value, Modifier.weight(1f), color = TextMain, fontWeight = FontWeight.Bold) } }
}

@Composable private fun QuickRows(rows: List<Pair<String, String>>, stack: MutableList<DriverScreen>) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) { rows.forEach { row -> Surface(Modifier.fillMaxWidth().clickable { stack.add(S.getValue(row.second)) }, color = CardWhite, shape = RoundedCornerShape(18.dp), shadowElevation = 1.dp) { Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) { Icon(Icons.Rounded.CheckCircle, null, tint = GrabGreen); Spacer(Modifier.width(12.dp)); Text(row.first, color = TextMain, fontWeight = FontWeight.Black) } } } }
}

@Composable
private fun BottomNav(current: DriverTab, modifier: Modifier = Modifier, onTab: (DriverTab) -> Unit) {
    NavigationBar(modifier.fillMaxWidth(), containerColor = CardWhite) { DriverTab.values().forEach { tab -> NavigationBarItem(selected = current == tab, onClick = { onTab(tab) }, icon = { Icon(tab.icon, tab.label) }, label = { Text(tab.label, fontSize = 11.sp) }) } }
}

@Composable
private fun FallbackMapPreview(title: String) {
    Box(Modifier.fillMaxWidth().height(210.dp).clip(RoundedCornerShape(26.dp)).background(Brush.linearGradient(listOf(Color(0xFFE7F8EE), Color(0xFFD7EEF9))))) {
        Canvas(Modifier.fillMaxSize()) { val route = Path().apply { moveTo(size.width * .12f, size.height * .78f); cubicTo(size.width * .28f, size.height * .25f, size.width * .58f, size.height * .92f, size.width * .88f, size.height * .22f) }; drawPath(route, GrabGreen, style = androidx.compose.ui.graphics.drawscope.Stroke(width = 10f)); drawCircle(GrabGreen, 16f, Offset(size.width * .18f, size.height * .72f)); drawCircle(Danger, 16f, Offset(size.width * .86f, size.height * .24f)) }
        Text(title, Modifier.align(Alignment.TopStart).padding(16.dp), color = TextMain, fontWeight = FontWeight.Black)
    }
}

private fun handlePrimaryAction(screen: DriverScreen, stack: MutableList<DriverScreen>, liveState: DriverDemoUiState, viewModel: DriverDemoViewModel) {
    when (screen.key) {
        "home_offline" -> viewModel.goOnline()
        "home_online" -> viewModel.goOffline()
        "offer", "offer_detail", "confirm_merge" -> { if (liveState.assignment == null) viewModel.loadLocalCoreDemo(); viewModel.acceptAssignment(); stack.clear(); stack.add(S.getValue("trip_overview")) }
        "trip_overview" -> stack.add(S.getValue("nav_pickup"))
        "nav_pickup", "nav_dropoff", "return_trip", "reorder_route", "route_quality", "hot_zone" -> viewModel.toggleDrivingSimulation()
        "pickup_arrived" -> stack.add(S.getValue("pickup_collect"))
        "pickup_collect" -> { viewModel.confirmPickedUp(); stack.add(S.getValue("nav_dropoff")) }
        "dropoff_arrived", "delivery_success", "proof" -> { viewModel.confirmDelivered(); stack.add(S.getValue("completed_trip")) }
        "delivery_failed" -> stack.add(S.getValue("return_trip"))
        "unreachable" -> viewModel.markCustomerUnreachable()
        "developer" -> viewModel.loadLocalCoreDemo()
        else -> stack.add(nextScreen(screen))
    }
}

private fun nextScreen(screen: DriverScreen): DriverScreen {
    val flow = listOf("offer_detail", "confirm_merge", "trip_overview", "nav_pickup", "pickup_arrived", "pickup_collect", "nav_dropoff", "dropoff_arrived", "delivery_success", "completed_trip")
    val index = flow.indexOf(screen.key)
    return if (index >= 0 && index < flow.lastIndex) S.getValue(flow[index + 1]) else S.getValue(roots.getValue(screen.tab))
}
