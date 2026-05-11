package com.routefood.app.core.map

import android.content.Context
import android.graphics.Color
import android.util.AttributeSet
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.pow
import kotlin.math.sin
import kotlin.math.sqrt
import org.maplibre.android.camera.CameraPosition
import org.maplibre.android.camera.CameraUpdateFactory
import org.maplibre.android.geometry.LatLng
import org.maplibre.android.geometry.LatLngBounds
import org.maplibre.android.maps.MapView
import org.maplibre.android.maps.MapLibreMapOptions
import org.maplibre.android.maps.MapLibreMap
import org.maplibre.android.maps.Style
import org.maplibre.android.style.expressions.Expression.get
import org.maplibre.android.style.layers.CircleLayer
import org.maplibre.android.style.layers.LineLayer
import org.maplibre.android.style.layers.Property
import org.maplibre.android.style.layers.PropertyFactory.circleBlur
import org.maplibre.android.style.layers.PropertyFactory.circleColor
import org.maplibre.android.style.layers.PropertyFactory.circleOpacity
import org.maplibre.android.style.layers.PropertyFactory.circleRadius
import org.maplibre.android.style.layers.PropertyFactory.circleStrokeColor
import org.maplibre.android.style.layers.PropertyFactory.circleStrokeOpacity
import org.maplibre.android.style.layers.PropertyFactory.circleStrokeWidth
import org.maplibre.android.style.layers.PropertyFactory.lineCap
import org.maplibre.android.style.layers.PropertyFactory.lineColor
import org.maplibre.android.style.layers.PropertyFactory.lineJoin
import org.maplibre.android.style.layers.PropertyFactory.lineOpacity
import org.maplibre.android.style.layers.PropertyFactory.lineWidth
import org.maplibre.android.style.layers.PropertyFactory.textAllowOverlap
import org.maplibre.android.style.layers.PropertyFactory.textColor
import org.maplibre.android.style.layers.PropertyFactory.textField
import org.maplibre.android.style.layers.PropertyFactory.textHaloColor
import org.maplibre.android.style.layers.PropertyFactory.textHaloWidth
import org.maplibre.android.style.layers.PropertyFactory.textIgnorePlacement
import org.maplibre.android.style.layers.PropertyFactory.textRotationAlignment
import org.maplibre.android.style.layers.PropertyFactory.textRotate
import org.maplibre.android.style.layers.PropertyFactory.textSize
import org.maplibre.android.style.layers.SymbolLayer
import org.maplibre.android.style.sources.GeoJsonSource
import org.maplibre.geojson.Feature
import org.maplibre.geojson.FeatureCollection
import org.maplibre.geojson.LineString
import org.maplibre.geojson.Point

data class MapRoutePoint(
    val label: String,
    val type: String,
    val lat: Double,
    val lng: Double,
    val title: String
)

data class MapRouteState(
    val driver: MapRoutePoint?,
    val stops: List<MapRoutePoint>,
    val polyline: List<Pair<Double, Double>>,
    val activeStepIndex: Int,
    val geometryAvailable: Boolean,
    val followDriver: Boolean = false,
    val driverHeadingDeg: Double = 0.0
)

class MapLibreRouteView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null
) : MapView(context, safe2dMapOptions(context, attrs)) {
    private var map: MapLibreMap? = null
    private var pendingState: MapRouteState? = null
    private var fittedInitialRoute = false
    private var lastActiveStepIndex = -1
    private var lastRenderSignature: String? = null
    private var lastCameraTarget: Pair<Double, Double>? = null

    init {
        onCreate(null)
        getMapAsync { mapLibreMap ->
            map = mapLibreMap
            mapLibreMap.uiSettings.isCompassEnabled = true
            mapLibreMap.uiSettings.isZoomGesturesEnabled = true
            mapLibreMap.uiSettings.isScrollGesturesEnabled = true
            mapLibreMap.uiSettings.isRotateGesturesEnabled = false
            mapLibreMap.uiSettings.isTiltGesturesEnabled = false
            mapLibreMap.setStyle(Style.Builder().fromJson(SAFE_2D_RASTER_STYLE)) {
                pendingState?.let { render(it) }
            }
        }
    }

    fun updateRoute(state: MapRouteState) {
        pendingState = state
        val currentMap = map ?: return
        val style = currentMap.style ?: return
        if (!style.isFullyLoaded) return
        render(state)
    }

    fun fitRoute() {
        map?.setPadding(56, 170, 56, 520)
        pendingState?.let { fitBounds(it) }
    }

    fun zoomIn() {
        map?.animateCamera(CameraUpdateFactory.zoomIn())
    }

    fun zoomOut() {
        map?.animateCamera(CameraUpdateFactory.zoomOut())
    }

    private fun render(state: MapRouteState) {
        val currentMap = map ?: return
        val style = currentMap.style ?: return
        val signature = renderSignature(state)
        if (signature != lastRenderSignature) {
            renderRouteLine(style, state)
            renderMarkers(style, state)
            lastRenderSignature = signature
        }
        updateCamera(state)
    }

    private fun renderSignature(state: MapRouteState): String {
        val driver = state.driver
        val driverCell = driver?.let { "${(it.lat * 300000).toInt()},${(it.lng * 300000).toInt()}" } ?: "none"
        return buildString {
            append(driverCell)
            append('|').append(state.activeStepIndex)
            append('|').append(state.geometryAvailable)
            append('|').append(state.followDriver)
            append('|').append(state.driverHeadingDeg.toInt())
            append('|').append(state.polyline.size)
            state.polyline.firstOrNull()?.let { append('|').append(it.first).append(',').append(it.second) }
            state.polyline.lastOrNull()?.let { append('|').append(it.first).append(',').append(it.second) }
            append('|').append(state.stops.size)
        }
    }

    private fun renderRouteLine(style: Style, state: MapRouteState) {
        val points = routePoints(state)
        val progress = if (state.followDriver) splitRouteProgress(points, state.driver) else RouteProgress(emptyList(), points)
        val remainingLine = routeLine(progress.remaining)
        val traveledLine = routeLine(progress.traveled)
        val remainingSource = style.getSourceAs<GeoJsonSource>(ROUTE_SOURCE_ID)
        if (remainingSource == null) {
            style.addSource(GeoJsonSource(ROUTE_TRAVELED_SOURCE_ID, traveledLine))
            style.addSource(GeoJsonSource(ROUTE_SOURCE_ID, remainingLine))
            style.addLayer(
                LineLayer(ROUTE_OUTLINE_LAYER_ID, ROUTE_SOURCE_ID).withProperties(
                    lineColor("#06111D"),
                    lineWidth(10f),
                    lineOpacity(0.82f),
                    lineCap(Property.LINE_CAP_ROUND),
                    lineJoin(Property.LINE_JOIN_MITER)
                )
            )
            style.addLayer(
                LineLayer(ROUTE_TRAVELED_LAYER_ID, ROUTE_TRAVELED_SOURCE_ID).withProperties(
                    lineColor("#64748B"),
                    lineWidth(6.5f),
                    lineOpacity(0.58f),
                    lineCap(Property.LINE_CAP_ROUND),
                    lineJoin(Property.LINE_JOIN_MITER)
                )
            )
            style.addLayer(
                LineLayer(ROUTE_LAYER_ID, ROUTE_SOURCE_ID).withProperties(
                    lineColor(if (state.geometryAvailable) "#18D674" else "#28C7FF"),
                    lineWidth(6.5f),
                    lineOpacity(0.96f),
                    lineCap(Property.LINE_CAP_ROUND),
                    lineJoin(Property.LINE_JOIN_MITER)
                )
            )
        } else {
            remainingSource.setGeoJson(remainingLine)
            style.getSourceAs<GeoJsonSource>(ROUTE_TRAVELED_SOURCE_ID)?.setGeoJson(traveledLine)
        }
    }

    private fun routeLine(points: List<Pair<Double, Double>>): FeatureCollection {
        if (points.size < 2) return FeatureCollection.fromFeatures(emptyArray())
        val safePoints = points
        return FeatureCollection.fromFeature(
            Feature.fromGeometry(LineString.fromLngLats(safePoints.map { Point.fromLngLat(it.second, it.first) }))
        )
    }

    private fun renderMarkers(style: Style, state: MapRouteState) {
        ensureMarkerLayers(style)
        upsertSource(style, DRIVER_SOURCE_ID, driverFeatures(state))
        upsertSource(style, PICKUP_SOURCE_ID, features(state.stops.filter { !it.type.equals("dropoff", true) }))
        upsertSource(style, DROPOFF_SOURCE_ID, features(state.stops.filter { it.type.equals("dropoff", true) }))
        upsertSource(style, ACTIVE_SOURCE_ID, features(state.stops.getOrNull(state.activeStepIndex)?.let { listOf(it) }.orEmpty()))
    }

    private fun ensureMarkerLayers(style: Style) {
        addCircleLayer(style, DRIVER_SHADOW_LAYER_ID, DRIVER_SOURCE_ID, "#06111D", 24f, 0f, opacity = 0.42f, blur = 0.2f)
        addCircleLayer(style, DRIVER_DOT_LAYER_ID, DRIVER_SOURCE_ID, "#18D674", 11f, 3.2f)
        addDriverArrowLayer(style)
        addLabelLayer(style, DRIVER_LABEL_LAYER_ID, DRIVER_SOURCE_ID, 12f, "#052E1A", "#FFFFFF")
        addCircleLayer(style, PICKUP_HALO_LAYER_ID, PICKUP_SOURCE_ID, "#FFFFFF", 18f, 0f, opacity = 0.82f, blur = 0.04f)
        addCircleLayer(style, DROPOFF_HALO_LAYER_ID, DROPOFF_SOURCE_ID, "#FFFFFF", 18f, 0f, opacity = 0.82f, blur = 0.04f)
        addCircleLayer(style, PICKUP_LAYER_ID, PICKUP_SOURCE_ID, "#FF8B26", 14f, 3.2f)
        addCircleLayer(style, DROPOFF_LAYER_ID, DROPOFF_SOURCE_ID, "#EF4444", 14f, 3.2f)
        addCircleLayer(style, ACTIVE_RING_LAYER_ID, ACTIVE_SOURCE_ID, "#18D674", 27f, 2f, opacity = 0.28f, blur = 0.18f)
        addCircleLayer(style, ACTIVE_LAYER_ID, ACTIVE_SOURCE_ID, "#111827", 17f, 4f)
        addLabelLayer(style, STOP_LABEL_LAYER_ID, PICKUP_SOURCE_ID, 12.5f, "#FFFFFF", "#7C2D12")
        addLabelLayer(style, DROPOFF_LABEL_LAYER_ID, DROPOFF_SOURCE_ID, 12.5f, "#FFFFFF", "#7F1D1D")
        addLabelLayer(style, ACTIVE_LABEL_LAYER_ID, ACTIVE_SOURCE_ID, 13.5f, "#FFFFFF", "#052E1A")
    }

    private fun addCircleLayer(
        style: Style,
        layerId: String,
        sourceId: String,
        color: String,
        radius: Float,
        strokeWidth: Float,
        opacity: Float = 0.96f,
        blur: Float = 0f
    ) {
        if (style.getLayer(layerId) != null) return
        ensureEmptySource(style, sourceId)
        style.addLayer(
            CircleLayer(layerId, sourceId).withProperties(
                circleColor(color),
                circleRadius(radius),
                circleOpacity(opacity),
                circleBlur(blur),
                circleStrokeWidth(strokeWidth),
                circleStrokeColor("#FFFFFF"),
                circleStrokeOpacity(0.96f)
            )
        )
    }

    private fun addLabelLayer(
        style: Style,
        layerId: String,
        sourceId: String,
        size: Float,
        color: String,
        haloColor: String
    ) {
        if (style.getLayer(layerId) != null) return
        ensureEmptySource(style, sourceId)
        style.addLayer(
            SymbolLayer(layerId, sourceId).withProperties(
                textField(get("label")),
                textSize(size),
                textColor(color),
                textHaloColor(haloColor),
                textHaloWidth(1.6f),
                textAllowOverlap(true),
                textIgnorePlacement(true)
            )
        )
    }

    private fun addDriverArrowLayer(style: Style) {
        if (style.getLayer(DRIVER_LAYER_ID) != null) return
        ensureEmptySource(style, DRIVER_SOURCE_ID)
        style.addLayer(
            SymbolLayer(DRIVER_LAYER_ID, DRIVER_SOURCE_ID).withProperties(
                textField(get("arrow")),
                textRotate(get("bearing")),
                textRotationAlignment(Property.ICON_ROTATION_ALIGNMENT_MAP),
                textSize(38f),
                textColor("#052E1A"),
                textHaloColor("#18D674"),
                textHaloWidth(3.2f),
                textAllowOverlap(true),
                textIgnorePlacement(true)
            )
        )
    }

    private fun ensureEmptySource(style: Style, sourceId: String) {
        if (style.getSourceAs<GeoJsonSource>(sourceId) == null) {
            style.addSource(GeoJsonSource(sourceId, FeatureCollection.fromFeatures(emptyArray())))
        }
    }

    private fun upsertSource(style: Style, sourceId: String, featureCollection: FeatureCollection) {
        val source = style.getSourceAs<GeoJsonSource>(sourceId)
        if (source == null) {
            style.addSource(GeoJsonSource(sourceId, featureCollection))
        } else {
            source.setGeoJson(featureCollection)
        }
    }

    private fun features(points: List<MapRoutePoint>): FeatureCollection {
        return FeatureCollection.fromFeatures(points.map { point ->
            Feature.fromGeometry(Point.fromLngLat(point.lng, point.lat)).also { feature ->
                feature.addStringProperty("label", point.label)
                feature.addStringProperty("title", point.title)
                feature.addStringProperty("type", point.type)
            }
        })
    }

    private fun driverFeatures(state: MapRouteState): FeatureCollection {
        val driver = state.driver ?: return FeatureCollection.fromFeatures(emptyArray())
        val bearing = state.driverHeadingDeg.takeIf { state.followDriver } ?: bearingFromRoute(routePoints(state), driver, state.stops.getOrNull(state.activeStepIndex))
        val feature = Feature.fromGeometry(Point.fromLngLat(driver.lng, driver.lat)).also { feature ->
            feature.addStringProperty("label", driver.label)
            feature.addStringProperty("arrow", "▲")
            feature.addStringProperty("title", driver.title)
            feature.addStringProperty("type", driver.type)
            feature.addNumberProperty("bearing", bearing)
        }
        return FeatureCollection.fromFeature(feature)
    }

    private fun fitBounds(state: MapRouteState) {
        val points = mutableListOf<LatLng>()
        state.driver?.let { points.add(LatLng(it.lat, it.lng)) }
        state.stops.forEach { points.add(LatLng(it.lat, it.lng)) }
        if (points.isEmpty()) return
        val builder = LatLngBounds.Builder()
        points.forEach { builder.include(it) }
        map?.setPadding(56, 170, 56, 520)
        map?.animateCamera(CameraUpdateFactory.newLatLngBounds(builder.build(), 56, 170, 56, 520), 650)
    }

    private fun updateCamera(state: MapRouteState) {
        val shouldFit = !fittedInitialRoute || lastActiveStepIndex != state.activeStepIndex
        if (!state.followDriver) {
            if (shouldFit) fitBounds(state)
            fittedInitialRoute = true
            lastActiveStepIndex = state.activeStepIndex
            return
        }
        val driver = state.driver ?: return
        val driverPoint = driver.lat to driver.lng
        val target = lookAheadTarget(routePoints(state), driverPoint, 110.0)
        val cameraMovedEnough = lastCameraTarget?.let { distanceMeters(it, target) >= 3.0 } ?: true
        if (!shouldFit && !cameraMovedEnough) return
        map?.setPadding(0, 150, 0, 430)
        val cameraPosition = CameraPosition.Builder()
            .target(LatLng(target.first, target.second))
            .zoom(17.0)
            .tilt(0.0)
            .bearing(0.0)
            .build()
        map?.easeCamera(CameraUpdateFactory.newCameraPosition(cameraPosition), 260)
        lastCameraTarget = target
        fittedInitialRoute = true
        lastActiveStepIndex = state.activeStepIndex
    }

    private fun lookAheadTarget(
        route: List<Pair<Double, Double>>,
        driverPoint: Pair<Double, Double>,
        lookAheadMeters: Double
    ): Pair<Double, Double> {
        if (route.size < 2) return driverPoint
        val projection = projectPointOnRoute(driverPoint, route)
        var current = projection.point
        var remaining = lookAheadMeters
        for (index in projection.segmentEndIndex until route.size) {
            val next = route[index]
            val segmentMeters = distanceMeters(current, next)
            if (segmentMeters >= remaining && segmentMeters > 0.1) {
                val ratio = remaining / segmentMeters
                return (current.first + (next.first - current.first) * ratio) to
                    (current.second + (next.second - current.second) * ratio)
            }
            remaining -= segmentMeters
            current = next
        }
        return route.last()
    }

    private fun routePoints(state: MapRouteState): List<Pair<Double, Double>> {
        if (state.polyline.size >= 2) return state.polyline
        if (!state.geometryAvailable) return emptyList()
        return buildList {
            state.driver?.let { add(it.lat to it.lng) }
            state.stops.forEach { add(it.lat to it.lng) }
        }
    }

    private data class RouteProgress(
        val traveled: List<Pair<Double, Double>>,
        val remaining: List<Pair<Double, Double>>
    )

    private data class RouteProjection(
        val segmentStartIndex: Int,
        val segmentEndIndex: Int,
        val point: Pair<Double, Double>,
        val distanceMeters: Double
    )

    private fun splitRouteProgress(points: List<Pair<Double, Double>>, driver: MapRoutePoint?): RouteProgress {
        if (points.size < 2 || driver == null) return RouteProgress(emptyList(), points)
        val driverPoint = driver.lat to driver.lng
        val projection = projectPointOnRoute(driverPoint, points)
        val traveled = (points.take(projection.segmentStartIndex + 1) + projection.point).distinctConsecutive()
        val remaining = (listOf(projection.point) + points.drop(projection.segmentEndIndex)).distinctConsecutive()
        return RouteProgress(traveled, remaining)
    }

    private fun List<Pair<Double, Double>>.distinctConsecutive(): List<Pair<Double, Double>> {
        if (isEmpty()) return this
        val result = mutableListOf<Pair<Double, Double>>()
        forEach { point ->
            if (result.lastOrNull() != point) result.add(point)
        }
        return result
    }

    private fun bearingFromRoute(points: List<Pair<Double, Double>>, driver: MapRoutePoint, fallbackTarget: MapRoutePoint? = null): Double {
        if (points.size < 2) return fallbackTarget?.let { bearingDegrees(driver.lat to driver.lng, it.lat to it.lng) } ?: 0.0
        val driverPoint = driver.lat to driver.lng
        val projection = projectPointOnRoute(driverPoint, points)
        val next = points.drop(projection.segmentEndIndex).firstOrNull { distanceMeters(projection.point, it) > 8.0 }
            ?: points.getOrNull(projection.segmentEndIndex.coerceAtMost(points.lastIndex))
            ?: fallbackTarget?.let { return bearingDegrees(driver.lat to driver.lng, it.lat to it.lng) }
            ?: return 0.0
        return bearingDegrees(projection.point, next)
    }

    private fun projectPointOnRoute(
        point: Pair<Double, Double>,
        route: List<Pair<Double, Double>>
    ): RouteProjection {
        var best = RouteProjection(0, 1, route.first(), distanceMeters(route.first(), point))
        for (index in 0 until route.lastIndex) {
            val projected = projectPointOnSegment(point, route[index], route[index + 1])
            val distance = distanceMeters(projected, point)
            if (distance < best.distanceMeters) {
                best = RouteProjection(index, index + 1, projected, distance)
            }
        }
        return best
    }

    private fun projectPointOnSegment(
        point: Pair<Double, Double>,
        start: Pair<Double, Double>,
        end: Pair<Double, Double>
    ): Pair<Double, Double> {
        val originLat = point.first
        val metersPerLng = 111_320.0 * cos(Math.toRadians(originLat))
        val sx = (start.second - point.second) * metersPerLng
        val sy = (start.first - point.first) * 111_320.0
        val ex = (end.second - point.second) * metersPerLng
        val ey = (end.first - point.first) * 111_320.0
        val dx = ex - sx
        val dy = ey - sy
        val lengthSquared = dx * dx + dy * dy
        if (lengthSquared == 0.0) return start
        val t = ((-sx * dx) + (-sy * dy)) / lengthSquared
        val clamped = t.coerceIn(0.0, 1.0)
        val px = sx + clamped * dx
        val py = sy + clamped * dy
        return (point.first + py / 111_320.0) to (point.second + px / metersPerLng)
    }

    private fun distanceMeters(a: Pair<Double, Double>, b: Pair<Double, Double>): Double {
        val latMeters = (a.first - b.first) * 111_320.0
        val lngMeters = (a.second - b.second) * 111_320.0 * cos(Math.toRadians((a.first + b.first) / 2.0))
        return sqrt(latMeters.pow(2) + lngMeters.pow(2))
    }

    private fun bearingDegrees(from: Pair<Double, Double>, to: Pair<Double, Double>): Double {
        val fromLat = Math.toRadians(from.first)
        val toLat = Math.toRadians(to.first)
        val deltaLng = Math.toRadians(to.second - from.second)
        val y = sin(deltaLng) * cos(toLat)
        val x = cos(fromLat) * sin(toLat) - sin(fromLat) * cos(toLat) * cos(deltaLng)
        return (Math.toDegrees(atan2(y, x)) + 360.0) % 360.0
    }

    companion object {
        private fun safe2dMapOptions(context: Context, attrs: AttributeSet?): MapLibreMapOptions {
            return MapLibreMapOptions.createFromAttributes(context, attrs)
                .textureMode(true)
                .translucentTextureSurface(false)
                .tiltGesturesEnabled(false)
                .rotateGesturesEnabled(false)
                .minPitchPreference(0.0)
                .maxPitchPreference(0.0)
        }

        private const val SAFE_2D_RASTER_STYLE = """
            {
              "version": 8,
              "name": "RouteFood 2D Light",
              "sources": {
                "carto-light": {
                  "type": "raster",
                  "tiles": ["https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png"],
                  "tileSize": 256,
                  "attribution": "Â© OpenStreetMap contributors Â© CARTO"
                }
              },
              "layers": [
                {
                  "id": "carto-light-layer",
                  "type": "raster",
                  "source": "carto-light",
                  "minzoom": 0,
                  "maxzoom": 20
                }
              ]
            }
        """
        private const val ROUTE_SOURCE_ID = "routefood-route-source"
        private const val ROUTE_TRAVELED_SOURCE_ID = "routefood-route-traveled-source"
        private const val ROUTE_OUTLINE_LAYER_ID = "routefood-route-outline"
        private const val ROUTE_TRAVELED_LAYER_ID = "routefood-route-traveled-line"
        private const val ROUTE_LAYER_ID = "routefood-route-line"
        private const val DRIVER_SOURCE_ID = "routefood-driver-source"
        private const val PICKUP_SOURCE_ID = "routefood-pickup-source"
        private const val DROPOFF_SOURCE_ID = "routefood-dropoff-source"
        private const val ACTIVE_SOURCE_ID = "routefood-active-source"
        private const val DRIVER_SHADOW_LAYER_ID = "routefood-driver-shadow-layer"
        private const val DRIVER_DOT_LAYER_ID = "routefood-driver-dot-layer"
        private const val DRIVER_LAYER_ID = "routefood-driver-layer"
        private const val DRIVER_LABEL_LAYER_ID = "routefood-driver-label-layer"
        private const val PICKUP_HALO_LAYER_ID = "routefood-pickup-halo-layer"
        private const val DROPOFF_HALO_LAYER_ID = "routefood-dropoff-halo-layer"
        private const val PICKUP_LAYER_ID = "routefood-pickup-layer"
        private const val DROPOFF_LAYER_ID = "routefood-dropoff-layer"
        private const val ACTIVE_RING_LAYER_ID = "routefood-active-ring-layer"
        private const val ACTIVE_LAYER_ID = "routefood-active-layer"
        private const val STOP_LABEL_LAYER_ID = "routefood-stop-label-layer"
        private const val DROPOFF_LABEL_LAYER_ID = "routefood-dropoff-label-layer"
        private const val ACTIVE_LABEL_LAYER_ID = "routefood-active-label-layer"
    }
}

