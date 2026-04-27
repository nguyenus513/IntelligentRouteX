package com.routefood.app.core.firebase;

import com.google.firebase.firestore.CollectionReference;
import com.google.firebase.firestore.FirebaseFirestore;

public class FirebaseRefs {
    private final FirebaseFirestore firestore;

    public FirebaseRefs() {
        firestore = FirebaseFirestore.getInstance();
    }

    public CollectionReference users() {
        return firestore.collection("users");
    }

    public CollectionReference drivers() {
        return firestore.collection("drivers");
    }

    public CollectionReference restaurants() {
        return firestore.collection("restaurants");
    }

    public CollectionReference orders() {
        return firestore.collection("orders");
    }

    public CollectionReference assignments() {
        return firestore.collection("assignments");
    }

    public CollectionReference menuItems(String restaurantId) {
        return restaurants().document(restaurantId).collection("menu_items");
    }
}
