# Phase 70 Baseline Matrix

| Baseline | Role | Current Status | Interpretation |
|---|---|---|---|
| Phase 56F | Stable certification system | Promoted for certification/shadow-mode | Safety, determinism, hard budget, feasibility baseline |
| Phase 47 | Research-quality baseline | Previous research baseline | Useful quality reference, not strict certification baseline |
| VROOM | Industry / production-like comparator | Active comparator; capability verified on Phase 76 micro-suite | Strong external baseline; feasible 15/15 on capability suite; on strict synthetic food current run has no feasible solution |
| Internal checker | Feasibility oracle | Active | Validates exact coverage, pickup/dropoff, capacity, time windows |
| OR-Tools | Future optional baseline | Not part of current final claim | Useful additional algorithmic comparator |
| PyVRP | Future optional baseline | Not part of current final claim | Useful HGS-style comparator if PDPTW mapping is validated |

Current conclusion:

- Phase 56F wins synthetic food feasibility/stability: feasible `6/6`, hard violations `0`, overBudget `0`.
- VROOM wins some Li-Lim feasible cases on quality.
- VROOM capability status is verified on Phase 76: both feasible `15/15`, fair quality `10` ties, `5` Phase 56F distance wins, `0` VROOM distance wins.
- Synthetic food quality superiority remains inconclusive because VROOM has no feasible synthetic solution in the audited run.
