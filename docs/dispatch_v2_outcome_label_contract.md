# Dispatch V2 Outcome Label Contract

- `dispatch-outcome` is outcome-time only.
- Required label fields:
  - `actualPickupTravelTimeSeconds`
  - `actualMerchantWaitTimeSeconds`
  - `actualDropoffTravelTimeSeconds`
  - `totalCompletionTimeSeconds`
  - `realizedTrafficDelaySeconds`
  - `realizedWeatherModifier`
  - `delivered`
  - `labelQuality`
- `labelQuality` enum:
  - `SIMULATED_STRONG`
  - `REAL_STRONG`
  - `REAL_PARTIAL`
  - `MISSING`
- V1 default is simulator-first, so generated dispatch outcomes are written as `SIMULATED_STRONG`.
