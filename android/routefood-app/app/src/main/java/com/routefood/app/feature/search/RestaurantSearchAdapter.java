package com.routefood.app.feature.search;

import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.TextView;

import androidx.annotation.NonNull;
import androidx.recyclerview.widget.RecyclerView;

import com.routefood.app.R;
import com.routefood.app.data.model.Restaurant;

import java.util.ArrayList;
import java.util.List;

public class RestaurantSearchAdapter extends RecyclerView.Adapter<RestaurantSearchAdapter.ViewHolder> {
    private final List<Restaurant> restaurants = new ArrayList<>();
    private final OnRestaurantClickListener listener;

    public interface OnRestaurantClickListener {
        void onRestaurantClicked(Restaurant restaurant);
    }

    public RestaurantSearchAdapter(OnRestaurantClickListener listener) {
        this.listener = listener;
    }

    @NonNull
    @Override
    public ViewHolder onCreateViewHolder(@NonNull ViewGroup parent, int viewType) {
        View view = LayoutInflater.from(parent.getContext())
                .inflate(R.layout.item_search_result, parent, false);
        return new ViewHolder(view);
    }

    @Override
    public void onBindViewHolder(@NonNull ViewHolder holder, int position) {
        holder.bind(restaurants.get(position), listener);
    }

    @Override
    public int getItemCount() {
        return restaurants.size();
    }

    public void submitList(List<Restaurant> nextRestaurants) {
        restaurants.clear();
        restaurants.addAll(nextRestaurants);
        notifyDataSetChanged();
    }

    static class ViewHolder extends RecyclerView.ViewHolder {
        private final TextView nameText;
        private final TextView metaText;
        private final TextView addressText;

        ViewHolder(@NonNull View itemView) {
            super(itemView);
            nameText = itemView.findViewById(R.id.searchResultName);
            metaText = itemView.findViewById(R.id.searchResultMeta);
            addressText = itemView.findViewById(R.id.searchResultAddress);
        }

        void bind(Restaurant restaurant, OnRestaurantClickListener listener) {
            nameText.setText(restaurant.name());
            String categories = String.join(", ", restaurant.categories());
            metaText.setText("Rating: " + restaurant.rating() + " • " + restaurant.averagePrepTimeMin() + " min");
            addressText.setText(categories.isEmpty() ? restaurant.address() : categories);
            itemView.setOnClickListener(v -> listener.onRestaurantClicked(restaurant));
        }
    }
}
