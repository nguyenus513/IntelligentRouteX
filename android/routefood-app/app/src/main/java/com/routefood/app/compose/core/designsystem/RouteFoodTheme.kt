package com.routefood.app.compose.core.designsystem

import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

val Cream = Color(0xFFFFF8EE)
val Surface = Color(0xFFFFFEFB)
val Elevated = Color(0xFFF7EEE2)
val Ink = Color(0xFF191714)
val Muted = Color(0xFF7D7067)
val Leaf = Color(0xFF0C9B63)
val Orange = Color(0xFFFF7A1A)
val Tomato = Color(0xFFE95142)
val Gold = Color(0xFFFFC857)
val Glass = Color(0xB3FFFFFF)
val GlassStrong = Color(0xE6FFFFFF)
val GlassStroke = Color(0x80FFFFFF)
val GlowGreen = Color(0x330C9B63)
val GlowOrange = Color(0x33FF7A1A)

val CardShape = RoundedCornerShape(26.dp)
val PillShape = RoundedCornerShape(999.dp)

private val colors = lightColorScheme(
    primary = Leaf,
    onPrimary = Color.White,
    secondary = Orange,
    tertiary = Tomato,
    background = Cream,
    onBackground = Ink,
    surface = Surface,
    onSurface = Ink,
    surfaceVariant = Elevated,
    onSurfaceVariant = Muted
)

private val typography = Typography(
    displayLarge = TextStyle(fontFamily = FontFamily.SansSerif, fontWeight = FontWeight.ExtraBold, fontSize = 38.sp, lineHeight = 42.sp),
    headlineLarge = TextStyle(fontFamily = FontFamily.SansSerif, fontWeight = FontWeight.ExtraBold, fontSize = 30.sp, lineHeight = 34.sp),
    titleLarge = TextStyle(fontFamily = FontFamily.SansSerif, fontWeight = FontWeight.Bold, fontSize = 20.sp, lineHeight = 24.sp),
    titleMedium = TextStyle(fontFamily = FontFamily.SansSerif, fontWeight = FontWeight.SemiBold, fontSize = 16.sp, lineHeight = 20.sp),
    bodyMedium = TextStyle(fontFamily = FontFamily.SansSerif, fontWeight = FontWeight.Medium, fontSize = 14.sp, lineHeight = 19.sp),
    labelMedium = TextStyle(fontFamily = FontFamily.SansSerif, fontWeight = FontWeight.SemiBold, fontSize = 12.sp, lineHeight = 15.sp)
)

@Composable
fun RouteFoodTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = colors, typography = typography, content = content)
}
