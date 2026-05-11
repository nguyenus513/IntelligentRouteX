package com.routefood.app.feature.user.restaurant;

import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.TextView;

import androidx.annotation.NonNull;
import androidx.recyclerview.widget.RecyclerView;

import com.google.android.material.button.MaterialButton;
import com.routefood.app.R;
import com.routefood.app.data.model.MenuItem;

import java.util.ArrayList;
import java.util.List;

public class MenuAdapter extends RecyclerView.Adapter<MenuAdapter.MenuViewHolder> {
    public interface Listener {
        void onAdd(MenuItem item);
    }

    private final Listener listener;
    private final List<MenuItem> items = new ArrayList<>();

    public MenuAdapter(Listener listener) {
        this.listener = listener;
    }

    public void submitList(List<MenuItem> nextItems) {
        items.clear();
        items.addAll(nextItems);
        notifyDataSetChanged();
    }

    @NonNull
    @Override
    public MenuViewHolder onCreateViewHolder(@NonNull ViewGroup parent, int viewType) {
        return new MenuViewHolder(LayoutInflater.from(parent.getContext()).inflate(R.layout.item_menu_food, parent, false));
    }

    @Override
    public void onBindViewHolder(@NonNull MenuViewHolder holder, int position) {
        MenuItem item = items.get(position);
        holder.nameText.setText(item.name() + " • " + item.price() + "đ");
        holder.descriptionText.setText(item.description());
        holder.addButton.setContentDescription("Thêm " + item.name());
        holder.addButton.setOnClickListener(view -> listener.onAdd(item));
    }

    @Override
    public int getItemCount() {
        return items.size();
    }

    static class MenuViewHolder extends RecyclerView.ViewHolder {
        final TextView nameText;
        final TextView descriptionText;
        final MaterialButton addButton;

        MenuViewHolder(@NonNull View itemView) {
            super(itemView);
            nameText = itemView.findViewById(R.id.menuNameText);
            descriptionText = itemView.findViewById(R.id.menuDescriptionText);
            addButton = itemView.findViewById(R.id.addMenuItemButton);
        }
    }
}
