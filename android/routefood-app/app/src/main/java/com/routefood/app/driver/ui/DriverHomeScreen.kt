package com.routefood.app.driver.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import com.routefood.app.driver.DriverDemoUiState

@Composable
internal fun DriverHomeScreen(state: DriverDemoUiState) {
    DriverHomeScreenLegacy(state)
}

@Composable
internal fun DriverHomeScreenLegacy(state: DriverDemoUiState) {
    Column {
        Text("Driver demo refactor in progress")
        Text("Online: ${state.online}")
        Text("Assignment: ${state.assignment?.assignmentCode ?: "none"}")
        Text("Phase: ${state.phase}")
    }
}
