package com.routefood.app.feature.user.cart;

import android.content.Intent;
import android.os.Bundle;
import android.widget.TextView;

import com.routefood.app.R;
import com.routefood.app.core.ui.BaseActivity;
import com.routefood.app.data.repository.CartStore;
import com.routefood.app.feature.user.checkout.CheckoutActivity;

import java.util.Map;

public class CartActivity extends BaseActivity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_cart);
        CartStore cartStore = new CartStore(this);
        StringBuilder summary = new StringBuilder();
        if (cartStore.itemsPayload().isEmpty()) {
            summary.append("Your cart is empty.");
        } else {
            for (Map<String, Object> item : cartStore.itemsPayload()) {
                summary.append(item.get("name")).append(" x").append(item.get("quantity")).append("\n");
            }
            summary.append("\nSubtotal: ").append(cartStore.subtotal()).append("đ");
        }
        ((TextView) findViewById(R.id.cartSummaryText)).setText(summary.toString());
        findViewById(R.id.checkoutButton).setOnClickListener(view -> startActivity(new Intent(this, CheckoutActivity.class)));
    }
}
