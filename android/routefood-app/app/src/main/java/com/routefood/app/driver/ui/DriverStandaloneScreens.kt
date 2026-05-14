package com.routefood.app.driver.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import com.routefood.app.driver.DriverDemoUiState

@Composable
internal fun DriverStandaloneScreen(state: DriverDemoUiState) {
    Column(Modifier.fillMaxWidth()) {
        Text("Driver app refactor active")
        Text("Phase: ${state.phase}")
        Text("Online: ${state.online}")
    }
}


