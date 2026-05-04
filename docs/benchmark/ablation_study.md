# Phase 73 Ablation Study

| Config | Quality Effect | Runtime Risk | Stability Effect |
|---|---|---|---|
| base-incumbent-only | baseline feasible construction | low | medium |
| + internal solver generator | candidate diversity and objective improvement | medium | requires deterministic candidate selection |
| + route-pool | vehicle/distance improvements when budget permits | high without hard cap | requires route-pool reserve and replay |
| + stable replay | no direct quality gain | low | high |
| + hard budget guard | may skip expensive improvements | low | high |
| + synthetic integration | food-like feasibility evidence | medium | dataset-dependent |

Conclusion: Phase 56F stability comes from stable replay plus hard budget guard; route-pool can improve quality but is a runtime-risk component without caps.
