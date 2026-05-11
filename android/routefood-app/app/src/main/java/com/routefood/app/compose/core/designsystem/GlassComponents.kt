package com.routefood.app.compose.core.designsystem

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

@Composable
fun LiquidBackground(content: @Composable BoxScope.() -> Unit) {
    Box(
        Modifier
            .fillMaxSize()
            .background(
                Brush.verticalGradient(
                    listOf(Color(0xFFFFFCF7), Color(0xFFFFF5EA), Color(0xFFF6EFE4))
                )
            )
    ) {
        Box(
            Modifier
                .fillMaxSize()
                .background(Brush.radialGradient(listOf(GlowGreen, Color.Transparent), radius = 860f))
        )
        Box(
            Modifier
                .fillMaxSize()
                .background(Brush.radialGradient(listOf(GlowOrange, Color.Transparent), radius = 980f))
        )
        content()
    }
}

@Composable
fun GlassSurface(
    modifier: Modifier = Modifier,
    radius: Dp = 28.dp,
    strong: Boolean = false,
    content: @Composable () -> Unit
) {
    val shape = RoundedCornerShape(radius)
    Card(
        modifier = modifier
            .clip(shape)
            .border(BorderStroke(1.dp, GlassStroke), shape),
        shape = shape,
        colors = CardDefaults.cardColors(containerColor = if (strong) GlassStrong else Glass)
    ) {
        Box(
            Modifier.background(
                Brush.verticalGradient(
                    listOf(Color.White.copy(alpha = .10f), Color.White.copy(alpha = .025f))
                )
            )
        ) { content() }
    }
}
