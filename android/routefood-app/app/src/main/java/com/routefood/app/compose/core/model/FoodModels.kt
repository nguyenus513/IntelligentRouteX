package com.routefood.app.compose.core.model

data class Restaurant(
    val id: String,
    val name: String,
    val cuisine: String,
    val coverUrl: String,
    val rating: Double,
    val etaMin: Int,
    val deliveryFee: Int,
    val distanceKm: Double,
    val tags: List<String>,
    val popularity: Double,
    val promoLabel: String? = null
)

data class MenuItem(
    val id: String,
    val restaurantId: String,
    val name: String,
    val description: String,
    val price: Int,
    val imageUrl: String,
    val tags: List<String>,
    val rating: Double,
    val soldCount: Int,
    val toppings: List<String> = emptyList()
)

data class Voucher(
    val id: String,
    val title: String,
    val description: String,
    val minOrder: Int,
    val discountAmount: Int,
    val tag: String? = null
)

data class PaymentMethod(
    val id: String,
    val title: String,
    val subtitle: String,
    val icon: String
)

data class CartItem(
    val menuItem: MenuItem,
    val quantity: Int,
    val note: String = "",
    val toppings: List<String> = emptyList()
) {
    val lineTotal: Int = menuItem.price * quantity
}

data class Order(
    val id: String,
    val items: List<CartItem>,
    val total: Int,
    val status: OrderStatus,
    val etaMin: Int,
    val paymentMethod: PaymentMethod,
    val voucher: Voucher?
)

enum class OrderStatus { Preparing, FindingDriver, Delivering, Delivered }

data class RecommendationSection(
    val id: String,
    val title: String,
    val subtitle: String,
    val tags: List<String>
)

data class RecommendedFood(
    val item: MenuItem,
    val restaurant: Restaurant,
    val reason: String
)

data class RecommendedFoodSection(
    val id: String,
    val title: String,
    val subtitle: String,
    val items: List<RecommendedFood>,
    val source: String = "rule_local"
)

