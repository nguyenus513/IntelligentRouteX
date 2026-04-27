package com.routefood.app.data.repository;

import com.google.firebase.firestore.QueryDocumentSnapshot;
import com.routefood.app.core.firebase.FirebaseRefs;
import com.routefood.app.data.model.MenuItem;
import com.routefood.app.data.model.Restaurant;

import java.util.ArrayList;
import java.util.List;

public class RestaurantRepository {
    private final FirebaseRefs refs;

    public RestaurantRepository() {
        refs = new FirebaseRefs();
    }

    public void loadActiveRestaurants(RepositoryCallback<List<Restaurant>> callback) {
        refs.restaurants()
                .whereEqualTo("active", true)
                .limit(30)
                .get()
                .addOnSuccessListener(snapshot -> {
                    List<Restaurant> restaurants = new ArrayList<>();
                    for (QueryDocumentSnapshot document : snapshot) {
                        restaurants.add(Restaurant.fromDocument(document));
                    }
                    callback.onSuccess(restaurants);
                })
                .addOnFailureListener(callback::onError);
    }

    public void loadMenuItems(String restaurantId, RepositoryCallback<List<MenuItem>> callback) {
        refs.menuItems(restaurantId)
                .whereEqualTo("available", true)
                .limit(80)
                .get()
                .addOnSuccessListener(snapshot -> {
                    List<MenuItem> menuItems = new ArrayList<>();
                    for (QueryDocumentSnapshot document : snapshot) {
                        menuItems.add(MenuItem.fromDocument(restaurantId, document));
                    }
                    callback.onSuccess(menuItems);
                })
                .addOnFailureListener(callback::onError);
    }
}
