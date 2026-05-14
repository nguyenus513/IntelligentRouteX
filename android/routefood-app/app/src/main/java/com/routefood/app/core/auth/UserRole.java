package com.routefood.app.core.auth;

public enum UserRole {
    USER("user"),
    DRIVER("driver"),
    ADMIN("ops_admin");

    private final String wireName;

    UserRole(String wireName) {
        this.wireName = wireName;
    }

    public String wireName() {
        return wireName;
    }

    public static UserRole fromWireName(String wireName) {
        for (UserRole role : values()) {
            if (role.wireName.equals(wireName)) {
                return role;
            }
        }
        return USER;
    }
}
