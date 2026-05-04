# Phase 86 Objective Calibration Notes

Objective calibration is only considered after Phase 86 proves why feasible candidates are rejected.

Possible findings:

- `distance-improved-but-objective-rejected`: distance gain exists but global objective rejects it.
- `vehicle-regression-rejected`: route count worsens.
- `tail-risk-regression-rejected`: food SLA/tail metrics regress.
- `lock-churn-regression-rejected`: active route churn is unsafe.
- `no-quality-improvement`: candidate does not improve meaningful quality.

Calibration must keep one code path, avoid benchmark hardcoding, and preserve safety gates.
