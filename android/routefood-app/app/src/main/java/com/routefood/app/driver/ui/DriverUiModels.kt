package com.routefood.app.driver.ui

import androidx.compose.runtime.Immutable
import com.routefood.app.driver.model.DriverAssignmentDemo
import com.routefood.app.driver.model.DriverLatLng

@Immutable
internal data class DriverMapRenderState(
    val assignment: DriverAssignmentDemo?,
    val driverLocation: DriverLatLng?,
    val navigationMode: Boolean,
)
