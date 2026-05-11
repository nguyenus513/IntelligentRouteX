package com.routefood.app.data.repository;

import com.google.firebase.firestore.QueryDocumentSnapshot;
import com.routefood.app.core.firebase.FirebaseRefs;
import com.routefood.app.core.supabase.SupabaseRestClient;
import com.routefood.app.data.model.GeoPoint;
import com.routefood.app.data.model.MenuItem;
import com.routefood.app.data.model.Restaurant;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Map;

import org.json.JSONArray;
import org.json.JSONObject;

public class RestaurantRepository {
    private final FirebaseRefs refs;
    private final SupabaseRestClient supabase;

    public RestaurantRepository() {
        FirebaseRefs firebaseRefs;
        try {
            firebaseRefs = new FirebaseRefs();
        } catch (IllegalStateException error) {
            firebaseRefs = null;
        }
        refs = firebaseRefs;
        supabase = new SupabaseRestClient();
    }

    public void loadActiveRestaurants(RepositoryCallback<List<Restaurant>> callback) {
        if (supabase.isConfigured()) {
            Map<String, String> query = SupabaseRestClient.query();
            query.put("select", "id,name,rating,prep_time_min,status,tags,metadata");
            query.put("status", "in.(open,busy)");
            query.put("order", "rating.desc");
            query.put("limit", "30");
            supabase.select("restaurants", query, new SupabaseRestClient.JsonArrayCallback() {
                @Override
                public void onSuccess(JSONArray array) {
                    List<Restaurant> restaurants = restaurantsFromSupabase(array);
                    if (restaurants.isEmpty()) {
                        loadFirebaseRestaurants(callback);
                    } else {
                        callback.onSuccess(restaurants);
                    }
                }

                @Override
                public void onError(Exception error) {
                    loadFirebaseRestaurants(callback);
                }
            });
            return;
        }
        loadFirebaseRestaurants(callback);
    }

    private void loadFirebaseRestaurants(RepositoryCallback<List<Restaurant>> callback) {
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
        if (supabase.isConfigured()) {
            Map<String, String> query = SupabaseRestClient.query();
            query.put("select", "id,restaurant_id,name,description,price,available,tags");
            query.put("restaurant_id", "eq." + restaurantId);
            query.put("available", "eq.true");
            query.put("limit", "80");
            supabase.select("menu_items", query, new SupabaseRestClient.JsonArrayCallback() {
                @Override
                public void onSuccess(JSONArray array) {
                    List<MenuItem> items = menuItemsFromSupabase(array, restaurantId);
                    if (items.isEmpty()) {
                        loadFirebaseMenuItems(restaurantId, callback);
                    } else {
                        callback.onSuccess(items);
                    }
                }

                @Override
                public void onError(Exception error) {
                    loadFirebaseMenuItems(restaurantId, callback);
                }
            });
            return;
        }
        loadFirebaseMenuItems(restaurantId, callback);
    }

    private void loadFirebaseMenuItems(String restaurantId, RepositoryCallback<List<MenuItem>> callback) {
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


    private List<Restaurant> restaurantsFromSupabase(JSONArray array) {
        List<Restaurant> restaurants = new ArrayList<>();
        for (int index = 0; index < array.length(); index++) {
            JSONObject item = array.optJSONObject(index);
            if (item == null) continue;
            JSONArray tags = item.optJSONArray("tags");
            List<String> categories = new ArrayList<>();
            if (tags != null) {
                for (int tagIndex = 0; tagIndex < tags.length(); tagIndex++) {
                    categories.add(tags.optString(tagIndex));
                }
            }
            JSONObject metadata = item.optJSONObject("metadata");
            restaurants.add(new Restaurant(
                    item.optString("id"),
                    item.optString("name", "Unnamed restaurant"),
                    metadata == null ? "" : metadata.optString("imageUrl", ""),
                    item.optDouble("rating", 4.5),
                    metadata == null ? "Ho Chi Minh City" : metadata.optString("address", "Ho Chi Minh City"),
                    new GeoPoint(10.7741, 106.7038),
                    categories,
                    item.optInt("prep_time_min", 15),
                    !"closed".equals(item.optString("status"))));
        }
        return restaurants;
    }

    private List<MenuItem> menuItemsFromSupabase(JSONArray array, String fallbackRestaurantId) {
        List<MenuItem> menuItems = new ArrayList<>();
        for (int index = 0; index < array.length(); index++) {
            JSONObject item = array.optJSONObject(index);
            if (item == null) continue;
            JSONArray tags = item.optJSONArray("tags");
            String category = tags != null && tags.length() > 0 ? tags.optString(0, "Main") : "Main";
            menuItems.add(new MenuItem(
                    item.optString("id"),
                    item.optString("restaurant_id", fallbackRestaurantId),
                    item.optString("name", "Menu item"),
                    item.optString("description", ""),
                    item.optLong("price", 0),
                    "",
                    category,
                    item.optBoolean("available", true)));
        }
        return menuItems;
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
