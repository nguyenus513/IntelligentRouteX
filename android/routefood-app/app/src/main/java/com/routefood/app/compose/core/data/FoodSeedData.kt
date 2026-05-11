package com.routefood.app.compose.core.data

import com.routefood.app.compose.core.model.MenuItem
import com.routefood.app.compose.core.model.PaymentMethod
import com.routefood.app.compose.core.model.RecommendationSection
import com.routefood.app.compose.core.model.Restaurant
import com.routefood.app.compose.core.model.Voucher

object FoodSeedData {
    val restaurants = listOf(
        Restaurant("r1", "Cơm Gà Q1", "Cơm Việt", img("photo-1604908176997-125f25cc6f3d"), 4.8, 22, 12000, 1.2, listOf("lunch", "best_seller", "hot_food", "rice"), 0.96, "Giảm 20K"),
        Restaurant("r2", "Bún Bò Huế Mưa", "Bún phở", img("photo-1569058242253-92a9c755a0ec"), 4.7, 28, 15000, 2.1, listOf("rainy_day", "hot_food", "dinner", "noodle"), 0.91, "Free ship"),
        Restaurant("r3", "Phở Bò Sài Gòn", "Phở", img("photo-1582878826629-29b7ad1cdc43"), 4.9, 20, 10000, 1.5, listOf("breakfast", "hot_food", "best_seller", "noodle"), 0.98),
        Restaurant("r4", "Bánh Mì 24h", "Ăn nhanh", img("photo-1551782450-a2132b4ba21d"), 4.6, 16, 9000, 0.8, listOf("breakfast", "snack", "cheap"), 0.88, "Mua 2 giảm 15%"),
        Restaurant("r5", "Trà Sữa Mây", "Đồ uống", img("photo-1551024601-bec78aea704b"), 4.7, 18, 8000, 1.0, listOf("drink", "sunny_day", "snack"), 0.93, "Topping free"),
        Restaurant("r6", "Gà Rán Giòn Tan", "Fast food", img("photo-1562967916-eb82221dfb92"), 4.5, 24, 14000, 2.4, listOf("combo", "family", "dinner"), 0.86),
        Restaurant("r7", "Pizza Đêm", "Pizza", img("photo-1513104890138-7c749659a591"), 4.6, 32, 18000, 3.0, listOf("dinner", "family", "premium", "combo"), 0.84, "Combo tối"),
        Restaurant("r8", "Green Bowl", "Healthy", img("photo-1512621776951-a57141f2eefd"), 4.8, 21, 12000, 1.7, listOf("healthy", "lunch", "sunny_day"), 0.89),
        Restaurant("r9", "Sushi Mini", "Nhật", img("photo-1579584425555-c3ce17fd4351"), 4.7, 35, 20000, 3.2, listOf("premium", "dinner"), 0.82),
        Restaurant("r10", "Lẩu Tối Ấm", "Lẩu", img("photo-1544025162-d76694265947"), 4.9, 40, 22000, 3.6, listOf("rainy_day", "family", "hot_food", "dinner"), 0.95, "Set 2 người")
    )

    val menuItems = restaurants.flatMapIndexed { index, restaurant ->
        val base = index * 5
        listOf(
            MenuItem("m${base + 1}", restaurant.id, "Best seller ${restaurant.name}", "Khẩu phần signature, vị đậm và đóng gói kỹ cho delivery.", 59000 + index * 3000, restaurant.coverUrl, restaurant.tags + "best_seller", 4.8, 1200 - index * 41, listOf("Ít cay", "Thêm sốt", "Phần lớn")),
            MenuItem("m${base + 2}", restaurant.id, "Combo tiết kiệm", "Combo có món chính, topping và đồ uống nhỏ.", 79000 + index * 4000, img("photo-1546069901-ba9599a7e63c"), restaurant.tags + "combo", 4.6, 860 - index * 27, listOf("Đổi nước", "Thêm topping")),
            MenuItem("m${base + 3}", restaurant.id, "Phần cá nhân", "Nhanh gọn cho bữa trưa văn phòng.", 49000 + index * 2000, img("photo-1504674900247-0877df9cc836"), restaurant.tags + "lunch", 4.5, 740 - index * 20),
            MenuItem("m${base + 4}", restaurant.id, "Món nóng ngày mưa", "Giữ nhiệt tốt, phù hợp khi trời mưa hoặc buổi tối.", 69000 + index * 3000, img("photo-1547592180-85f173990554"), restaurant.tags + listOf("rainy_day", "hot_food"), 4.7, 620 - index * 18),
            MenuItem("m${base + 5}", restaurant.id, "Đồ uống kèm", "Món uống cân bằng vị, giảm ngấy.", 29000 + index * 1000, img("photo-1544145945-f90425340c7e"), restaurant.tags + listOf("drink", "sunny_day"), 4.4, 510 - index * 14)
        )
    }

    val vouchers = listOf(
        Voucher("v1", "Free ship gần bạn", "Áp dụng cho đơn từ 80K", 80000, 15000, "nearby"),
        Voucher("v2", "Lunch -20K", "Bữa trưa nhanh, giảm trực tiếp", 120000, 20000, "lunch"),
        Voucher("v3", "Mưa ấm bụng", "Ưu đãi món nóng ngày mưa", 100000, 18000, "rainy_day"),
        Voucher("v4", "Combo gia đình", "Giảm cho đơn nhóm", 180000, 30000, "family"),
        Voucher("v5", "Đồ uống giải nhiệt", "Giảm trà sữa/nước ép", 70000, 12000, "drink")
    )

    val paymentMethods = listOf(
        PaymentMethod("cod", "COD", "Thanh toán khi nhận hàng", "COD"),
        PaymentMethod("wallet", "Ví RouteFood Demo", "Số dư demo 520.000đ", "RF"),
        PaymentMethod("visa", "Visa Demo **** 4242", "Thanh toán giả lập", "VISA"),
        PaymentMethod("qr", "QR Demo", "Quét mã mô phỏng", "QR")
    )

    val sections = listOf(
        RecommendationSection("ai_for_you", "AI gợi ý cho bạn", "Xếp hạng theo thói quen, giờ ăn và ưu đãi", listOf("best_seller", "lunch", "drink")),
        RecommendationSection("lunch_time", "Ăn trưa hôm nay", "Nhanh, gọn, hợp giờ văn phòng", listOf("lunch", "rice", "noodle")),
        RecommendationSection("rainy_day", "Hợp trời mưa", "Món nóng, nước dùng và lẩu", listOf("rainy_day", "hot_food")),
        RecommendationSection("best_sellers_nearby", "Quán bán chạy gần bạn", "Rating cao, nhiều lượt đặt", listOf("best_seller")),
        RecommendationSection("afternoon_drinks", "Đồ uống giờ chiều", "Trà sữa, nước mát và snack", listOf("drink", "snack", "sunny_day")),
        RecommendationSection("dinner_combo", "Combo tối nay", "No đủ, ấm bụng, hợp đi nhóm", listOf("dinner", "family", "combo")),
        RecommendationSection("reorder", "Đặt lại món quen", "Những món bạn sẽ muốn ăn lại", listOf("combo", "drink", "best_seller"))
    )

    private fun img(id: String) = "https://images.unsplash.com/$id?auto=format&fit=crop&w=1200&q=80"
}
