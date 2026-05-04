# Phase 69 Dataset Matrix

| Dataset | Type | Scenarios / Instances | Purpose | Expected Bottleneck |
|---|---|---|---|---|
| Li-Lim 8-case | Academic PDPTW | `lrc202,lrc206,lrc106,lrc104,lrc108,LRC1_2_7,LRC281,LC1_4_8` | Pickup-delivery, time windows, vehicle-loss regression checks | route-pool budget, vehicle count, distance quality |
| synthetic-food-smoke | Production-like synthetic PDPTW | `lunch_peak`, `rain_peak` | Fast food-dispatch sanity check | time windows, peak/rain traffic |
| synthetic-food-full | Production-like synthetic PDPTW | `lunch_peak`, `dinner_peak`, `apartment_cluster`, `rain_peak`, `sparse_suburban`, `cancellation_risk` | Full synthetic dispatch feasibility/stability evaluation | food-like time windows, clustering, traffic, cancellation risk |
| future real replay logs | Production replay | pending | Validate live orders/drivers/activeRoutes adapter | SLA tail, online churn, fallback behavior |
| future time-dependent traffic | Production stress | pending | Validate traffic-sensitive dispatch | travel-time uncertainty, rain/peak congestion |

Each dataset should be reported with request count, driver count, time-window tightness, traffic multiplier, clustered dropoff ratio, stress flags, and expected bottleneck before production claims are made.
