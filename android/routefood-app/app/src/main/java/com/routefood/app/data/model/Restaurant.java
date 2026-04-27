package com.routefood.app.data.model;

import com.google.firebase.firestore.DocumentSnapshot;

import java.util.ArrayList;
import java.util.List;

public class Restaurant {
    private final String id;
    private final String name;
    private final String imageUrl;
    private final double rating;
    private final String address;
    private final GeoPoint geo;
    private final List<String> categories;
    private final int averagePrepTimeMin;
    private final boolean active;

    public Restaurant(String id, String name, String imageUrl, double rating, String address,
                      GeoPoint geo, List<String> categories, int averagePrepTimeMin, boolean active) {
        this.id = id;
        this.name = name;
        this.imageUrl = imageUrl;
        this.rating = rating;
        this.address = address;
        this.geo = geo;
        this.categories = categories;
        this.averagePrepTimeMin = averagePrepTimeMin;
        this.active = active;
    }

    public String id() {
        return id;
    }

    public String name() {
        return name;
    }

    public String imageUrl() {
        return imageUrl;
    }

    public double rating() {
        return rating;
    }

    public String address() {
        return address;
    }

    public GeoPoint geo() {
        return geo;
    }

    public List<String> categories() {
        return categories;
    }

    public int averagePrepTimeMin() {
        return averagePrepTimeMin;
    }

    public boolean active() {
        return active;
    }

    public static Restaurant fromDocument(DocumentSnapshot document) {
        List<String> categories = new ArrayList<>();
        Object rawCategories = document.get("categories");
        if (rawCategories instanceof List<?>) {
            for (Object category : (List<?>) rawCategories) {
                if (category instanceof String) {
                    categories.add((String) category);
                }
            }
        }
        return new Restaurant(
                document.getId(),
                valueOrDefault(document.getString("name"), "Unnamed restaurant"),
                valueOrDefault(document.getString("imageUrl"), ""),
                numberOrDefault(document.get("rating"), 0),
                valueOrDefault(document.getString("address"), "Ho Chi Minh City"),
                GeoPoint.fromFirestore(document.get("geo")),
                categories,
                (int) numberOrDefault(document.get("avgPrepTimeMin"), 15),
                Boolean.TRUE.equals(document.getBoolean("active")));
    }

    private static String valueOrDefault(String value, String fallback) {
        return value == null || value.isEmpty() ? fallback : value;
    }

    private static double numberOrDefault(Object value, double fallback) {
        return value instanceof Number ? ((Number) value).doubleValue() : fallback;
    }
}
