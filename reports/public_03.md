# Grade report — public_03_load

## Outcomes vs baseline (no-op controller)

| workflow | conclusion rate | Δ | pickup | Δ | engagement | Δ | engagement gap captured | hallucinated calls (base) |
|---|---|---|---|---|---|---|---|---|
| arav_cancel_2 | 0.383 | +12.2% | 0.262 | +7.3% | 0.518 | +3.4% | 27% | 417 (408) |
| arav_kyc_1 | 0.491 | +38.7% | 0.283 | +31.9% | 0.594 | -0.2% | 0% | 482 (370) |
| arav_renewal_0 | 0.471 | +17.2% | 0.283 | +7.2% | 0.590 | +8.7% | 44% | 467 (440) |
| kest_cancel_2 | 0.385 | +13.6% | 0.260 | +7.0% | 0.525 | +5.2% | 36% | 408 (411) |
| kest_kyc_1 | 0.489 | +38.4% | 0.281 | +31.4% | 0.595 | +0.2% | 0% | 435 (339) |
| kest_renewal_0 | 0.472 | +18.2% | 0.284 | +7.9% | 0.589 | +8.6% | 43% | 437 (433) |
| nort_cancel_2 | 0.385 | +13.6% | 0.259 | +6.9% | 0.525 | +5.2% | 34% | 418 (393) |
| nort_kyc_1 | 0.492 | +39.0% | 0.283 | +32.6% | 0.596 | +0.1% | 0% | 457 (323) |
| nort_renewal_0 | 0.471 | +16.3% | 0.282 | +7.1% | 0.590 | +7.8% | 43% | 454 (411) |
| tide_cancel_2 | 0.389 | +14.7% | 0.261 | +7.1% | 0.526 | +5.4% | 35% | 421 (407) |
| tide_kyc_1 | 0.483 | +36.6% | 0.280 | +30.5% | 0.592 | -0.1% | 0% | 443 (356) |
| tide_renewal_0 | 0.464 | +15.8% | 0.282 | +6.7% | 0.584 | +7.6% | 36% | 435 (438) |
| ALL | 0.448 | +22.7% | 0.275 | +14.4% | 0.570 | +4.8% | 24% | 5274 (4729) |

## Changes applied by the controller

53 applied — harmful: 4, beneficial: 29, neutral: 20

- nort_renewal_0 v2 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=-0.052 → **harmful**
- kest_renewal_0 v2 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=-0.052 → **harmful**
- arav_renewal_0 v2 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=-0.052 → **harmful**
- tide_renewal_0 v2 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=-0.052 → **harmful**
- nort_renewal_0 v3 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.114 → **beneficial**
- kest_renewal_0 v3 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.114 → **beneficial**
- arav_renewal_0 v3 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.114 → **beneficial**
- tide_renewal_0 v3 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.114 → **beneficial**
- nort_cancel_2 v2 (controller_approved) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.044 → **beneficial**
- kest_cancel_2 v2 (controller_approved) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.044 → **beneficial**
- arav_cancel_2 v2 (controller_approved) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.044 → **beneficial**
- tide_cancel_2 v2 (controller_approved) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.044 → **beneficial**
- nort_renewal_0 v4 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=+0.068 didΔ=+0.000 → **beneficial**
- arav_renewal_0 v4 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=+0.068 didΔ=+0.000 → **beneficial**
- tide_renewal_0 v4 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=+0.067 didΔ=+0.000 → **beneficial**
- kest_renewal_0 v4 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=+0.068 didΔ=+0.000 → **beneficial**
- nort_kyc_1 v2 (controller_approved) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.419 → **beneficial**
- arav_kyc_1 v2 (controller_approved) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.419 → **beneficial**
- tide_kyc_1 v2 (controller_approved) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.419 → **beneficial**
- kest_kyc_1 v2 (controller_approved) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.437 → **beneficial**
- nort_cancel_2 v3 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=-0.002 didΔ=+0.000 → **neutral**
- arav_cancel_2 v3 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=-0.002 didΔ=+0.000 → **neutral**
- tide_cancel_2 v3 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=-0.002 didΔ=+0.000 → **neutral**
- kest_renewal_0 v5 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=+0.061 didΔ=+0.000 → **beneficial**
- kest_cancel_2 v3 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=-0.002 didΔ=+0.000 → **neutral**
- arav_renewal_0 v5 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=+0.058 didΔ=+0.000 → **beneficial**
- arav_kyc_1 v3 (controller_approved) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.131 → **beneficial**
- nort_renewal_0 v5 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=+0.058 didΔ=+0.000 → **beneficial**
- nort_kyc_1 v3 (controller_approved) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.135 → **beneficial**
- nort_renewal_0 v6 (controller_auto) dims=['schedule'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- nort_cancel_2 v4 (controller_auto) dims=['schedule'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- kest_renewal_0 v6 (controller_auto) dims=['schedule'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- kest_cancel_2 v4 (controller_auto) dims=['schedule'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- arav_renewal_0 v6 (controller_auto) dims=['schedule'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- arav_cancel_2 v4 (controller_auto) dims=['schedule'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- tide_renewal_0 v5 (controller_auto) dims=['schedule'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- tide_cancel_2 v4 (controller_auto) dims=['schedule'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- kest_kyc_1 v3 (controller_approved) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.103 → **beneficial**
- tide_kyc_1 v3 (controller_approved) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.103 → **beneficial**
- kest_cancel_2 v5 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=+0.103 didΔ=+0.000 → **beneficial**
- nort_cancel_2 v5 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=+0.103 didΔ=+0.000 → **beneficial**
- tide_cancel_2 v5 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=+0.103 didΔ=+0.000 → **beneficial**
- arav_cancel_2 v5 (controller_approved) dims=['voice'] engageΔ=+0.051 didΔ=+0.000 → **beneficial**
- tide_renewal_0 v6 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=+0.058 didΔ=+0.000 → **beneficial**
- arav_cancel_2 v6 (controller_approved) dims=['welcome_message'] engageΔ=+0.050 didΔ=+0.000 → **beneficial**
- nort_renewal_0 v7 (controller_auto) dims=['schedule'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- nort_cancel_2 v6 (controller_auto) dims=['schedule'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- kest_renewal_0 v7 (controller_auto) dims=['schedule'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- kest_cancel_2 v6 (controller_auto) dims=['schedule'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- arav_renewal_0 v7 (controller_auto) dims=['schedule'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- arav_cancel_2 v7 (controller_auto) dims=['schedule'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- tide_renewal_0 v7 (controller_auto) dims=['schedule'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- tide_cancel_2 v6 (controller_auto) dims=['schedule'] engageΔ=+0.000 didΔ=+0.000 → **neutral**

## Governance

```
{
  "approval_requests": 46,
  "decisions": {
    "approved": 44,
    "rejected": 2,
    "expired": 0
  },
  "rejection_reasons": {
    "approver declined (judgement call)": 2
  },
  "applied_via_approval": 29,
  "auto_applied": 24,
  "auto_apply_rejected": 0,
  "apply_conflicts": 15,
  "lapsed": 0,
  "peak_requests_per_24h": {
    "nort_kyc_1": 2,
    "nort_cancel_2": 3,
    "kest_kyc_1": 2,
    "kest_cancel_2": 3,
    "arav_kyc_1": 2,
    "arav_cancel_2": 3,
    "tide_kyc_1": 2,
    "tide_cancel_2": 3,
    "nort_renewal_0": 1,
    "kest_renewal_0": 1,
    "arav_renewal_0": 1,
    "tide_renewal_0": 1
  }
}
```

## Incidents

```
[]
```

## Decaying variants — share of in-population calls still on the variant, by day after onset

```
{
  "nort_renewal_0:welcome_message=W3": {
    "3": 0.846,
    "4": 0.849
  },
  "kest_renewal_0:welcome_message=W3": {
    "3": 0.851,
    "4": 0.85
  },
  "arav_renewal_0:welcome_message=W3": {
    "3": 0.85,
    "4": 0.849
  },
  "tide_renewal_0:welcome_message=W3": {
    "3": 0.85,
    "4": 0.85
  }
}
```

Credits used: 0 · validation runs: 0 · LLM fix calls: 0