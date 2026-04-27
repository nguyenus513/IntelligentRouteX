package com.routefood.app.data.repository;

import com.google.firebase.firestore.QueryDocumentSnapshot;
import com.routefood.app.core.firebase.FirebaseRefs;
import com.routefood.app.data.model.MenuItem;
import com.routefood.app.data.model.Restaurant;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class RestaurantRepository {
    private final FirebaseRefs refs;

    public RestaurantRepository() {
        FirebaseRefs firebaseRefs;
        try {
            firebaseRefs = new FirebaseRefs();
        } catch (IllegalStateException error) {
            firebaseRefs = null;
        }
        refs = firebaseRefs;
    }

    public void loadActiveRestaurants(RepositoryCallback<List<Restaurant>> callback) {
        if (refs == null) {
            callback.onSuccess(sampleRestaurants());
            return;
        }
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
        if (refs == null) {
            callback.onSuccess(sampleMenuItems(restaurantId));
            return;
        }
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

    private List<Restaurant> sampleRestaurants() {
        List<Restaurant> restaurants = new ArrayList<>();
        restaurants.add(new Restaurant("q1-pho-nguyen-hue", "Pho Nguyen Hue", "", 4.8,
                "Nguyen Hue, Quan 1", new com.routefood.app.data.model.GeoPoint(10.7741, 106.7038),
                Arrays.asList("pho", "breakfast"), 12, true));
        restaurants.add(new Restaurant("bt-com-tam-landmark", "Com Tam Landmark", "", 4.7,
                "Nguyen Huu Canh, Binh Thanh", new com.routefood.app.data.model.GeoPoint(10.7942, 106.7218),
                Arrays.asList("com tam", "lunch"), 15, true));
        return restaurants;
    }

    private List<MenuItem> sampleMenuItems(String restaurantId) {
        List<MenuItem> menuItems = new ArrayList<>();
        menuItems.add(new MenuItem("signature", restaurantId, "Signature Combo", "Best seller demo combo", 69000, "", "Popular", true));
        menuItems.add(new MenuItem("classic", restaurantId, "Classic Meal", "Reliable daily meal", 52000, "", "Main", true));
        return menuItems;
    }
}
