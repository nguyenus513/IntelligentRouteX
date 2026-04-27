package com.routefood.app.data.model;

public class CartItem {
    private final MenuItem menuItem;
    private final int quantity;
    private final String note;

    public CartItem(MenuItem menuItem, int quantity, String note) {
        this.menuItem = menuItem;
        this.quantity = quantity;
        this.note = note;
    }

    public MenuItem menuItem() {
        return menuItem;
    }

    public int quantity() {
        return quantity;
    }

    public String note() {
        return note;
    }

    public long lineTotal() {
        return menuItem.price() * quantity;
    }
}
