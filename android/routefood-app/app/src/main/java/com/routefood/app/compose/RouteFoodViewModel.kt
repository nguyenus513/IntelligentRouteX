package com.routefood.app.compose

import androidx.lifecycle.ViewModel
import com.routefood.app.compose.core.data.FoodSeedData
import com.routefood.app.compose.core.model.CartItem
import com.routefood.app.compose.core.model.MenuItem
import com.routefood.app.compose.core.model.Order
import com.routefood.app.compose.core.model.OrderStatus
import com.routefood.app.compose.core.model.PaymentMethod
import com.routefood.app.compose.core.model.RecommendationSection
import com.routefood.app.compose.core.model.RecommendedFood
import com.routefood.app.compose.core.model.RecommendedFoodSection
import com.routefood.app.compose.core.model.Restaurant
import com.routefood.app.compose.core.model.Voucher
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import java.text.NumberFormat
import java.util.Locale
import kotlin.math.max

data class RouteFoodUiState(
    val restaurants: List<Restaurant> = FoodSeedData.restaurants,
    val menuItems: List<MenuItem> = FoodSeedData.menuItems,
    val cart: List<CartItem> = emptyList(),
    val orders: List<Order> = emptyList(),
    val selectedVoucher: Voucher? = null,
    val selectedPayment: PaymentMethod = FoodSeedData.paymentMethods.first(),
    val query: String = "",
    val weather: String = "rainy_day",
    val userTaste: Set<String> = setOf("lunch", "drink", "best_seller")
) {
    val subtotal: Int = cart.sumOf { it.lineTotal }
    val deliveryFee: Int = if (cart.isEmpty()) 0 else 15000
    val discount: Int = selectedVoucher?.takeIf { subtotal >= it.minOrder }?.discountAmount ?: 0
    val total: Int = max(0, subtotal + deliveryFee - discount)
}

class RouteFoodViewModel : ViewModel() {
    private val _state = MutableStateFlow(RouteFoodUiState())
    val state: StateFlow<RouteFoodUiState> = _state.asStateFlow()

    fun updateQuery(query: String) = _state.update { it.copy(query = query) }

    fun addToCart(item: MenuItem, quantity: Int = 1, toppings: List<String> = emptyList(), note: String = "") {
        _state.update { current ->
            val existing = current.cart.firstOrNull { it.menuItem.id == item.id && it.toppings == toppings && it.note == note }
            val nextCart = if (existing == null) {
                current.cart + CartItem(item, quantity, note, toppings)
            } else {
                current.cart.map { if (it == existing) it.copy(quantity = it.quantity + quantity) else it }
            }
            current.copy(cart = nextCart)
        }
    }

    fun updateQuantity(itemId: String, quantity: Int) {
        _state.update { current ->
            current.copy(cart = current.cart.mapNotNull { item ->
                when {
                    item.menuItem.id != itemId -> item
                    quantity <= 0 -> null
                    else -> item.copy(quantity = quantity)
                }
            })
        }
    }

    fun applyVoucher(voucher: Voucher?) = _state.update { it.copy(selectedVoucher = voucher) }
    fun selectPayment(method: PaymentMethod) = _state.update { it.copy(selectedPayment = method) }

    fun placeOrder(): Order? {
        val snapshot = _state.value
        if (snapshot.cart.isEmpty()) return null
        val order = Order(
            id = "RF${System.currentTimeMillis().toString().takeLast(6)}",
            items = snapshot.cart,
            total = snapshot.total,
            status = OrderStatus.Preparing,
            etaMin = 28,
            paymentMethod = snapshot.selectedPayment,
            voucher = snapshot.selectedVoucher
        )
        _state.update { it.copy(cart = emptyList(), selectedVoucher = null, orders = listOf(order) + it.orders) }
        return order
    }

    fun restaurantItems(restaurantId: String) = _state.value.menuItems.filter { it.restaurantId == restaurantId }

    fun recommendedRestaurants(tags: List<String>): List<Restaurant> {
        val state = _state.value
        return state.restaurants.sortedByDescending { restaurant ->
            scoreRestaurant(restaurant, tags, state)
        }.take(8)
    }

    fun homeRecommendationSections(): List<RecommendedFoodSection> {
        val state = _state.value
        return FoodSeedData.sections.map { section ->
            val items = state.menuItems
                .mapNotNull { item ->
                    val restaurant = state.restaurants.firstOrNull { it.id == item.restaurantId } ?: return@mapNotNull null
                    val score = scoreFood(item, restaurant, section, state)
                    RecommendedFood(item, restaurant, recommendationReason(item, restaurant, section)) to score
                }
                .sortedByDescending { it.second }
                .map { it.first }
                .distinctBy { it.item.id }
                .take(8)
            RecommendedFoodSection(section.id, section.title, section.subtitle, items)
        }
    }

    private fun scoreFood(item: MenuItem, restaurant: Restaurant, section: RecommendationSection, state: RouteFoodUiState): Double {
        val itemTags = item.tags.toSet()
        val sectionMatch = section.tags.count { it in itemTags || it in restaurant.tags } * 0.22
        val weatherMatch = if (state.weather in itemTags || state.weather in restaurant.tags) 0.18 else 0.0
        val tasteMatch = state.userTaste.count { it in itemTags || it in restaurant.tags } * 0.08
        val popularityScore = (item.soldCount.coerceAtLeast(0) / 1200.0).coerceAtMost(1.0) * 0.28
        val ratingScore = (item.rating / 5.0) * 0.12
        val distanceScore = (1.0 / (restaurant.distanceKm + 1.0)) * 0.12
        val promoScore = if (restaurant.promoLabel != null) 0.1 else 0.0
        return sectionMatch + weatherMatch + tasteMatch + popularityScore + ratingScore + distanceScore + promoScore
    }

    private fun scoreRestaurant(restaurant: Restaurant, tags: List<String>, state: RouteFoodUiState): Double {
        val tagMatch = tags.count { it in restaurant.tags } * 0.2
        val weatherMatch = if (state.weather in restaurant.tags) 0.15 else 0.0
        val tasteMatch = state.userTaste.count { it in restaurant.tags } * 0.05
        return restaurant.popularity * 0.3 + tagMatch + weatherMatch + tasteMatch + (1.0 / (restaurant.distanceKm + 1.0)) * 0.1 + if (restaurant.promoLabel != null) 0.1 else 0.0
    }

    private fun recommendationReason(item: MenuItem, restaurant: Restaurant, section: RecommendationSection): String {
        val tags = item.tags + restaurant.tags
        return when {
            section.id == "rainy_day" || "rainy_day" in tags -> "Món nóng hợp trời mưa"
            section.id == "afternoon_drinks" || "drink" in tags -> "Đồ uống hợp giờ chiều"
            section.id == "dinner_combo" || "family" in tags -> "Combo hợp bữa tối"
            section.id == "best_sellers_nearby" || "best_seller" in tags -> "Bán chạy gần bạn"
            section.id == "lunch_time" || "lunch" in tags -> "Nhanh gọn cho bữa trưa"
            restaurant.promoLabel != null -> "Có ưu đãi hôm nay"
            else -> "Hợp khẩu vị của bạn"
        }
    }
}

fun Int.money(): String = NumberFormat.getCurrencyInstance(Locale("vi", "VN")).format(this)
