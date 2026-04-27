package com.routefood.app.core.map;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Path;
import android.util.AttributeSet;
import android.view.View;

import androidx.annotation.Nullable;

import com.routefood.app.data.model.GeoPoint;

import java.util.ArrayList;
import java.util.List;

public class DemoMapView extends View {
    private static final double MIN_LAT = 10.70;
    private static final double MAX_LAT = 10.83;
    private static final double MIN_LNG = 106.62;
    private static final double MAX_LNG = 106.76;

    private final Paint backgroundPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint gridPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint routePaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint pickupPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint dropoffPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint driverPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint textPaint = new Paint(Paint.ANTI_ALIAS_FLAG);

    private GeoPoint pickup = new GeoPoint(10.7741, 106.7038);
    private GeoPoint dropoff = new GeoPoint(10.7942, 106.7218);
    private GeoPoint driver = new GeoPoint(10.776, 106.704);
    private final List<GeoPoint> routePoints = new ArrayList<>();
    private String label = "HCMC live route";

    public DemoMapView(Context context) {
        super(context);
        init();
    }

    public DemoMapView(Context context, @Nullable AttributeSet attrs) {
        super(context, attrs);
        init();
    }

    public void setRoute(@Nullable GeoPoint pickup, @Nullable GeoPoint dropoff, @Nullable GeoPoint driver, String label) {
        if (pickup != null) {
            this.pickup = pickup;
        }
        if (dropoff != null) {
            this.dropoff = dropoff;
        }
        if (driver != null) {
            this.driver = driver;
        }
        this.label = label == null ? "HCMC live route" : label;
        invalidate();
    }

    public void setRoadRoute(List<GeoPoint> points) {
        routePoints.clear();
        routePoints.addAll(points);
        invalidate();
    }

    private void init() {
        backgroundPaint.setColor(Color.rgb(232, 248, 238));
        gridPaint.setColor(Color.argb(90, 0, 177, 79));
        gridPaint.setStrokeWidth(2f);
        routePaint.setColor(Color.rgb(0, 177, 79));
        routePaint.setStrokeWidth(8f);
        routePaint.setStyle(Paint.Style.STROKE);
        routePaint.setStrokeCap(Paint.Cap.ROUND);
        pickupPaint.setColor(Color.rgb(255, 176, 0));
        dropoffPaint.setColor(Color.rgb(239, 68, 68));
        driverPaint.setColor(Color.rgb(17, 24, 39));
        textPaint.setColor(Color.rgb(17, 24, 39));
        textPaint.setTextSize(32f);
        textPaint.setFakeBoldText(true);
    }

    @Override
    protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        float width = getWidth();
        float height = getHeight();
        canvas.drawRoundRect(0, 0, width, height, 36, 36, backgroundPaint);
        drawGrid(canvas, width, height);
        drawRoute(canvas);
        drawMarker(canvas, pickup, pickupPaint, "P");
        drawMarker(canvas, dropoff, dropoffPaint, "U");
        drawMarker(canvas, driver, driverPaint, "D");
        canvas.drawText(label, 28, 46, textPaint);
    }

    private void drawGrid(Canvas canvas, float width, float height) {
        for (int i = 1; i < 5; i++) {
            float x = width * i / 5f;
            float y = height * i / 5f;
            canvas.drawLine(x, 0, x, height, gridPaint);
            canvas.drawLine(0, y, width, y, gridPaint);
        }
    }

    private void drawRoute(Canvas canvas) {
        Path path = new Path();
        if (!routePoints.isEmpty()) {
            GeoPoint first = routePoints.get(0);
            path.moveTo(x(first), y(first));
            for (int index = 1; index < routePoints.size(); index++) {
                GeoPoint point = routePoints.get(index);
                path.lineTo(x(point), y(point));
            }
        } else {
            path.moveTo(x(driver), y(driver));
            path.lineTo(x(pickup), y(pickup));
            path.lineTo(x(dropoff), y(dropoff));
        }
        canvas.drawPath(path, routePaint);
    }

    private void drawMarker(Canvas canvas, GeoPoint point, Paint paint, String text) {
        float x = x(point);
        float y = y(point);
        canvas.drawCircle(x, y, 24, paint);
        Paint markerTextPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        markerTextPaint.setColor(Color.WHITE);
        markerTextPaint.setTextSize(24f);
        markerTextPaint.setFakeBoldText(true);
        markerTextPaint.setTextAlign(Paint.Align.CENTER);
        canvas.drawText(text, x, y + 8, markerTextPaint);
    }

    private float x(GeoPoint point) {
        double normalized = (point.longitude() - MIN_LNG) / (MAX_LNG - MIN_LNG);
        return (float) (Math.max(0.05, Math.min(0.95, normalized)) * getWidth());
    }

    private float y(GeoPoint point) {
        double normalized = (MAX_LAT - point.latitude()) / (MAX_LAT - MIN_LAT);
        return (float) (Math.max(0.08, Math.min(0.92, normalized)) * getHeight());
    }
}
