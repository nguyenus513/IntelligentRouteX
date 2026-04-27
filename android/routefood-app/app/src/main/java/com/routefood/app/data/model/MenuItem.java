package com.routefood.app.data.model;

import com.google.firebase.firestore.DocumentSnapshot;

public class MenuItem {
    private final String id;
    private final String restaurantId;
    private final String name;
    private final String description;
    private final long price;
    private final String imageUrl;
    private final String category;
    private final boolean available;

    public MenuItem(String id, String restaurantId, String name, String description, long price,
                    String imageUrl, String category, boolean available) {
        this.id = id;
        this.restaurantId = restaurantId;
        this.name = name;
        this.description = description;
        this.price = price;
        this.imageUrl = imageUrl;
        this.category = category;
        this.available = available;
    }

    public String id() {
        return id;
    }

    public String restaurantId() {
        return restaurantId;
    }

    public String name() {
        return name;
    }

    public String description() {
        return description;
    }

    public long price() {
        return price;
    }

    public String imageUrl() {
        return imageUrl;
    }

    public String category() {
        return category;
    }

    public boolean available() {
        return available;
    }

    public static MenuItem fromDocument(String restaurantId, DocumentSnapshot document) {
        return new MenuItem(
                document.getId(),
                restaurantId,
                valueOrDefault(document.getString("name"), "Unnamed item"),
                valueOrDefault(document.getString("description"), ""),
                longOrDefault(document.get("price"), 0),
                valueOrDefault(document.getString("imageUrl"), ""),
                valueOrDefault(document.getString("category"), "Popular"),
                !Boolean.FALSE.equals(document.getBoolean("available")));
    }

    private static String valueOrDefault(String value, String fallback) {
        return value == null || value.isEmpty() ? fallback : value;
    }

    private static long longOrDefault(Object value, long fallback) {
        return value instanceof Number ? ((Number) value).longValue() : fallback;
    }
}
