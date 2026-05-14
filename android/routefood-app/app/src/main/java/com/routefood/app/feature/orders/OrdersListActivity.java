package com.routefood.app.feature.orders;

import android.content.Intent;
import android.os.Bundle;
import android.view.View;
import android.widget.ProgressBar;
import android.widget.TextView;

import androidx.recyclerview.widget.LinearLayoutManager;
import androidx.recyclerview.widget.RecyclerView;

import com.routefood.app.R;
import com.routefood.app.core.ui.BaseActivity;
import com.routefood.app.data.model.Order;
import com.routefood.app.data.repository.OrderRepository;
import com.routefood.app.data.repository.RepositoryCallback;
import com.routefood.app.feature.user.tracking.UserTrackingActivity;

import java.util.ArrayList;
import java.util.List;

public class OrdersListActivity extends BaseActivity {
    private RecyclerView recyclerView;
    private OrderAdapter adapter;
    private TextView emptyStateText;
    private ProgressBar progressBar;
    private List<Order> orders = new ArrayList<>();

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_orders_list);

        recyclerView = findViewById(R.id.ordersRecyclerView);
        emptyStateText = findViewById(R.id.emptyStateText);
        progressBar = findViewById(R.id.progressBar);

        recyclerView.setLayoutManager(new LinearLayoutManager(this));
        adapter = new OrderAdapter(this::onOrderClicked);
        recyclerView.setAdapter(adapter);

        loadOrders();
    }

    private void loadOrders() {
        progressBar.setVisibility(View.VISIBLE);
        emptyStateText.setVisibility(View.GONE);
        recyclerView.setVisibility(View.GONE);

        // For now, show demo orders - in production this would fetch from Firestore/Supabase
        showDemoOrders();
    }

    private void showDemoOrders() {
        try {
            Thread.sleep(500); // Simulate loading
        } catch (InterruptedException e) {
            e.printStackTrace();
        }

        // Demo orders for testing
        List<Order> demoOrders = new ArrayList<>();
        demoOrders.add(new Order("order_1", "user_1", "restaurant_1", "in_transit", "driver_1", "assignment_1", 150000L, 25, null, null));
        demoOrders.add(new Order("order_2", "user_1", "restaurant_2", "confirmed", "null", "null", 85000L, 30, null, null));
        demoOrders.add(new Order("order_3", "user_1", "restaurant_3", "delivered", "driver_3", "assignment_3", 120000L, 0, null, null));

        orders = demoOrders;
        adapter.submitList(orders);
        progressBar.setVisibility(View.GONE);
        recyclerView.setVisibility(View.VISIBLE);

        if (orders.isEmpty()) {
            emptyStateText.setVisibility(View.VISIBLE);
            emptyStateText.setText("No orders yet. Place your first order!");
        }
    }

    private void onOrderClicked(Order order) {
        Intent intent = new Intent(this, UserTrackingActivity.class);
        intent.putExtra("orderId", order.id());
        intent.putExtra("status", order.status());
        intent.putExtra("total", order.total());
        startActivity(intent);
    }

    private String formatStatus(String status) {
        return status.replace("_", " ").substring(0, 1).toUpperCase() + status.replace("_", " ").substring(1);
    }

    private String formatPrice(long price) {
        return String.format("VND %d", price);
    }
}
