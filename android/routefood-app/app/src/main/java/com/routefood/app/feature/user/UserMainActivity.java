package com.routefood.app.feature.user;

import android.os.Bundle;
import android.content.Intent;
import android.view.View;
import android.widget.TextView;

import androidx.recyclerview.widget.LinearLayoutManager;
import androidx.recyclerview.widget.RecyclerView;

import com.routefood.app.R;
import com.routefood.app.core.ui.BaseActivity;
import com.routefood.app.data.model.Restaurant;
import com.routefood.app.data.repository.RepositoryCallback;
import com.routefood.app.data.repository.RestaurantRepository;
import com.routefood.app.feature.user.home.RestaurantAdapter;
import com.routefood.app.feature.user.restaurant.RestaurantDetailActivity;

import java.util.List;

public class UserMainActivity extends BaseActivity {
    private TextView homeStateText;
    private RestaurantAdapter restaurantAdapter;
    private RestaurantRepository restaurantRepository;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_user_main);
        homeStateText = findViewById(R.id.homeStateText);
        restaurantAdapter = new RestaurantAdapter(restaurant -> {
            Intent intent = new Intent(this, RestaurantDetailActivity.class);
            intent.putExtra(RestaurantDetailActivity.EXTRA_RESTAURANT_ID, restaurant.id());
            intent.putExtra(RestaurantDetailActivity.EXTRA_RESTAURANT_NAME, restaurant.name());
            intent.putExtra(RestaurantDetailActivity.EXTRA_RESTAURANT_META,
                    "Rating " + restaurant.rating() + " • " + restaurant.averagePrepTimeMin() + " min");
            startActivity(intent);
        });
        restaurantRepository = new RestaurantRepository();

        RecyclerView recyclerView = findViewById(R.id.restaurantRecyclerView);
        recyclerView.setLayoutManager(new LinearLayoutManager(this));
        recyclerView.setAdapter(restaurantAdapter);

        loadRestaurants();
    }

    private void loadRestaurants() {
        homeStateText.setVisibility(View.VISIBLE);
        homeStateText.setText("Loading HCMC restaurants...");
        restaurantRepository.loadActiveRestaurants(new RepositoryCallback<>() {
            @Override
            public void onSuccess(List<Restaurant> restaurants) {
                if (restaurants.isEmpty()) {
                    homeStateText.setVisibility(View.VISIBLE);
                    homeStateText.setText("No restaurants yet. Seed HCMC demo data to populate this list.");
                    return;
                }
                homeStateText.setVisibility(View.GONE);
                restaurantAdapter.submitList(restaurants);
            }

            @Override
            public void onError(Exception error) {
                homeStateText.setVisibility(View.VISIBLE);
                homeStateText.setText("Unable to load restaurants. Check Firebase config or emulator connection.");
            }
        });
    }
}
