package com.routefood.app.data.repository;

import android.content.Context;
import android.content.SharedPreferences;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class CartStore {
    private static final String PREFS_NAME = "routefood_cart";
    private static final String KEY_RESTAURANT_ID = "restaurant_id";
    private final SharedPreferences preferences;

    public CartStore(Context context) {
        preferences = context.getApplicationContext().getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
    }

    public void addItem(String restaurantId, String itemId, String name, long price) {
        SharedPreferences.Editor editor = preferences.edit();
        if (!restaurantId.equals(preferences.getString(KEY_RESTAURANT_ID, ""))) {
            editor.clear();
            editor.putString(KEY_RESTAURANT_ID, restaurantId);
        }
        int quantity = preferences.getInt(quantityKey(itemId), 0) + 1;
        editor.putString(nameKey(itemId), name);
        editor.putLong(priceKey(itemId), price);
        editor.putInt(quantityKey(itemId), quantity);
        editor.apply();
    }

    public String restaurantId() {
        return preferences.getString(KEY_RESTAURANT_ID, "");
    }

    public List<Map<String, Object>> itemsPayload() {
        List<Map<String, Object>> items = new ArrayList<>();
        for (Map.Entry<String, ?> entry : preferences.getAll().entrySet()) {
            if (!entry.getKey().startsWith("qty_")) {
                continue;
            }
            String itemId = entry.getKey().substring(4);
            int quantity = preferences.getInt(quantityKey(itemId), 0);
            if (quantity <= 0) {
                continue;
            }
            Map<String, Object> item = new HashMap<>();
            item.put("itemId", itemId);
            item.put("name", preferences.getString(nameKey(itemId), "Item"));
            item.put("price", preferences.getLong(priceKey(itemId), 0));
            item.put("quantity", quantity);
            items.add(item);
        }
        return items;
    }

    public long subtotal() {
        long total = 0;
        for (Map<String, Object> item : itemsPayload()) {
            total += ((Number) item.get("price")).longValue() * ((Number) item.get("quantity")).intValue();
        }
        return total;
    }

    public void clear() {
        preferences.edit().clear().apply();
    }

    private String nameKey(String itemId) {
        return "name_" + itemId;
    }

    private String priceKey(String itemId) {
        return "price_" + itemId;
    }

    private String quantityKey(String itemId) {
        return "qty_" + itemId;
    }
}
