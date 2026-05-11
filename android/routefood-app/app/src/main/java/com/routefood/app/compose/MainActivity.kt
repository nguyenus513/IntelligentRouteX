package com.routefood.app.compose

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.wrapContentHeight
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AccountCircle
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.LocalOffer
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.ShoppingBag
import androidx.compose.material.icons.filled.ShoppingCart
import androidx.compose.material.icons.filled.Star
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Badge
import androidx.compose.material3.BadgedBox
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import coil.compose.AsyncImage
import com.routefood.app.compose.core.data.FoodSeedData
import com.routefood.app.compose.core.designsystem.CardShape
import com.routefood.app.compose.core.designsystem.Cream
import com.routefood.app.compose.core.designsystem.Elevated
import com.routefood.app.compose.core.designsystem.Gold
import com.routefood.app.compose.core.designsystem.GlassSurface
import com.routefood.app.compose.core.designsystem.Leaf
import com.routefood.app.compose.core.designsystem.LiquidBackground
import com.routefood.app.compose.core.designsystem.Muted
import com.routefood.app.compose.core.designsystem.Orange
import com.routefood.app.compose.core.designsystem.PillShape
import com.routefood.app.compose.core.designsystem.RouteFoodTheme
import com.routefood.app.compose.core.model.CartItem
import com.routefood.app.compose.core.model.MenuItem
import com.routefood.app.compose.core.model.Order
import com.routefood.app.compose.core.model.PaymentMethod
import com.routefood.app.compose.core.model.RecommendedFood
import com.routefood.app.compose.core.model.Restaurant
import com.routefood.app.compose.core.model.Voucher

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent { RouteFoodTheme { RouteFoodApp() } }
    }
}

private enum class Tab { Home, Search, Orders, Offers, Profile }

@Composable
private fun CompactNavItem(tab: Tab, selected: Boolean, modifier: Modifier = Modifier, onClick: () -> Unit) {
    val tint = if (selected) MaterialTheme.colorScheme.onSurface else Muted
    Column(
        modifier.clickable { onClick() }.padding(vertical = 6.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(2.dp)
    ) {
        Box(
            Modifier
                .size(width = 46.dp, height = 28.dp)
                .clip(PillShape)
                .background(if (selected) Color(0xFFEADCFD) else Color.Transparent),
            contentAlignment = Alignment.Center
        ) {
            when (tab) {
                Tab.Home -> Icon(Icons.Default.Home, null, tint = tint, modifier = Modifier.size(20.dp))
                Tab.Search -> Icon(Icons.Default.Search, null, tint = tint, modifier = Modifier.size(20.dp))
                Tab.Orders -> Icon(Icons.Default.ShoppingBag, null, tint = tint, modifier = Modifier.size(20.dp))
                Tab.Offers -> Icon(Icons.Default.LocalOffer, null, tint = tint, modifier = Modifier.size(20.dp))
                Tab.Profile -> Icon(Icons.Default.AccountCircle, null, tint = tint, modifier = Modifier.size(20.dp))
            }
        }
        Text(
            if (tab == Tab.Home) "Home" else if (tab == Tab.Search) "Search" else if (tab == Tab.Orders) "Orders" else if (tab == Tab.Offers) "Offers" else "Profile",
            fontSize = 10.sp,
            color = tint,
            fontWeight = if (selected) FontWeight.Black else FontWeight.SemiBold,
            maxLines = 1
        )
    }
}

@Composable
fun RouteFoodApp(viewModel: RouteFoodViewModel = viewModel()) {
    val state by viewModel.state.collectAsState()
    var selectedTab by remember { mutableStateOf(Tab.Home) }
    var selectedRestaurant by remember { mutableStateOf<Restaurant?>(null) }
    var selectedFood by remember { mutableStateOf<MenuItem?>(null) }
    var showCart by remember { mutableStateOf(false) }
    var confirmation by remember { mutableStateOf<Order?>(null) }

    Scaffold(
        containerColor = Cream,
        bottomBar = {
            GlassSurface(
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 6.dp).fillMaxWidth().height(70.dp),
                radius = 28.dp,
                strong = true
            ) {
                Row(Modifier.fillMaxSize().padding(horizontal = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                Tab.values().forEach { tab ->
                    CompactNavItem(tab, selectedTab == tab, Modifier.weight(1f)) { selectedTab = tab }
                }
            }
            }
        },
        floatingActionButton = { FloatingCartBar(state, onClick = { showCart = true }) }
    ) { padding ->
        LiquidBackground {
        Box(Modifier.padding(padding).fillMaxSize()) {
            when (selectedTab) {
                Tab.Home -> HomeScreen(state, viewModel, onRestaurant = { selectedRestaurant = it }, onFood = { selectedFood = it })
                Tab.Search -> SearchScreen(state, viewModel, onRestaurant = { selectedRestaurant = it }, onFood = { selectedFood = it })
                Tab.Orders -> OrdersScreen(state.orders)
                Tab.Offers -> OffersScreen(state.selectedVoucher, viewModel::applyVoucher)
                Tab.Profile -> ProfileScreen()
            }
        }
        }
    }

    selectedRestaurant?.let { restaurant ->
        RestaurantDetailScreen(
            restaurant = restaurant,
            items = state.menuItems.filter { it.restaurantId == restaurant.id },
            onBack = { selectedRestaurant = null },
            onFood = { selectedFood = it }
        )
    }
    selectedFood?.let { food -> FoodSheet(food, onDismiss = { selectedFood = null }, onAdd = { qty, toppings, note -> viewModel.addToCart(food, qty, toppings, note); selectedFood = null }) }
    if (showCart) CartSheet(state, viewModel, onDismiss = { showCart = false }, onPlaced = { order -> confirmation = order; showCart = false; selectedTab = Tab.Orders })
    confirmation?.let { OrderSuccessSheet(it, onDismiss = { confirmation = null }) }
}
@Composable
private fun HomeScreen(state: RouteFoodUiState, viewModel: RouteFoodViewModel, onRestaurant: (Restaurant) -> Unit, onFood: (MenuItem) -> Unit) {
    val recommendationSections = viewModel.homeRecommendationSections()
    LazyColumn(contentPadding = PaddingValues(bottom = 120.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) {
        item { HomeHeroHeader(state.query, viewModel::updateQuery) }
        item { ServiceGrid() }
        item { WalletMiniCard() }
        item { PromoCarousel("Order now", state.restaurants.take(4), onRestaurant) }
        item { PaddedBlock { CategoryRow() } }
        items(recommendationSections) { section ->
            PaddedBlock { RecommendationFoodSection(section.title, section.subtitle, section.items, onFood) }
        }
    }
}

@Composable
private fun HomeHeroHeader(query: String, onQuery: (String) -> Unit) {
    Box(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(bottomStart = 34.dp, bottomEnd = 34.dp))
            .background(Brush.verticalGradient(listOf(Color(0xFF0D4B32), Color(0xFF1B7249))))
            .padding(start = 14.dp, end = 14.dp, top = 48.dp, bottom = 24.dp)
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Box(Modifier.size(36.dp).clip(CircleShape).background(Color.White.copy(alpha = .18f)), contentAlignment = Alignment.Center) { Text("⌗", color = Color.White, fontWeight = FontWeight.Black) }
                GlassSurface(Modifier.weight(1f), radius = 14.dp, strong = true) {
                    OutlinedTextField(
                        value = query,
                        onValueChange = onQuery,
                        modifier = Modifier.fillMaxWidth().height(54.dp),
                        shape = RoundedCornerShape(14.dp),
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedBorderColor = Color.Transparent,
                            unfocusedBorderColor = Color.Transparent,
                            focusedContainerColor = Color.Transparent,
                            unfocusedContainerColor = Color.Transparent,
                            focusedTextColor = MaterialTheme.colorScheme.onSurface,
                            unfocusedTextColor = MaterialTheme.colorScheme.onSurface
                        ),
                        leadingIcon = { Icon(Icons.Default.Search, null) },
                        placeholder = { Text("Search places") },
                        singleLine = true
                    )
                }
                Box(Modifier.size(42.dp).clip(CircleShape).background(Color(0xFFFFC24B)), contentAlignment = Alignment.Center) { Text("RF", color = Color.White, fontWeight = FontWeight.Black, fontSize = 13.sp) }
                Box(Modifier.size(42.dp).clip(CircleShape).background(Color.White), contentAlignment = Alignment.Center) { Text("👤") }
            }
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceBetween) {
                Column(Modifier.weight(1f)) {
                    Text("DELIVER TO", color = Color.White.copy(.72f), fontSize = 12.sp, fontWeight = FontWeight.Bold)
                    Text("Vinhomes Grand Park - The Beverly", color = Color.White, fontSize = 17.sp, fontWeight = FontWeight.Black, maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) { CircleGlassButton("♡"); CircleGlassButton("▣") }
            }
            Text("Đại chiến bánh mì", color = Color.White, fontSize = 22.sp, fontWeight = FontWeight.Black)
            Text("RouteFood Deal giảm 50% hôm nay  →", color = Color.White.copy(.84f), fontWeight = FontWeight.Bold)
        }
    }
}

@Composable
private fun CircleGlassButton(label: String) {
    Box(Modifier.size(42.dp).clip(CircleShape).background(Color.White.copy(alpha = .20f)), contentAlignment = Alignment.Center) { Text(label, color = Color.White, fontWeight = FontWeight.Black) }
}

@Composable
private fun PaddedBlock(content: @Composable () -> Unit) {
    Box(Modifier.padding(horizontal = 14.dp)) { content() }
}

@Composable
private fun ServiceGrid() {
    val services = listOf("🏍️" to "Bike", "🚘" to "Car", "🍔" to "Food", "📦" to "Express", "🍽️" to "Dine Out", "🛒" to "Mart", "🚗" to "Ride later", "▦" to "All")
    Column(Modifier.padding(horizontal = 14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        services.chunked(4).forEach { row -> Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) { row.forEach { (icon, label) -> ServiceTile(icon, label, Modifier.weight(1f)) } } }
    }
}

@Composable
private fun ServiceTile(icon: String, label: String, modifier: Modifier = Modifier) {
    Card(
        modifier = modifier.height(82.dp).clickable { },
        shape = RoundedCornerShape(22.dp),
        colors = CardDefaults.cardColors(containerColor = Color.White.copy(alpha = .96f)),
        elevation = CardDefaults.cardElevation(defaultElevation = 5.dp)
    ) {
        Column(
            Modifier.fillMaxSize().padding(10.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center
        ) {
            Box(
                Modifier.size(36.dp).clip(CircleShape).background(Color(0xFFEAF8F2)),
                contentAlignment = Alignment.Center
            ) { Text(icon, fontSize = 20.sp) }
            Spacer(Modifier.height(7.dp))
            Text(label, fontWeight = FontWeight.ExtraBold, fontSize = 11.sp, maxLines = 1, color = MaterialTheme.colorScheme.onSurface)
        }
    }
}

@Composable
private fun WalletMiniCard() {
    GlassSurface(Modifier.padding(horizontal = 14.dp).width(158.dp), radius = 14.dp, strong = true) {
        Row(Modifier.padding(12.dp), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) { Column { Text("View", color = Muted, fontSize = 11.sp); Text("RoutePay", fontWeight = FontWeight.Black) }; Text("RF", color = Color.White, modifier = Modifier.clip(CircleShape).background(Leaf).padding(5.dp), fontSize = 11.sp, fontWeight = FontWeight.Black) }
    }
}

@Composable
private fun PromoCarousel(title: String, restaurants: List<Restaurant>, onRestaurant: (Restaurant) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 14.dp), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) { Text(title, fontSize = 20.sp, fontWeight = FontWeight.Black); Box(Modifier.size(28.dp).clip(CircleShape).background(Color(0xFFEAF8F2)), contentAlignment = Alignment.Center) { Text("›", color = Leaf, fontWeight = FontWeight.Black) } }
        LazyRow(contentPadding = PaddingValues(horizontal = 14.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) { items(restaurants) { restaurant -> PromoCard(restaurant, onRestaurant) } }
    }
}

@Composable
private fun PromoCard(restaurant: Restaurant, onRestaurant: (Restaurant) -> Unit) {
    Card(
        Modifier.width(316.dp).height(244.dp).clickable { onRestaurant(restaurant) },
        shape = RoundedCornerShape(28.dp),
        colors = CardDefaults.cardColors(containerColor = Color.White),
        elevation = CardDefaults.cardElevation(defaultElevation = 8.dp)
    ) {
        Column(Modifier.fillMaxSize()) {
            Box(Modifier.fillMaxWidth().height(154.dp)) {
                AsyncImage(restaurant.coverUrl, null, Modifier.fillMaxSize(), contentScale = ContentScale.Crop)
                Box(
                    Modifier.padding(12.dp).clip(PillShape).background(Color.White.copy(alpha = .92f)).padding(horizontal = 10.dp, vertical = 6.dp)
                ) { Text(restaurant.promoLabel ?: "RouteFood Deal", color = Leaf, fontWeight = FontWeight.Black, fontSize = 12.sp) }
            }
            Column(Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 10.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                Text(restaurant.name, fontWeight = FontWeight.Black, fontSize = 17.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text("${restaurant.cuisine} - ${restaurant.etaMin} phut - ${restaurant.distanceKm}km", color = Muted, fontSize = 12.sp, maxLines = 1)
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                    Text("${restaurant.rating} sao", color = Gold, fontWeight = FontWeight.Black, fontSize = 12.sp)
                    Box(Modifier.size(30.dp).clip(CircleShape).background(Leaf), contentAlignment = Alignment.Center) { Text("+", color = Color.White, fontWeight = FontWeight.Black) }
                }
            }
        }
    }
}

@Composable
private fun SearchBox(value: String, onChange: (String) -> Unit) {
    GlassSurface(radius = 999.dp, strong = true) {
        OutlinedTextField(
            value = value,
            onValueChange = onChange,
            modifier = Modifier.fillMaxWidth(),
            shape = PillShape,
            colors = OutlinedTextFieldDefaults.colors(
                focusedBorderColor = Leaf,
                unfocusedBorderColor = Color.Transparent,
                focusedContainerColor = Color.Transparent,
                unfocusedContainerColor = Color.Transparent,
                focusedTextColor = MaterialTheme.colorScheme.onSurface,
                unfocusedTextColor = MaterialTheme.colorScheme.onSurface
            ),
            leadingIcon = { Icon(Icons.Default.Search, null) },
            placeholder = { Text("Tìm món, quán, trà sữa, cơm trưa...") },
            singleLine = true
        )
    }
}

@Composable
private fun PromoHero() {
    GlassSurface(radius = 34.dp, strong = true) {
        Box(Modifier.background(Brush.linearGradient(listOf(Leaf, Orange))).padding(22.dp)) {
            Column(Modifier.fillMaxWidth()) {
                Text("Lunch Intelligence", color = Color.White.copy(.82f), fontWeight = FontWeight.Bold)
                Text("AI chọn món trưa hợp thời tiết, gần bạn và đang có voucher", color = Color.White, fontSize = 28.sp, lineHeight = 32.sp, fontWeight = FontWeight.Black)
                Spacer(Modifier.height(12.dp))
                AssistChip(onClick = {}, label = { Text("Giảm đến 30K hôm nay") }, leadingIcon = { Icon(Icons.Default.LocalOffer, null) })
            }
        }
    }
}

@Composable
private fun CategoryRow() {
    val categories = listOf("Cơm", "Mì / Phở", "Trà sữa", "Gà rán", "Pizza", "Healthy", "Lẩu")
    LazyRow(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        items(categories) { category -> AssistChip(onClick = {}, label = { Text(category, fontWeight = FontWeight.Bold) }) }
    }
}

@Composable
private fun RestaurantSection(title: String, subtitle: String, restaurants: List<Restaurant>, onRestaurant: (Restaurant) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        SectionTitle(title, subtitle)
        LazyRow(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
            items(restaurants) { RestaurantCard(it, onRestaurant) }
        }
    }
}

@Composable
private fun FoodSection(title: String, items: List<MenuItem>, onFood: (MenuItem) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        SectionTitle(title, "Best seller, combo và món hợp thời điểm")
        LazyRow(horizontalArrangement = Arrangement.spacedBy(14.dp)) { items(items) { FoodCard(it, onFood) } }
    }
}

@Composable
private fun RecommendationFoodSection(title: String, subtitle: String, items: List<RecommendedFood>, onFood: (MenuItem) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        SectionTitle(title, subtitle)
        LazyRow(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
            items(items) { recommended -> FoodCard(recommended.item, onFood, recommended.reason) }
        }
    }
}

@Composable
private fun SectionTitle(title: String, subtitle: String) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
            Text(title, fontSize = 23.sp, fontWeight = FontWeight.Black, color = MaterialTheme.colorScheme.onSurface)
            Text(subtitle, color = Muted, fontSize = 13.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        Box(Modifier.clip(PillShape).background(Color(0xFFEAF8F2)).padding(horizontal = 12.dp, vertical = 8.dp)) {
            Text("Xem them", color = Leaf, fontWeight = FontWeight.Black, fontSize = 12.sp)
        }
    }
}

@Composable
private fun FloatingCartBar(state: RouteFoodUiState, onClick: () -> Unit) {
    if (state.cart.isEmpty()) return
    Card(
        modifier = Modifier.padding(horizontal = 12.dp, vertical = 70.dp).width(268.dp).clickable { onClick() },
        shape = PillShape,
        colors = CardDefaults.cardColors(containerColor = Color.White),
        elevation = CardDefaults.cardElevation(defaultElevation = 12.dp)
    ) {
        Row(
            Modifier.padding(horizontal = 12.dp, vertical = 9.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Box(Modifier.size(32.dp).clip(CircleShape).background(Leaf), contentAlignment = Alignment.Center) {
                Text(state.cart.sumOf { it.quantity }.toString(), color = Color.White, fontWeight = FontWeight.Black, fontSize = 13.sp)
            }
            Column(Modifier.weight(1f)) {
                Text("Gio hang", fontWeight = FontWeight.Black, fontSize = 13.sp)
                Text("${state.cart.sumOf { it.quantity }} items - ${state.total.money()}", color = Muted, fontSize = 10.sp)
            }
            Text("?", color = Leaf, fontSize = 22.sp, fontWeight = FontWeight.Black)
        }
    }
}

@Composable
private fun RestaurantCard(restaurant: Restaurant, onClick: (Restaurant) -> Unit) {
    Card(
        Modifier.width(262.dp).height(256.dp).clickable { onClick(restaurant) },
        shape = RoundedCornerShape(28.dp),
        colors = CardDefaults.cardColors(containerColor = Color.White),
        elevation = CardDefaults.cardElevation(defaultElevation = 7.dp)
    ) {
        Column(Modifier.fillMaxSize()) {
            Box(Modifier.fillMaxWidth().height(138.dp)) {
                AsyncImage(restaurant.coverUrl, null, Modifier.fillMaxSize(), contentScale = ContentScale.Crop)
                restaurant.promoLabel?.let {
                    Box(Modifier.padding(10.dp).clip(PillShape).background(Orange).padding(horizontal = 9.dp, vertical = 5.dp)) {
                        Text(it, color = Color.White, fontWeight = FontWeight.Black, fontSize = 11.sp)
                    }
                }
            }
            Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(7.dp)) {
                Text(restaurant.name, fontWeight = FontWeight.Black, fontSize = 18.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text(restaurant.cuisine, color = Muted, fontSize = 13.sp, maxLines = 1)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Default.Star, null, tint = Gold, modifier = Modifier.size(17.dp))
                    Text("${restaurant.rating} - ${restaurant.etaMin} phut - ${restaurant.distanceKm}km", color = Muted, fontSize = 12.sp)
                }
            }
        }
    }
}

@Composable
private fun FoodCard(item: MenuItem, onClick: (MenuItem) -> Unit, reason: String? = null) {
    val restaurant = FoodSeedData.restaurants.firstOrNull { it.id == item.restaurantId }
    Card(
        Modifier.width(198.dp).height(302.dp).clickable { onClick(item) },
        shape = RoundedCornerShape(30.dp),
        colors = CardDefaults.cardColors(containerColor = Color.White),
        elevation = CardDefaults.cardElevation(defaultElevation = 8.dp)
    ) {
        Column(Modifier.fillMaxSize()) {
            Box(Modifier.fillMaxWidth().height(136.dp)) {
                AsyncImage(item.imageUrl, null, Modifier.fillMaxSize(), contentScale = ContentScale.Crop)
                Box(Modifier.padding(10.dp).clip(PillShape).background(Color.White.copy(alpha = .92f)).padding(horizontal = 9.dp, vertical = 5.dp)) {
                    Text(reason ?: "RouteFood Pick", color = Leaf, fontSize = 11.sp, fontWeight = FontWeight.Black, maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
            }
            Column(
                Modifier.fillMaxWidth().weight(1f).padding(13.dp),
                verticalArrangement = Arrangement.spacedBy(6.dp)
            ) {
                Text(item.name, fontWeight = FontWeight.Black, fontSize = 16.sp, maxLines = 2, overflow = TextOverflow.Ellipsis)
                restaurant?.let { Text(it.name, color = Muted, fontSize = 12.sp, maxLines = 1, overflow = TextOverflow.Ellipsis) }
                Text(item.price.money(), color = Leaf, fontWeight = FontWeight.Black, fontSize = 17.sp)
                Text("${item.rating} sao - da ban ${item.soldCount}", color = Muted, fontSize = 11.sp, maxLines = 1)
                Spacer(Modifier.weight(1f))
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                    Text("${restaurant?.etaMin ?: 25} phut", color = Muted, fontSize = 12.sp, fontWeight = FontWeight.Bold)
                    Box(Modifier.size(34.dp).clip(CircleShape).background(Leaf), contentAlignment = Alignment.Center) {
                        Text("+", color = Color.White, fontWeight = FontWeight.Black, fontSize = 18.sp)
                    }
                }
            }
        }
    }
}

@Composable
private fun SearchScreen(state: RouteFoodUiState, viewModel: RouteFoodViewModel, onRestaurant: (Restaurant) -> Unit, onFood: (MenuItem) -> Unit) {
    val restaurants = state.restaurants.filter { it.name.contains(state.query, true) || it.tags.any { tag -> tag.contains(state.query, true) } || state.query.isBlank() }
    LazyColumn(contentPadding = PaddingValues(bottom = 112.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item { SearchResultHeader(state.query, viewModel::updateQuery) }
        item { SearchCategoryCircles() }
        item { SearchFilterChips() }
        item { SearchPromoStrip() }
        items(restaurants) { RestaurantResultRow(it, onRestaurant) }
        if (restaurants.isEmpty()) item { PaddedBlock { EmptyState("No matching places", "Try noodles, rice, seafood or coffee.") } }
    }
}

@Composable
private fun SearchResultHeader(query: String, onQuery: (String) -> Unit) {
    Row(Modifier.fillMaxWidth().padding(start = 14.dp, end = 14.dp, top = 48.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        Text("‹", fontSize = 30.sp, fontWeight = FontWeight.Light)
        GlassSurface(Modifier.weight(1f), radius = 8.dp, strong = true) {
            OutlinedTextField(
                value = query,
                onValueChange = onQuery,
                modifier = Modifier.fillMaxWidth().height(48.dp),
                shape = RoundedCornerShape(8.dp),
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = Color.Transparent,
                    unfocusedBorderColor = Color.Transparent,
                    focusedContainerColor = Color.Transparent,
                    unfocusedContainerColor = Color.Transparent
                ),
                leadingIcon = { Icon(Icons.Default.Search, null) },
                placeholder = { Text("What shall we deliver?") },
                singleLine = true
            )
        }
    }
}

@Composable
private fun SearchCategoryCircles() {
    val categories = listOf("🍜" to "Noodles\n& Congee", "🍚" to "Rice", "🦐" to "Seafood", "🍛" to "Others", "🧋" to "Coffee - Tea\n- Juice")
    LazyRow(contentPadding = PaddingValues(horizontal = 14.dp), horizontalArrangement = Arrangement.spacedBy(18.dp)) {
        items(categories) { (icon, label) ->
            Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.width(72.dp)) {
                Box(Modifier.size(58.dp).clip(CircleShape).background(Color.White), contentAlignment = Alignment.Center) { Text(icon, fontSize = 28.sp) }
                Text(label, fontSize = 11.sp, fontWeight = FontWeight.SemiBold, lineHeight = 13.sp)
            }
        }
    }
}

@Composable
private fun SearchFilterChips() {
    LazyRow(contentPadding = PaddingValues(horizontal = 14.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        items(listOf("⚙", "↕ Sort By", "🏍 Under 18.000đ", "⚡ Under 30 min")) {
            GlassSurface(radius = 999.dp, strong = true) { Text(it, modifier = Modifier.padding(horizontal = 14.dp, vertical = 9.dp), color = Muted, fontWeight = FontWeight.Bold, fontSize = 13.sp) }
        }
    }
}

@Composable
private fun SearchPromoStrip() {
    Box(Modifier.padding(horizontal = 14.dp).fillMaxWidth().clip(RoundedCornerShape(8.dp)).background(Color(0xFFFFF4D8)).padding(10.dp)) {
        Text("Tiết kiệm đến 12.000đ phí giao với RouteFood Plus  →", color = Color(0xFF7A5A18), fontWeight = FontWeight.Bold, fontSize = 12.sp)
    }
}

@Composable
private fun RestaurantResultRow(restaurant: Restaurant, onClick: (Restaurant) -> Unit) {
    Row(Modifier.fillMaxWidth().clickable { onClick(restaurant) }.padding(horizontal = 14.dp, vertical = 4.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        Box {
            AsyncImage(restaurant.coverUrl, null, Modifier.size(112.dp).clip(RoundedCornerShape(10.dp)), contentScale = ContentScale.Crop)
            Text("50%", color = Color.White, fontSize = 12.sp, fontWeight = FontWeight.Black, modifier = Modifier.align(Alignment.BottomStart).background(Leaf).padding(horizontal = 8.dp, vertical = 3.dp))
        }
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(5.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(restaurant.name, fontWeight = FontWeight.Black, fontSize = 16.sp, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                Text("🏅", fontSize = 13.sp)
            }
            Text("★ ${restaurant.rating} (${(restaurant.popularity * 100).toInt()}+) · $$$ · ${restaurant.cuisine}", color = Muted, fontSize = 12.sp, maxLines = 1)
            Text("🛵 Free ₫${restaurant.deliveryFee} · From ${restaurant.etaMin} mins", color = Orange, fontSize = 12.sp, fontWeight = FontWeight.Bold)
            LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                items(listOf("12.000đ off", "19.000đ min", "Hot")) { chip ->
                    Box(Modifier.clip(RoundedCornerShape(12.dp)).background(Color.White).padding(horizontal = 10.dp, vertical = 8.dp)) { Text(chip, fontSize = 11.sp, fontWeight = FontWeight.Bold, color = Muted) }
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun RestaurantDetailScreen(restaurant: Restaurant, items: List<MenuItem>, onBack: () -> Unit, onFood: (MenuItem) -> Unit) {
    Surface(Modifier.fillMaxSize(), color = Cream) {
        LazyColumn(verticalArrangement = Arrangement.spacedBy(16.dp)) {
            item {
                Box {
                    AsyncImage(restaurant.coverUrl, null, Modifier.fillMaxWidth().height(260.dp), contentScale = ContentScale.Crop)
                    IconButton(onClick = onBack, modifier = Modifier.padding(18.dp).clip(CircleShape).background(Elevated)) { Icon(Icons.Default.ArrowBack, null, tint = MaterialTheme.colorScheme.onSurface) }
                }
            }
            item { Column(Modifier.padding(horizontal = 20.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) { Text(restaurant.name, fontSize = 34.sp, fontWeight = FontWeight.Black); Text("${restaurant.cuisine} - ${restaurant.rating} sao - ${restaurant.etaMin} phút - ${restaurant.deliveryFee.money()}", color = Muted); LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) { items(restaurant.tags) { AssistChip(onClick = {}, label = { Text(it) }) } } } }
            item { SectionTitle("Best seller", "Những món được đặt nhiều nhất") }
            items(items) { FoodListRow(it, onFood) }
            item { Spacer(Modifier.height(96.dp)) }
        }
    }
}

@Composable
private fun FoodListRow(item: MenuItem, onClick: (MenuItem) -> Unit) {
    GlassSurface(Modifier.padding(horizontal = 20.dp).fillMaxWidth().clickable { onClick(item) }, strong = true) {
        Row(Modifier.padding(12.dp), horizontalArrangement = Arrangement.spacedBy(14.dp)) {
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(8.dp)) { Text(item.name, fontWeight = FontWeight.Black, fontSize = 18.sp); Text(item.description, color = Muted, maxLines = 2); Text(item.price.money(), color = Leaf, fontWeight = FontWeight.Black) }
            AsyncImage(item.imageUrl, null, Modifier.size(110.dp).clip(CardShape), contentScale = ContentScale.Crop)
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun FoodSheet(food: MenuItem, onDismiss: () -> Unit, onAdd: (Int, List<String>, String) -> Unit) {
    var quantity by remember { mutableStateOf(1) }
    var note by remember { mutableStateOf("") }
    var toppings by remember { mutableStateOf(setOf<String>()) }
    ModalBottomSheet(onDismissRequest = onDismiss, containerColor = MaterialTheme.colorScheme.surface.copy(alpha = .96f)) {
        LazyColumn(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            item { AsyncImage(food.imageUrl, null, Modifier.fillMaxWidth().height(220.dp).clip(CardShape), contentScale = ContentScale.Crop) }
            item { Text(food.name, fontSize = 28.sp, fontWeight = FontWeight.Black); Text(food.description, color = Muted); Text(food.price.money(), color = Leaf, fontWeight = FontWeight.Black, fontSize = 22.sp) }
            item { Text("Topping", fontWeight = FontWeight.Black); LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) { items(food.toppings.ifEmpty { listOf("Ít cay", "Thêm sốt", "Không hành") }) { topping -> FilterChip(selected = topping in toppings, onClick = { toppings = if (topping in toppings) toppings - topping else toppings + topping }, label = { Text(topping) }) } } }
            item { OutlinedTextField(note, { note = it }, Modifier.fillMaxWidth(), label = { Text("Ghi chú cho quán") }, shape = CardShape) }
            item { Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) { QuantityControl(quantity, { quantity = it }); Button(onClick = { onAdd(quantity, toppings.toList(), note) }, shape = PillShape) { Text("Thêm - ${(food.price * quantity).money()}") } } }
            item { Spacer(Modifier.height(20.dp)) }
        }
    }
}

@Composable
private fun QuantityControl(quantity: Int, onChange: (Int) -> Unit) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) { OutlinedButton(onClick = { onChange((quantity - 1).coerceAtLeast(1)) }, shape = CircleShape) { Text("-") }; Text(quantity.toString(), fontWeight = FontWeight.Black, fontSize = 18.sp); OutlinedButton(onClick = { onChange(quantity + 1) }, shape = CircleShape) { Text("+") } }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun CartSheet(state: RouteFoodUiState, viewModel: RouteFoodViewModel, onDismiss: () -> Unit, onPlaced: (Order) -> Unit) {
    ModalBottomSheet(onDismissRequest = onDismiss, containerColor = MaterialTheme.colorScheme.surface.copy(alpha = .96f)) {
        LazyColumn(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            item { Text("Giỏ hàng", fontSize = 30.sp, fontWeight = FontWeight.Black) }
            if (state.cart.isEmpty()) item { EmptyState("Giỏ hàng trống", "Thêm món ngon trước khi checkout.") }
            items(state.cart) { CartRow(it, viewModel) }
            item { VoucherChooser(state.selectedVoucher, viewModel::applyVoucher) }
            item { PaymentChooser(state.selectedPayment, viewModel::selectPayment) }
            item { PriceBreakdown(state) }
            item { Button(enabled = state.cart.isNotEmpty(), onClick = { viewModel.placeOrder()?.let(onPlaced) }, modifier = Modifier.fillMaxWidth().height(54.dp), shape = PillShape) { Text("Đặt đơn - ${state.total.money()}", fontWeight = FontWeight.Black) } }
            item { Spacer(Modifier.height(24.dp)) }
        }
    }
}

@Composable
private fun CartRow(item: CartItem, viewModel: RouteFoodViewModel) {
    GlassSurface(strong = true) { Row(Modifier.padding(12.dp), horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) { AsyncImage(item.menuItem.imageUrl, null, Modifier.size(72.dp).clip(CardShape), contentScale = ContentScale.Crop); Column(Modifier.weight(1f)) { Text(item.menuItem.name, fontWeight = FontWeight.Black); Text(item.lineTotal.money(), color = Leaf, fontWeight = FontWeight.Bold); if (item.note.isNotBlank()) Text(item.note, color = Muted, fontSize = 12.sp) }; QuantityControl(item.quantity) { viewModel.updateQuantity(item.menuItem.id, it) } } }
}

@Composable
private fun VoucherChooser(selected: Voucher?, onSelect: (Voucher?) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) { Text("Voucher", fontWeight = FontWeight.Black); LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) { items(FoodSeedData.vouchers) { voucher -> FilterChip(selected = selected?.id == voucher.id, onClick = { onSelect(if (selected?.id == voucher.id) null else voucher) }, label = { Text("${voucher.title} - -${voucher.discountAmount.money()}") }) } } }
}

@Composable
private fun PaymentChooser(selected: PaymentMethod, onSelect: (PaymentMethod) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) { Text("Thanh toán", fontWeight = FontWeight.Black); FoodSeedData.paymentMethods.forEach { method -> Card(Modifier.fillMaxWidth().clickable { onSelect(method) }, shape = CardShape, colors = CardDefaults.cardColors(containerColor = if (selected.id == method.id) Color(0xFFE1F6EC) else Elevated)) { Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) { Text(method.icon, fontSize = 24.sp); Column(Modifier.weight(1f)) { Text(method.title, fontWeight = FontWeight.Black); Text(method.subtitle, color = Muted, fontSize = 12.sp) }; AnimatedVisibility(selected.id == method.id) { Icon(Icons.Default.CheckCircle, null, tint = Leaf) } } } } }
}

@Composable
private fun PriceBreakdown(state: RouteFoodUiState) {
    GlassSurface(strong = true) { Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) { PriceLine("Tạm tính", state.subtotal); PriceLine("Phí giao hàng", state.deliveryFee); PriceLine("Giảm giá", -state.discount); Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) { Text("Tổng cộng", fontWeight = FontWeight.Black); Text(state.total.money(), color = Leaf, fontWeight = FontWeight.Black, fontSize = 20.sp) } } }
}

@Composable
private fun PriceLine(label: String, value: Int) { Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) { Text(label, color = Muted); Text(value.money()) } }

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun OrderSuccessSheet(order: Order, onDismiss: () -> Unit) {
    ModalBottomSheet(onDismissRequest = onDismiss, containerColor = MaterialTheme.colorScheme.surface.copy(alpha = .96f)) { Column(Modifier.padding(24.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(14.dp)) { Icon(Icons.Default.CheckCircle, null, tint = Leaf, modifier = Modifier.size(72.dp)); Text("Đặt đơn thành công", fontSize = 28.sp, fontWeight = FontWeight.Black); Text("Mã đơn ${order.id} - ETA ${order.etaMin} phút", color = Muted); Button(onClick = onDismiss, shape = PillShape, modifier = Modifier.fillMaxWidth()) { Text("Theo dõi đơn") }; Spacer(Modifier.height(24.dp)) } }
}

@Composable
private fun OrdersScreen(orders: List<Order>) {
    LazyColumn(contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) { item { Text("Đơn hàng", fontSize = 34.sp, fontWeight = FontWeight.Black) }; if (orders.isEmpty()) item { EmptyState("Chưa có đơn", "Đặt món đầu tiên để xem timeline ở đây.") }; items(orders) { OrderCard(it) }; item { Spacer(Modifier.height(96.dp)) } }
}

@Composable
private fun OffersScreen(selected: Voucher?, onSelect: (Voucher?) -> Unit) {
    LazyColumn(contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        item {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("Offers", fontSize = 34.sp, fontWeight = FontWeight.Black)
                Text("Liquid glass vouchers picked for today", color = Muted)
            }
        }
        item {
            LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                items(listOf("Available", "Best for you", "Free ship", "Lunch Deal")) {
                    FilterChip(selected = it == "Available", onClick = {}, label = { Text(it) })
                }
            }
        }
        items(FoodSeedData.vouchers) { voucher ->
            VoucherTicket(voucher, selected?.id == voucher.id) {
                onSelect(if (selected?.id == voucher.id) null else voucher)
            }
        }
        item { Spacer(Modifier.height(112.dp)) }
    }
}

@Composable
private fun VoucherTicket(voucher: Voucher, selected: Boolean, onClick: () -> Unit) {
    GlassSurface(Modifier.fillMaxWidth().clickable { onClick() }, radius = 30.dp, strong = true) {
        Row(Modifier.padding(18.dp), horizontalArrangement = Arrangement.spacedBy(16.dp), verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(70.dp).clip(CardShape).background(Brush.linearGradient(listOf(Leaf, Orange))), contentAlignment = Alignment.Center) {
                Text("-${voucher.discountAmount / 1000}K", color = Color.White, fontWeight = FontWeight.Black, fontSize = 20.sp)
            }
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                Text(voucher.title, fontWeight = FontWeight.Black, fontSize = 19.sp)
                Text(voucher.description, color = Muted)
                Text("Min order ${voucher.minOrder.money()}", color = Leaf, fontWeight = FontWeight.Bold, fontSize = 12.sp)
            }
            Text(if (selected) "Applied" else "Apply", color = if (selected) Leaf else Orange, fontWeight = FontWeight.Black)
        }
    }
}

@Composable
private fun OrderCard(order: Order) {
    GlassSurface(strong = true) { Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) { Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) { Text(order.id, fontWeight = FontWeight.Black); Text(order.total.money(), color = Leaf, fontWeight = FontWeight.Black) }; Text("${order.items.size} món - ${order.paymentMethod.title} - ETA ${order.etaMin} phút", color = Muted); listOf("Quán nhận đơn", "Đang chuẩn bị", "Tìm tài xế", "Đang giao").forEachIndexed { index, label -> Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) { Box(Modifier.size(12.dp).clip(CircleShape).background(if (index <= 1) Leaf else Color(0xFFD8CABC))); Text(label, fontWeight = if (index <= 1) FontWeight.Bold else FontWeight.Normal) } } } }
}

@Composable
private fun ProfileScreen() {
    LazyColumn(contentPadding = PaddingValues(start = 14.dp, end = 14.dp, top = 46.dp, bottom = 118.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        item { Text("‹", fontSize = 30.sp, fontWeight = FontWeight.Light) }
        item { ProfileIdentityCard() }
        item { ProfileTabs() }
        item { PaymentDashboardGrid() }
        item { BusinessQuickRow() }
        item { ProfileSectionList("For more value", listOf("RoutePoints" to "23 RoutePoints", "Subscriptions" to "", "Rewards" to "", "Challenges" to "")) }
        item { ProfileSectionList("General", listOf("Personal info" to "", "Saved addresses" to "", "Payment methods" to "", "Help Centre" to "", "Settings" to "")) }
    }
}

@Composable
private fun ProfileIdentityCard() {
    GlassSurface(Modifier.fillMaxWidth(), radius = 18.dp, strong = true) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Box(Modifier.size(48.dp).clip(CircleShape).background(Color(0xFF2FAF9F)), contentAlignment = Alignment.Center) {
                    Icon(Icons.Default.AccountCircle, null, tint = Color.White, modifier = Modifier.size(34.dp))
                }
                Text("Minh", fontWeight = FontWeight.ExtraBold, fontSize = 18.sp, modifier = Modifier.weight(1f))
                Box(Modifier.clip(PillShape).background(Color(0xFFEAF8F4)).padding(horizontal = 16.dp, vertical = 9.dp)) {
                    Text("Profile", color = Color(0xFF237A68), fontWeight = FontWeight.Bold)
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                ProfileMiniPill("∞ Join RouteFood Plus", Modifier.weight(1f))
                ProfileMiniPill("VIP Track progress", Modifier.weight(1f))
            }
        }
    }
}

@Composable
private fun ProfileMiniPill(text: String, modifier: Modifier = Modifier) {
    Box(modifier.clip(PillShape).background(Color.White).padding(horizontal = 12.dp, vertical = 8.dp), contentAlignment = Alignment.Center) {
        Text(text, fontWeight = FontWeight.Bold, fontSize = 12.sp, maxLines = 1)
    }
}

@Composable
private fun ProfileTabs() {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(Modifier.fillMaxWidth()) {
            Text("Dashboard", color = Leaf, fontWeight = FontWeight.Black, modifier = Modifier.weight(1f), textAlign = androidx.compose.ui.text.style.TextAlign.Center)
            Text("Activity", color = Muted, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f), textAlign = androidx.compose.ui.text.style.TextAlign.Center)
        }
        Box(Modifier.fillMaxWidth().height(2.dp).background(Color(0xFFE8E5DF))) {
            Box(Modifier.fillMaxWidth(.5f).height(2.dp).background(Leaf))
        }
    }
}

@Composable
private fun PaymentDashboardGrid() {
    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        PaymentTile("RF", "Default", "RoutePay", Modifier.weight(1f), Leaf)
        PaymentTile("+", "", "Add payment method", Modifier.weight(1f), Color(0xFFE3F6F2))
    }
}

@Composable
private fun PaymentTile(icon: String, badge: String, title: String, modifier: Modifier, color: Color) {
    Card(modifier.height(116.dp), shape = RoundedCornerShape(14.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
        Column(Modifier.fillMaxSize().padding(14.dp), verticalArrangement = Arrangement.SpaceBetween) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(34.dp).clip(CircleShape).background(color), contentAlignment = Alignment.Center) { Text(icon, color = if (icon == "+") Color(0xFF1F8C7C) else Color.White, fontWeight = FontWeight.Black) }
                if (badge.isNotBlank()) Box(Modifier.clip(PillShape).background(Color(0xFFF1F0EE)).padding(horizontal = 18.dp, vertical = 7.dp)) { Text(badge, color = Muted, fontSize = 10.sp, fontWeight = FontWeight.Bold) }
            }
            Text(title, fontWeight = FontWeight.Bold)
        }
    }
}

@Composable
private fun BusinessQuickRow() {
    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        SmallMonoCard("Set up Family account", "👥", Modifier.weight(1f))
        SmallMonoCard("Business Centre", "💼", Modifier.weight(1f))
    }
}

@Composable
private fun SmallMonoCard(title: String, icon: String, modifier: Modifier) {
    Card(modifier.height(56.dp), shape = RoundedCornerShape(12.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
        Row(Modifier.fillMaxSize().padding(horizontal = 12.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceBetween) {
            Text(title, fontWeight = FontWeight.Bold, fontSize = 12.sp)
            Text(icon, fontSize = 24.sp)
        }
    }
}

@Composable
private fun ProfileSectionList(title: String, rows: List<Pair<String, String>>) {
    Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Text(title, fontSize = 20.sp, fontWeight = FontWeight.ExtraBold, modifier = Modifier.padding(vertical = 10.dp))
        rows.forEach { (label, value) ->
            Row(Modifier.fillMaxWidth().height(54.dp), verticalAlignment = Alignment.CenterVertically) {
                Text(label, fontWeight = FontWeight.Medium, modifier = Modifier.weight(1f))
                if (value.isNotBlank()) Text(value, color = Muted, fontWeight = FontWeight.Medium)
                Text("  ›", color = Muted, fontSize = 24.sp)
            }
            Box(Modifier.fillMaxWidth().height(1.dp).background(Color(0xFFE8E1D8)))
        }
    }
}

@Composable
private fun RestaurantListStyleItem(title: String) { GlassSurface(strong = true) { Row(Modifier.fillMaxWidth().padding(18.dp), horizontalArrangement = Arrangement.SpaceBetween) { Text(title, fontWeight = FontWeight.Bold); Text("›", color = Muted, fontSize = 24.sp) } } }

@Composable
private fun EmptyState(title: String, subtitle: String) { GlassSurface(strong = true) { Column(Modifier.fillMaxWidth().padding(28.dp), horizontalAlignment = Alignment.CenterHorizontally) { Text(title, fontWeight = FontWeight.Black, fontSize = 20.sp); Text(subtitle, color = Muted) } } }
