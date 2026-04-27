package com.routefood.app.data.model;

public class UserProfile {
    private final String uid;
    private final String role;
    private final String displayName;
    private final String phone;
    private final String avatarUrl;
    private final boolean blocked;

    public UserProfile(String uid, String role, String displayName, String phone, String avatarUrl, boolean blocked) {
        this.uid = uid;
        this.role = role;
        this.displayName = displayName;
        this.phone = phone;
        this.avatarUrl = avatarUrl;
        this.blocked = blocked;
    }

    public String uid() {
        return uid;
    }

    public String role() {
        return role;
    }

    public String displayName() {
        return displayName;
    }

    public String phone() {
        return phone;
    }

    public String avatarUrl() {
        return avatarUrl;
    }

    public boolean blocked() {
        return blocked;
    }
}
