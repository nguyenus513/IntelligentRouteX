package com.routefood.app.compose.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.Icon
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.routefood.app.compose.core.designsystem.CardShape
import com.routefood.app.compose.core.designsystem.Cream
import com.routefood.app.compose.core.designsystem.GlassSurface
import com.routefood.app.compose.core.designsystem.Leaf
import com.routefood.app.compose.core.designsystem.Muted
import com.routefood.app.compose.core.designsystem.PillShape

@Composable
fun RouteFoodHeroHeader(query: String, onQuery: (String) -> Unit) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clip(androidx.compose.foundation.shape.RoundedCornerShape(bottomStart = 34.dp, bottomEnd = 34.dp))
            .background(Brush.verticalGradient(listOf(Color(0xFF0D4B32), Color(0xFF1B7249))))
            .padding(start = 14.dp, end = 14.dp, top = 48.dp, bottom = 24.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp)
    ) {
        GlassSurface(Modifier.fillMaxWidth(), radius = 14.dp, strong = true) {
            OutlinedTextField(
                value = query,
                onValueChange = onQuery,
                modifier = Modifier.fillMaxWidth().height(54.dp),
                shape = androidx.compose.foundation.shape.RoundedCornerShape(14.dp),
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = Color.Transparent,
                    unfocusedBorderColor = Color.Transparent,
                    focusedContainerColor = Color.Transparent,
                    unfocusedContainerColor = Color.Transparent,
                    focusedTextColor = Color.White,
                    unfocusedTextColor = Color.White
                ),
                leadingIcon = { Icon(Icons.Default.Search, null) },
                placeholder = { Text("Search places", color = Color.White.copy(alpha = .72f)) },
                singleLine = true
            )
        }
        Text("DELIVER TO", color = Color.White.copy(alpha = .72f), fontSize = 12.sp, fontWeight = FontWeight.Bold)
        Text("Vinhomes Grand Park - The Beverly", color = Color.White, fontSize = 17.sp, fontWeight = FontWeight.Black, maxLines = 1, overflow = TextOverflow.Ellipsis)
        Text("Äáº¡i chiáº¿n bÃ¡nh mÃ¬", color = Color.White, fontSize = 22.sp, fontWeight = FontWeight.Black)
        Text("RouteFood Deal giáº£m 50% hÃ´m nay â†’", color = Color.White.copy(alpha = .84f), fontWeight = FontWeight.Bold)
    }
}

@Composable
fun RouteFoodEmptyState(title: String, subtitle: String) {
    GlassSurface(strong = true) {
        Column(Modifier.fillMaxWidth().padding(28.dp)) {
            Text(title, fontWeight = FontWeight.Black, fontSize = 20.sp)
            Text(subtitle, color = Muted)
        }
    }
}

@Composable
fun RouteFoodSectionTitle(title: String, subtitle: String) {
    Column(verticalArrangement = Arrangement.spacedBy(3.dp)) {
        Text(title, fontSize = 23.sp, fontWeight = FontWeight.Black, color = Cream)
        Text(subtitle, color = Muted, fontSize = 13.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

@Composable
fun RouteFoodGlassPill(text: String) {
    GlassSurface(radius = 999.dp, strong = true) {
        Text(text, modifier = Modifier.padding(horizontal = 14.dp, vertical = 9.dp), color = Muted, fontWeight = FontWeight.Bold, fontSize = 13.sp)
    }
}


