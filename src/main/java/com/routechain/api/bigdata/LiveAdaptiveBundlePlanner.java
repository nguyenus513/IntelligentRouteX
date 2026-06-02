package com.routechain.api.bigdata;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

final class LiveAdaptiveBundlePlanner {
    PlanResult plan(List<Map<String, Object>> orders) {
        List<Map<String, Object>> ranked = orders.stream()
                .sorted(Comparator.comparingDouble(this::admissionScore).reversed())
                .toList();
        List<BundleCandidate> candidates = buildCandidates(ranked);
        List<BundleCandidate> selected = greedySetPacking(candidates);
        double breakRisk = selected.stream().mapToDouble(BundleCandidate::breakRisk).average().orElse(0.0);
        double bundleScore = selected.stream().mapToDouble(BundleCandidate::score).sum();
        double coverage = orders.isEmpty() ? 1.0 : selected.stream().map(BundleCandidate::orderIds).flatMap(Set::stream).distinct().count() * 1.0 / orders.size();
        return new PlanResult(
                selected.size(),
                candidates.size(),
                round(bundleScore),
                round(breakRisk),
                round(coverage),
                selected.stream().map(BundleCandidate::asMap).toList());
    }

    private List<BundleCandidate> buildCandidates(List<Map<String, Object>> ranked) {
        List<BundleCandidate> candidates = new ArrayList<>();
        for (int i = 0; i < ranked.size(); i++) {
            Map<String, Object> seed = ranked.get(i);
            List<Map<String, Object>> members = new ArrayList<>();
            members.add(seed);
            for (int j = 0; j < ranked.size() && members.size() < 4; j++) {
                if (i == j) continue;
                Map<String, Object> candidate = ranked.get(j);
                if (compatible(seed, candidate)) members.add(candidate);
            }
            candidates.add(bundle(members));
        }
        candidates.sort(Comparator.comparingDouble(BundleCandidate::score).reversed());
        return candidates;
    }

    private List<BundleCandidate> greedySetPacking(List<BundleCandidate> candidates) {
        Set<String> used = new LinkedHashSet<>();
        List<BundleCandidate> selected = new ArrayList<>();
        for (BundleCandidate candidate : candidates) {
            if (candidate.orderIds().stream().noneMatch(used::contains)) {
                selected.add(candidate);
                used.addAll(candidate.orderIds());
            }
        }
        return selected;
    }

    private BundleCandidate bundle(List<Map<String, Object>> members) {
        Set<String> ids = new LinkedHashSet<>();
        for (Map<String, Object> member : members) ids.add(orderId(member));
        double score = members.stream().mapToDouble(this::admissionScore).sum() / Math.max(1, members.size())
                + Math.max(0, members.size() - 1) * 8.0
                - breakRisk(members) * 30.0;
        return new BundleCandidate(ids, round(score), round(breakRisk(members)), members.size());
    }

    private boolean compatible(Map<String, Object> left, Map<String, Object> right) {
        if (!String.valueOf(left.getOrDefault("_geoCell", "")).equals(String.valueOf(right.getOrDefault("_geoCell", "")))) return false;
        double etaGap = Math.abs(number(left, "promisedEtaMinutes", 45.0) - number(right, "promisedEtaMinutes", 45.0));
        if (etaGap > 30.0) return false;
        if (urgent(left) != urgent(right)) return number(left, "promisedEtaMinutes", 45.0) <= number(right, "promisedEtaMinutes", 45.0) || number(right, "promisedEtaMinutes", 45.0) <= number(left, "promisedEtaMinutes", 45.0);
        return true;
    }

    private double admissionScore(Map<String, Object> order) {
        long waitedMs = Math.max(0L, System.currentTimeMillis() - longNumber(order, "_bufferedAtMs", System.currentTimeMillis()));
        double ageScore = Math.min(100.0, waitedMs / 1000.0 * 3.0);
        double deadline = number(order, "promisedEtaMinutes", 45.0);
        double lateRisk = Math.max(0.0, 45.0 - deadline) * 2.0;
        double priority = number(order, "priority", 1.0) * 10.0;
        double urgentBoost = urgent(order) ? 100.0 : 0.0;
        double bundlePotential = "normal".equals(String.valueOf(order.getOrDefault("_lane", "normal"))) ? 10.0 : 4.0;
        return ageScore + lateRisk + priority + urgentBoost + bundlePotential;
    }

    private double breakRisk(List<Map<String, Object>> members) {
        double maxEta = members.stream().mapToDouble(order -> number(order, "promisedEtaMinutes", 45.0)).max().orElse(45.0);
        double minEta = members.stream().mapToDouble(order -> number(order, "promisedEtaMinutes", 45.0)).min().orElse(45.0);
        double etaRisk = Math.min(1.0, Math.max(0.0, maxEta - minEta) / 45.0);
        double urgentMix = members.stream().anyMatch(this::urgent) && members.stream().anyMatch(order -> !urgent(order)) ? 0.20 : 0.0;
        double sizeRisk = Math.max(0.0, members.size() - 3) * 0.08;
        return Math.min(1.0, etaRisk + urgentMix + sizeRisk);
    }

    private String orderId(Map<String, Object> order) {
        Object id = order.getOrDefault("externalOrderId", order.getOrDefault("orderId", "unknown"));
        return String.valueOf(id);
    }

    private boolean urgent(Map<String, Object> order) {
        return Boolean.TRUE.equals(order.get("urgent")) || "true".equalsIgnoreCase(String.valueOf(order.get("urgent")));
    }

    private double number(Map<String, Object> item, String key, double fallback) {
        Object value = item.get(key);
        if (value instanceof Number number) return number.doubleValue();
        try { return value == null ? fallback : Double.parseDouble(String.valueOf(value)); } catch (NumberFormatException ignored) { return fallback; }
    }

    private long longNumber(Map<String, Object> item, String key, long fallback) {
        Object value = item.get(key);
        if (value instanceof Number number) return number.longValue();
        try { return value == null ? fallback : Long.parseLong(String.valueOf(value)); } catch (NumberFormatException ignored) { return fallback; }
    }

    private double round(double value) { return Math.round(value * 100.0) / 100.0; }

    record PlanResult(int selectedBundleCount, int candidateBundleCount, double bundleScore, double breakRisk, double coverageRate, List<Map<String, Object>> bundles) {
        Map<String, Object> asMap() {
            Map<String, Object> map = new LinkedHashMap<>();
            map.put("admissionPolicy", "AGING_REGRET_PRIORITY");
            map.put("selectedBundleCount", selectedBundleCount);
            map.put("candidateBundleCount", candidateBundleCount);
            map.put("bundleScore", bundleScore);
            map.put("breakRisk", breakRisk);
            map.put("coverageRate", coverageRate);
            map.put("bundles", bundles);
            return map;
        }
    }

    private record BundleCandidate(Set<String> orderIds, double score, double breakRisk, int size) {
        Map<String, Object> asMap() {
            Map<String, Object> map = new LinkedHashMap<>();
            map.put("orderIds", orderIds);
            map.put("score", score);
            map.put("breakRisk", breakRisk);
            map.put("size", size);
            return map;
        }
    }
}
