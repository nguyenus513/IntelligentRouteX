package com.routefood.app.feature.user.checkout;

import android.content.Intent;
import android.os.Bundle;
import android.widget.TextView;
import android.widget.Toast;

import com.routefood.app.R;
import com.routefood.app.core.ui.BaseActivity;
import com.routefood.app.data.repository.CartStore;
import com.routefood.app.data.repository.OrderRepository;
import com.routefood.app.data.repository.RepositoryCallback;
import com.routefood.app.feature.user.tracking.UserTrackingActivity;

import java.util.HashMap;
import java.util.Map;

public class CheckoutActivity extends BaseActivity {
    private CartStore cartStore;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_checkout);
        cartStore = new CartStore(this);
        long deliveryFee = cartStore.itemsPayload().isEmpty() ? 0 : 15000;
        long serviceFee = cartStore.itemsPayload().isEmpty() ? 0 : 5000;
        long total = cartStore.subtotal() + deliveryFee + serviceFee;
        ((TextView) findViewById(R.id.checkoutSummaryText)).setText(
                "Tạm tính\n" + cartStore.subtotal() + "đ\n\n"
                        + "Phí giao hàng\n" + deliveryFee + "đ\n\n"
                        + "Phí dịch vụ\n" + serviceFee + "đ\n\n"
                        + "Total\n" + total + "đ");
        findViewById(R.id.placeOrderButton).setOnClickListener(view -> placeOrder());
    }

    private void placeOrder() {
        if (cartStore.itemsPayload().isEmpty()) {
            Toast.makeText(this, "Giỏ hàng trống.", Toast.LENGTH_SHORT).show();
            return;
        }
        Map<String, Object> dropoff = new HashMap<>();
        dropoff.put("lat", 10.7741);
        dropoff.put("lng", 106.7038);
        Map<String, Object> payload = new HashMap<>();
        payload.put("restaurantId", cartStore.restaurantId());
        payload.put("dropoffLocation", dropoff);
        payload.put("items", cartStore.itemsPayload());
        payload.put("paymentMethod", "COD_DEMO");
        new OrderRepository(this).createUserOrder(payload, new RepositoryCallback<>() {
            @Override
            public void onSuccess(Map<String, Object> value) {
                String orderId = String.valueOf(value.get("orderId"));
                cartStore.clear();
                Intent intent = new Intent(CheckoutActivity.this, UserTrackingActivity.class);
                intent.putExtra(UserTrackingActivity.EXTRA_ORDER_ID, orderId);
                startActivity(intent);
                finish();
            }

            @Override
            public void onError(Exception error) {
                Toast.makeText(CheckoutActivity.this, error.getMessage(), Toast.LENGTH_LONG).show();
            }
        });
    }
}
