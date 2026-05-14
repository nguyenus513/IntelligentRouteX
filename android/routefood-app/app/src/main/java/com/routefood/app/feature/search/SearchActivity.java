package com.routefood.app.feature.search;

import android.content.Intent;
import android.os.Bundle;
import android.view.View;
import android.widget.EditText;
import android.widget.ProgressBar;
import android.widget.TextView;

import androidx.recyclerview.widget.LinearLayoutManager;
import androidx.recyclerview.widget.RecyclerView;

import com.routefood.app.R;
import com.routefood.app.core.ui.BaseActivity;
import com.routefood.app.data.model.Restaurant;
import com.routefood.app.data.repository.RepositoryCallback;
import com.routefood.app.data.repository.RestaurantRepository;
import com.routefood.app.feature.user.restaurant.RestaurantDetailActivity;

import java.util.ArrayList;
import java.util.List;

public class SearchActivity extends BaseActivity {
    private EditText searchEditText;
    private TextView emptyStateText;
    private RecyclerView recyclerView;
    private RestaurantSearchAdapter adapter;
    private RestaurantRepository repository;
    private List<Restaurant> allRestaurants = new ArrayList<>();
    private List<Restaurant> displayedRestaurants = new ArrayList<>();

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_search);

        searchEditText = findViewById(R.id.searchEditText);
        emptyStateText = findViewById(R.id.emptyStateText);
        recyclerView = findViewById(R.id.searchResultsRecyclerView);
        recyclerView.setLayoutManager(new LinearLayoutManager(this));
        adapter = new RestaurantSearchAdapter(this::onRestaurantClicked);
        recyclerView.setAdapter(adapter);

        searchEditText.setOnEditorActionListener((v, actionId, event) -> {
            performSearch();
            return true;
        });

        loadRestaurants();
    }

    private void onRestaurantClicked(Restaurant restaurant) {
        Intent intent = new Intent(this, RestaurantDetailActivity.class);
        intent.putExtra("restaurant_id", restaurant.id());
        intent.putExtra("restaurant_name", restaurant.name());
        startActivity(intent);
    }

    private void loadRestaurants() {
        findViewById(R.id.progressBar).setVisibility(View.VISIBLE);
        repository = new RestaurantRepository();
        repository.loadActiveRestaurants(new RepositoryCallback<List<Restaurant>>() {
            @Override
            public void onSuccess(List<Restaurant> restaurants) {
                allRestaurants = new ArrayList<>(restaurants);
                displayedRestaurants = new ArrayList<>(allRestaurants);
                adapter.submitList(displayedRestaurants);
                findViewById(R.id.progressBar).setVisibility(View.GONE);
                if (allRestaurants.isEmpty()) {
                    emptyStateText.setVisibility(View.VISIBLE);
                    emptyStateText.setText("No restaurants available");
                }
            }

            @Override
            public void onError(Exception error) {
                findViewById(R.id.progressBar).setVisibility(View.GONE);
                emptyStateText.setVisibility(View.VISIBLE);
                emptyStateText.setText("Unable to load restaurants");
            }
        });
    }

    private void performSearch() {
        String query = searchEditText.getText().toString().trim().toLowerCase();
        if (query.isEmpty()) {
            displayedRestaurants = new ArrayList<>(allRestaurants);
        } else {
            displayedRestaurants.clear();
            for (Restaurant r : allRestaurants) {
                if (r.name().toLowerCase().contains(query) ||
                    r.address().toLowerCase().contains(query) ||
                    hasMatchingCategory(r, query)) {
                    displayedRestaurants.add(r);
                }
            }
        }
        adapter.submitList(displayedRestaurants);
        emptyStateText.setVisibility(displayedRestaurants.isEmpty() ? View.VISIBLE : View.GONE);
    }

    private boolean hasMatchingCategory(Restaurant r, String query) {
        for (String cat : r.categories()) {
            if (cat.toLowerCase().contains(query)) return true;
        }
        return false;
    }
}
