package com.routefood.app.core.map;

import android.content.Context;
import android.util.AttributeSet;
import android.webkit.WebSettings;
import android.webkit.WebView;

import com.routefood.app.data.model.GeoPoint;
import com.routefood.app.data.model.RouteStop;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

public class LeafletMapView extends WebView {
    public LeafletMapView(Context context) {
        super(context);
        init();
    }

    public LeafletMapView(Context context, AttributeSet attrs) {
        super(context, attrs);
        init();
    }

    private void init() {
        WebSettings settings = getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setLoadWithOverviewMode(true);
        settings.setUseWideViewPort(true);
        setBackgroundColor(0xFF050505);
    }

    public void setDeliveryRoute(GeoPoint driver, GeoPoint pickup, GeoPoint dropoff, List<GeoPoint> routePoints, String label) {
        setDeliveryRoute(driver, pickup, dropoff, routePoints, null, label, "Single order");
    }

    public void setDeliveryRoute(GeoPoint driver, GeoPoint pickup, GeoPoint dropoff, List<GeoPoint> pickupLeg, List<GeoPoint> deliveryLeg, String label, String batchLabel) {
        List<GeoPoint> safePickupLeg = pickupLeg == null || pickupLeg.isEmpty() ? Arrays.asList(driver, pickup) : pickupLeg;
        List<GeoPoint> safeDeliveryLeg = deliveryLeg == null || deliveryLeg.isEmpty() ? Arrays.asList(pickup, dropoff) : deliveryLeg;
        loadDataWithBaseURL("https://routefood.local/", html(driver, pickup, dropoff, safePickupLeg, safeDeliveryLeg, label, batchLabel), "text/html", "UTF-8", null);
    }

    public void setBatchRoute(
            GeoPoint driver,
            GeoPoint pickupOne,
            GeoPoint pickupTwo,
            GeoPoint dropoffOne,
            GeoPoint dropoffTwo,
            List<GeoPoint> driverToPickupOne,
            List<GeoPoint> pickupOneToPickupTwo,
            List<GeoPoint> pickupTwoToDropoffOne,
            List<GeoPoint> dropoffOneToDropoffTwo,
            String activeStopLabel,
            String batchSummaryLabel
    ) {
        List<GeoPoint> safeDriverToPickupOne = driverToPickupOne == null || driverToPickupOne.isEmpty() ? Arrays.asList(driver, pickupOne) : driverToPickupOne;
        List<GeoPoint> safePickupOneToPickupTwo = pickupOneToPickupTwo == null || pickupOneToPickupTwo.isEmpty() ? Arrays.asList(pickupOne, pickupTwo) : pickupOneToPickupTwo;
        List<GeoPoint> safePickupTwoToDropoffOne = pickupTwoToDropoffOne == null || pickupTwoToDropoffOne.isEmpty() ? Arrays.asList(pickupTwo, dropoffOne) : pickupTwoToDropoffOne;
        List<GeoPoint> safeDropoffOneToDropoffTwo = dropoffOneToDropoffTwo == null || dropoffOneToDropoffTwo.isEmpty() ? Arrays.asList(dropoffOne, dropoffTwo) : dropoffOneToDropoffTwo;
        loadDataWithBaseURL(
                "https://routefood.local/",
                batchHtml(driver, pickupOne, pickupTwo, dropoffOne, dropoffTwo, safeDriverToPickupOne, safePickupOneToPickupTwo, safePickupTwoToDropoffOne, safeDropoffOneToDropoffTwo, activeStopLabel, batchSummaryLabel),
                "text/html",
                "UTF-8",
                null);
    }

    public void setRoutePlan(GeoPoint driver, List<RouteStop> stops, List<GeoPoint> roadRoute, String activeStopLabel, String batchSummaryLabel) {
        if (stops == null || stops.isEmpty()) {
            return;
        }
        List<GeoPoint> safeRoadRoute = roadRoute == null || roadRoute.isEmpty() ? fallbackPoints(driver, stops) : roadRoute;
        loadDataWithBaseURL(
                "https://routefood.local/",
                routePlanHtml(driver, stops, safeRoadRoute, activeStopLabel, batchSummaryLabel),
                "text/html",
                "UTF-8",
                null);
    }

    private String html(GeoPoint driver, GeoPoint pickup, GeoPoint dropoff, List<GeoPoint> pickupLeg, List<GeoPoint> deliveryLeg, String label, String batchLabel) {
        String allPoints = jsPoints(join(pickupLeg, deliveryLeg));
        return "<!doctype html><html><head><meta name='viewport' content='width=device-width,initial-scale=1,maximum-scale=5,user-scalable=yes'>"
                + "<link rel='stylesheet' href='https://unpkg.com/leaflet@1.9.4/dist/leaflet.css'/>"
                + "<script src='https://unpkg.com/leaflet@1.9.4/dist/leaflet.js'></script>"
                + "<style>" + commonCss() + "</style></head>"
                + "<body><div id='map'></div><script>"
                + "const driver=" + jsPoint(driver) + ";const pickup=" + jsPoint(pickup) + ";const dropoff=" + jsPoint(dropoff) + ";"
                + "const pickupLeg=" + jsPoints(pickupLeg) + ";const deliveryLeg=" + jsPoints(deliveryLeg) + ";const allPoints=" + allPoints + ";"
                + "const compact=(window.innerHeight<330);const map=L.map('map',{zoomControl:true,attributionControl:true,preferCanvas:true,dragging:true,touchZoom:true,doubleClickZoom:true,scrollWheelZoom:true,boxZoom:false,tap:true,zoomSnap:.25,zoomDelta:.5}).setView(driver,15);"
                + "L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:20,maxNativeZoom:19,detectRetina:true,attribution:'OpenStreetMap'}).addTo(map);L.control.scale({metric:true,imperial:false,position:'bottomleft'}).addTo(map);"
                + "const icon=(c)=>L.divIcon({className:'',html:`<div class=\"pin ${c}\"></div>`,iconSize:[26,26],iconAnchor:[13,13]});"
                + "L.polyline(pickupLeg,{color:'#050505',weight:9,opacity:.55,lineCap:'round',lineJoin:'round'}).addTo(map);"
                + "L.polyline(deliveryLeg,{color:'#050505',weight:9,opacity:.55,lineCap:'round',lineJoin:'round'}).addTo(map);"
                + "L.polyline(pickupLeg,{color:'#FFFFFF',weight:5,opacity:.96,lineCap:'round',lineJoin:'round'}).addTo(map);"
                + "L.polyline(deliveryLeg,{color:'#7EE787',weight:5,opacity:.96,lineCap:'round',lineJoin:'round'}).addTo(map);"
                + "L.polyline(deliveryLeg,{color:'#FFFFFF',weight:1.6,opacity:.85,dashArray:'6 9',lineCap:'round'}).addTo(map);"
                + "L.marker(driver,{icon:icon('driver')}).addTo(map);L.marker(pickup,{icon:icon('')}).addTo(map);L.marker(dropoff,{icon:icon('drop')}).addTo(map);"
                + "const mid=allPoints[Math.max(0,Math.floor(allPoints.length*.48))];"
                + "if(window.innerHeight>=330){L.marker(mid,{icon:L.divIcon({className:'',html:'<div class=\"label\">" + escape(label) + "</div>',iconSize:[140,28],iconAnchor:[70,14]})}).addTo(map);}"
                + "if(!compact){L.marker(allPoints[Math.max(0,Math.floor(allPoints.length*.18))],{icon:L.divIcon({className:'',html:'<div class=\"batch-label\">" + escape(batchLabel) + "</div>',iconSize:[150,28],iconAnchor:[75,14]})}).addTo(map);}"
                + "const bounds=L.latLngBounds(allPoints);const fit=()=>map.fitBounds(bounds,{paddingTopLeft:[24,compact?34:92],paddingBottomRight:[24,compact?34:170],maxZoom:compact?16:17});fit();const focus=L.control({position:'bottomright'});focus.onAdd=()=>{const div=L.DomUtil.create('button','focus-route');div.type='button';div.innerHTML='ROUTE';L.DomEvent.disableClickPropagation(div);L.DomEvent.on(div,'click',fit);return div;};focus.addTo(map);const follow=L.control({position:'bottomright'});follow.onAdd=()=>{const div=L.DomUtil.create('button','focus-driver');div.type='button';div.innerHTML='DRIVER';L.DomEvent.disableClickPropagation(div);L.DomEvent.on(div,'click',()=>map.flyTo(driver,18,{duration:.55}));return div;};follow.addTo(map);"
                + "</script></body></html>";
    }

    private String batchHtml(
            GeoPoint driver,
            GeoPoint pickupOne,
            GeoPoint pickupTwo,
            GeoPoint dropoffOne,
            GeoPoint dropoffTwo,
            List<GeoPoint> driverToPickupOne,
            List<GeoPoint> pickupOneToPickupTwo,
            List<GeoPoint> pickupTwoToDropoffOne,
            List<GeoPoint> dropoffOneToDropoffTwo,
            String activeStopLabel,
            String batchSummaryLabel
    ) {
        java.util.ArrayList<GeoPoint> allRoutePoints = new java.util.ArrayList<>();
        allRoutePoints.addAll(driverToPickupOne);
        allRoutePoints.addAll(pickupOneToPickupTwo);
        allRoutePoints.addAll(pickupTwoToDropoffOne);
        allRoutePoints.addAll(dropoffOneToDropoffTwo);
        return "<!doctype html><html><head><meta name='viewport' content='width=device-width,initial-scale=1,maximum-scale=5,user-scalable=yes'>"
                + "<link rel='stylesheet' href='https://unpkg.com/leaflet@1.9.4/dist/leaflet.css'/>"
                + "<script src='https://unpkg.com/leaflet@1.9.4/dist/leaflet.js'></script>"
                + "<style>" + commonCss() + "</style></head>"
                + "<body><div id='map'></div><script>"
                + "const driver=" + jsPoint(driver) + ";const p1=" + jsPoint(pickupOne) + ";const p2=" + jsPoint(pickupTwo) + ";const d1=" + jsPoint(dropoffOne) + ";const d2=" + jsPoint(dropoffTwo) + ";"
                + "const l1=" + jsPoints(driverToPickupOne) + ";const l2=" + jsPoints(pickupOneToPickupTwo) + ";const l3=" + jsPoints(pickupTwoToDropoffOne) + ";const l4=" + jsPoints(dropoffOneToDropoffTwo) + ";const allPoints=" + jsPoints(allRoutePoints) + ";"
                + "const compact=(window.innerHeight<330);const map=L.map('map',{zoomControl:true,attributionControl:true,preferCanvas:true,dragging:true,touchZoom:true,doubleClickZoom:true,scrollWheelZoom:true,boxZoom:false,tap:true,zoomSnap:.25,zoomDelta:.5}).setView(driver,15);"
                + "L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:20,maxNativeZoom:19,detectRetina:true,attribution:'OpenStreetMap'}).addTo(map);L.control.scale({metric:true,imperial:false,position:'bottomleft'}).addTo(map);"
                + "const leg=(pts,color,dash)=>{L.polyline(pts,{color:'#050505',weight:10,opacity:.62,lineCap:'round',lineJoin:'round'}).addTo(map);L.polyline(pts,{color:color,weight:5.4,opacity:.98,lineCap:'round',lineJoin:'round',dashArray:dash||null}).addTo(map);};"
                + "leg(l1,'#FFFFFF');leg(l2,'#FFFFFF','2 8');leg(l3,'#7EE787');leg(l4,'#7EE787','6 8');"
                + "const stop=(point,label,type)=>L.marker(point,{icon:L.divIcon({className:'',html:`<div class=\"stop ${type}\">${label}</div>`,iconSize:[34,34],iconAnchor:[17,17]})}).addTo(map);"
                + "L.marker(driver,{icon:L.divIcon({className:'',html:'<div class=\"pin driver\"></div>',iconSize:[26,26],iconAnchor:[13,13]})}).addTo(map);stop(p1,'P1','pickup');stop(p2,'P2','pickup');stop(d1,'D1','drop');stop(d2,'D2','drop');"
                + "if(!compact){const mid=allPoints[Math.max(0,Math.floor(allPoints.length*.48))];L.marker(mid,{icon:L.divIcon({className:'',html:'<div class=\"label\">" + escape(activeStopLabel) + "</div>',iconSize:[150,28],iconAnchor:[75,14]})}).addTo(map);const legend=L.control({position:'topright'});legend.onAdd=()=>{const div=L.DomUtil.create('div','map-legend');div.innerHTML='PICKUP <b></b> DROPOFF <i></i><br><span>" + escape(batchSummaryLabel) + "</span>';return div;};legend.addTo(map);}"
                + "const bounds=L.latLngBounds(allPoints);const fit=()=>map.fitBounds(bounds,{paddingTopLeft:[24,compact?24:88],paddingBottomRight:[24,compact?30:188],maxZoom:compact?16:17});fit();const focus=L.control({position:'bottomright'});focus.onAdd=()=>{const div=L.DomUtil.create('button','focus-route');div.type='button';div.innerHTML='ROUTE';L.DomEvent.disableClickPropagation(div);L.DomEvent.on(div,'click',fit);return div;};focus.addTo(map);const follow=L.control({position:'bottomright'});follow.onAdd=()=>{const div=L.DomUtil.create('button','focus-driver');div.type='button';div.innerHTML='DRIVER';L.DomEvent.disableClickPropagation(div);L.DomEvent.on(div,'click',()=>map.flyTo(driver,18,{duration:.55}));return div;};follow.addTo(map);"
                + "</script></body></html>";
    }

    private String commonCss() {
        return "html,body,#map{height:100%;margin:0;background:#050505;overflow:hidden;} #map{filter:saturate(.58) contrast(1.08) brightness(.88);} .leaflet-control-attribution{font:600 9px system-ui;background:rgba(5,5,5,.72);color:#aaa;border-radius:999px;padding:2px 8px;} .leaflet-control-zoom{border:0!important;border-radius:18px!important;overflow:hidden;box-shadow:0 18px 45px rgba(0,0,0,.42)!important;} .leaflet-control-zoom a{width:42px!important;height:42px!important;line-height:42px!important;background:rgba(5,5,5,.82)!important;color:#fff!important;border:1px solid rgba(255,255,255,.14)!important;font:900 20px system-ui!important;} .leaflet-control-scale-line{background:rgba(5,5,5,.72)!important;color:#fff!important;border:1px solid rgba(255,255,255,.16)!important;border-radius:999px!important;padding:3px 9px!important;font:800 10px system-ui!important;} .focus-route,.focus-driver{height:38px;min-width:72px;margin:6px 0 0 0;border:1px solid rgba(255,255,255,.16);border-radius:999px;background:rgba(5,5,5,.82);color:#fff;font:900 10px system-ui;letter-spacing:.08em;box-shadow:0 16px 38px rgba(0,0,0,.36);} .focus-driver{background:#7EE787;color:#050505;} .pin{width:18px;height:18px;border-radius:999px;background:#fff;border:4px solid rgba(5,5,5,.75);box-shadow:0 0 0 8px rgba(255,255,255,.14),0 10px 24px rgba(0,0,0,.35);} .pin.driver{background:#7EE787;} .pin.drop{background:#F2CC60;} .label{font:800 11px system-ui;letter-spacing:.08em;color:#050505;background:#fff;border-radius:999px;padding:7px 11px;white-space:nowrap;box-shadow:0 12px 30px rgba(0,0,0,.35);} .batch-label{font:700 10px system-ui;letter-spacing:.08em;color:white;background:rgba(5,5,5,.76);border:1px solid rgba(255,255,255,.2);border-radius:999px;padding:6px 10px;white-space:nowrap;backdrop-filter:blur(16px);} .stop{width:34px;height:34px;border-radius:999px;display:grid;place-items:center;font:900 11px system-ui;letter-spacing:.03em;border:2px solid rgba(5,5,5,.85);box-shadow:0 0 0 7px rgba(255,255,255,.12),0 14px 26px rgba(0,0,0,.42);} .stop.pickup{background:#fff;color:#050505;} .stop.drop{background:#7EE787;color:#050505;} .map-legend{font:800 9px system-ui;letter-spacing:.09em;color:rgba(255,255,255,.88);background:rgba(5,5,5,.72);border:1px solid rgba(255,255,255,.16);border-radius:18px;padding:9px 11px;box-shadow:0 16px 40px rgba(0,0,0,.38);backdrop-filter:blur(18px);} .map-legend b,.map-legend i{display:inline-block;width:22px;height:4px;border-radius:999px;margin:0 7px 2px 5px;background:#fff;} .map-legend i{background:#7EE787;} .map-legend span{display:block;margin-top:4px;color:rgba(255,255,255,.62);letter-spacing:.02em;font:700 10px system-ui;}";
    }

    private String routePlanHtml(GeoPoint driver, List<RouteStop> stops, List<GeoPoint> roadRoute, String activeStopLabel, String batchSummaryLabel) {
        return "<!doctype html><html><head><meta name='viewport' content='width=device-width,initial-scale=1,maximum-scale=5,user-scalable=yes'>"
                + "<link rel='stylesheet' href='https://unpkg.com/leaflet@1.9.4/dist/leaflet.css'/>"
                + "<script src='https://unpkg.com/leaflet@1.9.4/dist/leaflet.js'></script>"
                + "<style>" + commonCss() + "</style></head>"
                + "<body><div id='map'></div><script>"
                + "const driver=" + jsPoint(driver) + ";const stops=" + jsStops(stops) + ";const route=" + jsPoints(roadRoute) + ";const allPoints=[driver,...stops.map(s=>s.point),...route];"
                + "const compact=(window.innerHeight<330);const map=L.map('map',{zoomControl:true,attributionControl:true,preferCanvas:true,dragging:true,touchZoom:true,doubleClickZoom:true,scrollWheelZoom:true,boxZoom:false,tap:true,zoomSnap:.25,zoomDelta:.5}).setView(driver,15);"
                + "L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:20,maxNativeZoom:19,detectRetina:true,attribution:'OpenStreetMap'}).addTo(map);L.control.scale({metric:true,imperial:false,position:'bottomleft'}).addTo(map);"
                + "L.polyline(route,{color:'#050505',weight:10,opacity:.62,lineCap:'round',lineJoin:'round'}).addTo(map);L.polyline(route,{color:'#7EE787',weight:5.4,opacity:.98,lineCap:'round',lineJoin:'round'}).addTo(map);L.polyline(route,{color:'#FFFFFF',weight:1.5,opacity:.78,dashArray:'7 10',lineCap:'round'}).addTo(map);"
                + "L.marker(driver,{icon:L.divIcon({className:'',html:'<div class=\"pin driver\"></div>',iconSize:[26,26],iconAnchor:[13,13]})}).addTo(map);"
                + "stops.forEach(s=>L.marker(s.point,{icon:L.divIcon({className:'',html:`<div class=\"stop ${s.type==='dropoff'?'drop':'pickup'}\">${s.label}</div>`,iconSize:[34,34],iconAnchor:[17,17]})}).addTo(map).bindTooltip(s.title));"
                + "if(!compact){const mid=route[Math.max(0,Math.floor(route.length*.48))]||driver;L.marker(mid,{icon:L.divIcon({className:'',html:'<div class=\"label\">" + escape(activeStopLabel) + "</div>',iconSize:[170,28],iconAnchor:[85,14]})}).addTo(map);const legend=L.control({position:'topright'});legend.onAdd=()=>{const div=L.DomUtil.create('div','map-legend');div.innerHTML='ROUTEPLAN <b></b> LIVE ROAD <i></i><br><span>" + escape(batchSummaryLabel) + "</span>';return div;};legend.addTo(map);}"
                + "const bounds=L.latLngBounds(allPoints);const fit=()=>map.fitBounds(bounds,{paddingTopLeft:[24,compact?24:88],paddingBottomRight:[24,compact?30:188],maxZoom:compact?16:17});fit();const focus=L.control({position:'bottomright'});focus.onAdd=()=>{const div=L.DomUtil.create('button','focus-route');div.type='button';div.innerHTML='ROUTE';L.DomEvent.disableClickPropagation(div);L.DomEvent.on(div,'click',fit);return div;};focus.addTo(map);const follow=L.control({position:'bottomright'});follow.onAdd=()=>{const div=L.DomUtil.create('button','focus-driver');div.type='button';div.innerHTML='DRIVER';L.DomEvent.disableClickPropagation(div);L.DomEvent.on(div,'click',()=>map.flyTo(driver,18,{duration:.55}));return div;};follow.addTo(map);"
                + "</script></body></html>";
    }

    private List<GeoPoint> fallbackPoints(GeoPoint driver, List<RouteStop> stops) {
        ArrayList<GeoPoint> points = new ArrayList<>();
        points.add(driver);
        for (RouteStop stop : stops) {
            points.add(stop.location());
        }
        return points;
    }

    private List<GeoPoint> join(List<GeoPoint> first, List<GeoPoint> second) {
        java.util.ArrayList<GeoPoint> points = new java.util.ArrayList<>(first);
        if (!second.isEmpty()) {
            points.addAll(second);
        }
        return points;
    }

    private String jsPoints(List<GeoPoint> points) {
        StringBuilder builder = new StringBuilder("[");
        for (int index = 0; index < points.size(); index++) {
            if (index > 0) {
                builder.append(',');
            }
            builder.append(jsPoint(points.get(index)));
        }
        return builder.append(']').toString();
    }

    private String jsPoint(GeoPoint point) {
        return String.format(Locale.US, "[%f,%f]", point.latitude(), point.longitude());
    }

    private String jsStops(List<RouteStop> stops) {
        StringBuilder builder = new StringBuilder("[");
        for (int index = 0; index < stops.size(); index++) {
            RouteStop stop = stops.get(index);
            if (index > 0) builder.append(',');
            builder.append("{label:'")
                    .append(escape(stop.label()))
                    .append("',title:'")
                    .append(escape(stop.title()))
                    .append("',type:'")
                    .append(escape(stop.type()))
                    .append("',point:")
                    .append(jsPoint(stop.location()))
                    .append('}');
        }
        return builder.append(']').toString();
    }

    private String escape(String value) {
        return value == null ? "" : value.replace("\\", "\\\\").replace("'", "\\'").replace("\"", "&quot;");
    }
}
