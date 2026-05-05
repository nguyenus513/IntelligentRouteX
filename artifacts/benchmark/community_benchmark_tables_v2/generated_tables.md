## Generated Numeric Tables

### Routing Aggregate by Dataset and Scale

| Dataset | Scale | Instances | Paired feasible | Feasible rate (%) | Vehicle gap vs OR-Tools | Distance gap vs OR-Tools (%) | Runtime (s) | Hard-violation rows |
|---|---|---|---|---|---|---|---|---|
| li-lim | large | 104 | 104 | 100.000 | 0.087 | 2.076 | 56.171 | 0 |
| li-lim | medium | 177 | 176 | 100.000 | 0.057 | 1.409 | 53.388 | 0 |
| li-lim | small | 73 | 59 | 80.822 | 0.119 | 1.661 | 45.022 | 0 |
| solomon | small | 6 | 6 | 100.000 | -1.833 | 3.580 | 60.580 | 0 |

### VROOM Li-Lim Live Comparator

| Instance | VROOM status | VROOM feasible | VROOM | Ours | Vehicle gap | Distance gap (%) | VROOM runtime (ms) |
|---|---|---|---|---|---|---|---|
| LRC202 | ok | no | 4/1398.020 | 5/1591.021 | - | - | 534 |
| LRC206 | ok | yes | 3/1159.033 | 4/1348.841 | 1 | 16.376 | 386 |
| LRC106 | ok | yes | 12/1474.085 | 12/1489.758 | 0 | 1.063 | 408 |
| LRC104 | ok | yes | 10/1129.338 | 11/1170.620 | 1 | 3.655 | 417 |
| LRC108 | ok | yes | 11/1167.174 | 12/1300.589 | 1 | 11.431 | 345 |
| LRC1_2_7 | ok | no | 17/3419.307 | 17/3782.925 | - | - | 1781 |
| LRC281 | vroom-timeout | no | -/- | 94/73280.848 | - | - | 60120 |
| LC1_4_8 | vroom-timeout | no | -/- | 43/10026.852 | - | - | 60076 |

### Food Dispatch Numeric Metrics

| Metric | Value |
|---|---|
| row_count | 3 |
| served_order_rate_pct | 100.000 |
| late_order_rate_pct | 0.000 |
| p95_delay | 12.212 |
| p95_food_on_vehicle_time | 11.465 |
| avg_order_to_delivery_time | 23.606 |
| p95_order_to_delivery_time | 48.952 |
| courier_utilization_pct | 98.485 |
| assignment_fairness_gini | 0.142 |
| courier_shift_violations | 0 |
| pickup_before_dropoff_violations | 0 |
| cost_per_order | not measured |
| p99_latency | not measured |

### Dynamic Dispatch Numeric Metrics

| Metric | Value |
|---|---|
| row_count | 3 |
| hard_violations | 0 |
| avg_route_stability_score | 1.000 |
| served_order_delta_vs_baseline | 0 |
| total_tardiness_delta_vs_baseline | 0.000 |
| p95_latency | not measured |
| p99_latency | not measured |
| cost_per_order | not measured |

### ML Ablation Numeric Metrics

| Component | Rows | Positive rows | Mean selector delta | Std selector delta | Mean robust delta | Std robust delta | Inference ms |
|---|---|---|---|---|---|---|---|
| forecast | 2 | 1 | -0.006 | 0.008 | 0.001 | 0.002 | not measured |
| greedrl | 15 | 1 | 0.012 | 0.047 | -0.026 | 0.045 | not measured |
| routefinder | 2 | 1 | 0.010 | 0.014 | 0.002 | 0.003 | not measured |
| tabular | 1 | 0 | 0.000 | 0.000 | 0.000 | 0.000 | not measured |
