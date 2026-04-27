package com.routefood.app.feature.user.restaurant;

import android.content.Intent;
import android.os.Bundle;
import android.widget.TextView;
import android.widget.Toast;

import androidx.recyclerview.widget.LinearLayoutManager;
import androidx.recyclerview.widget.RecyclerView;

import com.routefood.app.R;
import com.routefood.app.core.ui.BaseActivity;
import com.routefood.app.data.model.MenuItem;
import com.routefood.app.data.repository.CartStore;
import com.routefood.app.data.repository.RepositoryCallback;
import com.routefood.app.data.repository.RestaurantRepository;
import com.routefood.app.feature.user.cart.CartActivity;

import java.util.List;

public class RestaurantDetailActivity extends BaseActivity {
    public static final String EXTRA_RESTAURANT_ID = "restaurant_id";
    public static final String EXTRA_RESTAURANT_NAME = "restaurant_name";
    public static final String EXTRA_RESTAURANT_META = "restaurant_meta";

    private CartStore cartStore;
    private MenuAdapter menuAdapter;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_restaurant_detail);
        String restaurantId = getIntent().getStringExtra(EXTRA_RESTAURANT_ID);
        String restaurantName = getIntent().getStringExtra(EXTRA_RESTAURANT_NAME);
        String restaurantMeta = getIntent().getStringExtra(EXTRA_RESTAURANT_META);
        cartStore = new CartStore(this);

        ((TextView) findViewById(R.id.restaurantTitleText)).setText(restaurantName);
        ((TextView) findViewById(R.id.restaurantSubtitleText)).setText(restaurantMeta);
        menuAdapter = new MenuAdapter(item -> {
            cartStore.addItem(restaurantId, item.id(), item.name(), item.price());
            Toast.makeText(this, "Added " + item.name(), Toast.LENGTH_SHORT).show();
        });
        RecyclerView recyclerView = findViewById(R.id.menuRecyclerView);
        recyclerView.setLayoutManager(new LinearLayoutManager(this));
        recyclerView.setAdapter(menuAdapter);
        findViewById(R.id.openCartButton).setOnClickListener(view -> startActivity(new Intent(this, CartActivity.class)));

        new RestaurantRepository().loadMenuItems(restaurantId, new RepositoryCallback<>() {
            @Override
            public void onSuccess(List<MenuItem> value) {
                menuAdapter.submitList(value);
            }

            @Override
            public void onError(Exception error) {
                Toast.makeText(RestaurantDetailActivity.this, "Unable to load menu", Toast.LENGTH_LONG).show();
            }
        });
    }
}
