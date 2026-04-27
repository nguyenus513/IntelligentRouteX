package com.routefood.app.feature.user.home;

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

public class RestaurantAdapter extends RecyclerView.Adapter<RestaurantAdapter.RestaurantViewHolder> {
    private final List<Restaurant> restaurants = new ArrayList<>();

    public void submitList(List<Restaurant> nextRestaurants) {
        restaurants.clear();
        restaurants.addAll(nextRestaurants);
        notifyDataSetChanged();
    }

    @NonNull
    @Override
    public RestaurantViewHolder onCreateViewHolder(@NonNull ViewGroup parent, int viewType) {
        View view = LayoutInflater.from(parent.getContext()).inflate(R.layout.item_restaurant_card, parent, false);
        return new RestaurantViewHolder(view);
    }

    @Override
    public void onBindViewHolder(@NonNull RestaurantViewHolder holder, int position) {
        holder.bind(restaurants.get(position));
    }

    @Override
    public int getItemCount() {
        return restaurants.size();
    }

    static class RestaurantViewHolder extends RecyclerView.ViewHolder {
        private final TextView nameText;
        private final TextView metaText;
        private final TextView addressText;

        RestaurantViewHolder(@NonNull View itemView) {
            super(itemView);
            nameText = itemView.findViewById(R.id.restaurantNameText);
            metaText = itemView.findViewById(R.id.restaurantMetaText);
            addressText = itemView.findViewById(R.id.restaurantAddressText);
        }

        void bind(Restaurant restaurant) {
            nameText.setText(restaurant.name());
            metaText.setText("★ " + restaurant.rating() + " • " + restaurant.averagePrepTimeMin() + " min • " + categories(restaurant));
            addressText.setText(restaurant.address());
        }

        private String categories(Restaurant restaurant) {
            if (restaurant.categories().isEmpty()) {
                return "Popular";
            }
            return android.text.TextUtils.join(", ", restaurant.categories());
        }
    }
}
