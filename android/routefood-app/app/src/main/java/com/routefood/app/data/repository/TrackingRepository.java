package com.routefood.app.data.repository;

import com.google.firebase.database.FirebaseDatabase;

public class TrackingRepository {
    public com.google.firebase.database.DatabaseReference driverLocation(String driverId) {
        return FirebaseDatabase.getInstance().getReference("driver_locations").child(driverId);
    }
}
