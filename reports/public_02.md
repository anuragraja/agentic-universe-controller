# Grade report — public_02_incidents

## Outcomes vs baseline (no-op controller)

| workflow | conclusion rate | Δ | pickup | Δ | engagement | Δ | engagement gap captured | hallucinated calls (base) |
|---|---|---|---|---|---|---|---|---|
| ks_cancel | 0.295 | +19.3% | 0.206 | +12.2% | 0.498 | +4.5% | 30% | 86 (330) |
| nw_kyc | 0.435 | +16.0% | 0.272 | +12.6% | 0.603 | +1.9% | 2% | 49 (31) |
| nw_renewal | 0.476 | +11.6% | 0.292 | +11.5% | 0.546 | -0.4% | 5% | 59 (55) |
| ALL | 0.385 | +15.3% | 0.249 | +12.0% | 0.540 | +1.8% | 14% | 194 (416) |

## Changes applied by the controller

7 applied — beneficial: 5, neutral: 2

- nw_renewal v2 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.085 → **beneficial**
- nw_renewal v3 (controller_auto) dims=['schedule'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- ks_cancel v2 (controller_auto) dims=['schedule'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- ks_cancel v4 (controller_approved) dims=['prompt_version'] engageΔ=+0.102 didΔ=+0.000 → **beneficial**
- nw_kyc v2 (controller_approved) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.283 → **beneficial**
- ks_cancel v5 (controller_approved) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.591 → **beneficial**
- nw_kyc v3 (controller_approved) dims=['voice'] engageΔ=+0.034 didΔ=+0.000 → **beneficial**

## Governance

```
{
  "approval_requests": 6,
  "decisions": {
    "approved": 5,
    "rejected": 1,
    "expired": 0
  },
  "rejection_reasons": {
    "approver declined (judgement call)": 1
  },
  "applied_via_approval": 4,
  "auto_applied": 3,
  "auto_apply_rejected": 7,
  "apply_conflicts": 1,
  "lapsed": 0,
  "peak_requests_per_24h": {
    "ks_cancel": 2,
    "nw_kyc": 1
  }
}
```

## Incidents

```
[
  {
    "type": "did_flagged",
    "workflow": "ks_cancel",
    "at": "D2 10:00",
    "flagged_did_share_by_day": {
      "2": 0.507,
      "3": 0.502,
      "4": 0.496,
      "5": 0.509,
      "6": 0.503,
      "7": 0.159,
      "8": 0.0,
      "9": 0.0
    }
  },
  {
    "type": "supervisor_edit",
    "workflow": "ks_cancel",
    "at": "D3 11:30",
    "mttr_minutes": 150,
    "fixed_by": "controller_approved"
  },
  {
    "type": "supervisor_edit",
    "workflow": "nw_renewal",
    "at": "D5 15:00"
  }
]
```

## Decaying variants — share of in-population calls still on the variant, by day after onset

```
{}
```

Credits used: 14 · validation runs: 4 · LLM fix calls: 2