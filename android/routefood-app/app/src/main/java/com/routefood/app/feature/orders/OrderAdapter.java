package com.routefood.app.feature.orders;

import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.TextView;

import androidx.annotation.NonNull;
import androidx.recyclerview.widget.RecyclerView;

import com.routefood.app.R;
import com.routefood.app.data.model.Order;

import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Locale;

public class OrderAdapter extends RecyclerView.Adapter<OrderAdapter.ViewHolder> {
    private final List<Order> orders = new ArrayList<>();
    private final OnOrderClickListener listener;
    private static final SimpleDateFormat dateFormat = new SimpleDateFormat("MMM dd, yyyy", Locale.US);

    public interface OnOrderClickListener {
        void onOrderClicked(Order order);
    }

    public OrderAdapter(OnOrderClickListener listener) {
        this.listener = listener;
    }

    @NonNull
    @Override
    public ViewHolder onCreateViewHolder(@NonNull ViewGroup parent, int viewType) {
        View view = LayoutInflater.from(parent.getContext())
                .inflate(R.layout.item_order_card, parent, false);
        return new ViewHolder(view);
    }

    @Override
    public void onBindViewHolder(@NonNull ViewHolder holder, int position) {
        holder.bind(orders.get(position), listener);
    }

    @Override
    public int getItemCount() {
        return orders.size();
    }

    public void submitList(List<Order> nextOrders) {
        orders.clear();
        orders.addAll(nextOrders);
        notifyDataSetChanged();
    }

    static class ViewHolder extends RecyclerView.ViewHolder {
        private final TextView orderNumberText;
        private final TextView dateText;
        private final TextView statusText;
        private final TextView priceText;
        private final View statusDot;

        ViewHolder(@NonNull View itemView) {
            super(itemView);
            orderNumberText = itemView.findViewById(R.id.orderNumberText);
            dateText = itemView.findViewById(R.id.dateText);
            statusText = itemView.findViewById(R.id.statusText);
            priceText = itemView.findViewById(R.id.priceText);
            statusDot = itemView.findViewById(R.id.statusDot);
        }

        void bind(Order order, OrderAdapter.OnOrderClickListener listener) {
            orderNumberText.setText("#" + shortenId(order.id()));
            dateText.setText(dateFormat.format(new Date()));
            statusText.setText(formatStatus(order.status()));
            priceText.setText("VND " + (order.total() / 1000) + "K");

            setStatusColor(order.status());

            itemView.setOnClickListener(v -> listener.onOrderClicked(order));
        }

        private void setStatusColor(String status) {
            switch (status.toLowerCase()) {
                case "delivered":
                case "completed":
                    statusText.setTextColor(0xFF10B981);
                    statusDot.setBackgroundColor(0xFF10B981);
                    break;
                case "in_transit":
                case "delivering":
                    statusText.setTextColor(0xFFF59E0B);
                    statusDot.setBackgroundColor(0xFFF59E0B);
                    break;
                case "confirmed":
                    statusText.setTextColor(0xFF3B82F6);
                    statusDot.setBackgroundColor(0xFF3B82F6);
                    break;
                default:
                    statusText.setTextColor(0xFF6B7280);
                    statusDot.setBackgroundColor(0xFF6B7280);
            }
        }

        private String formatStatus(String status) {
            if (status == null) return "Unknown";
            String[] parts = status.split("_");
            StringBuilder result = new StringBuilder();
            for (int i = 0; i < parts.length; i++) {
                if (i > 0) result.append(" ");
                if (parts[i].length() > 0) {
                    result.append(Character.toUpperCase(parts[i].charAt(0)));
                    result.append(parts[i].substring(1).toLowerCase());
                }
            }
            return result.toString();
        }

        private String shortenId(String id) {
            if (id == null || id.length() <= 8) return id;
            return id.substring(0, 4) + "..." + id.substring(id.length() - 4);
        }
    }
}
