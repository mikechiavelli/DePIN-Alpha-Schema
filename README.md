# Post Fiat Alpha Registry — JSON Schema Specification

**The data primitive layer between human-authored Alpha Registry reports and the Hive Mind's automated signal routing.**

> Schema Version: `v1.1.0` · Published: March 2026 · Analyst: Post Fiat Alpha Registry

---

## What This Is

The Post Fiat Alpha Registry produces three types of research reports:

| Report Type | What It Covers |
|---|---|
| **Tokenomics Scorecard** | Pre-TGE comparative analysis of 2–5 projects using a 10-point weighted scoring rubric |
| **Sector Deep Dive** | Multi-protocol sector analysis (AI Agents, DePIN, RWA) using the same scoring framework |
| **Airdrop Intelligence** | Farming priority rankings using an 8-factor rubric with inverted scoring factors |

This repository defines a **formal JSON Schema (Draft-07)** for all three report types, a **Python validator script** that checks any submitted report for compliance, and **example reports** demonstrating end-to-end usage.

The schema creates a standardised data layer so that Hive Mind agents can programmatically ingest, route, and act on Alpha Registry research without parsing unstructured text.

---

## Repository Contents

```
pft_alpha_registry_schema.json          ← Unified JSON Schema (v1.1.0)
validator.py                            ← Python validation script
example_report_render.json              ← Render Network sector deep dive (compliant)
example_report_storj.json               ← Storj sector deep dive (compliant)
depin_sector_deep_dive.json             ← Full DePIN sector report — 12 protocols
pft_validator_package.zip               ← All files bundled for easy download
README.md                               ← This file
```

---

## Quick Start

### 1. Install the one dependency

```bash
pip install jsonschema
```

### 2. Validate an example report

```bash
python validator.py example_report_storj.json
```

Expected output:

```
=================================================================
  Post Fiat Alpha Registry — Schema Validator v1.0.0
=================================================================
  File       : example_report_storj.json
  Report Type: sector_deep_dive
  Validated  : 2026-03-25T00:59:04+00:00
  Result     : ✅ PASS
─────────────────────────────────────────────────────────────────
  Schema Errors         : 0
  Business Rule Errors  : 0
  Warnings              : 0
=================================================================
```

### 3. Validate your own report

```bash
python validator.py your_report.json
```

### 4. Get JSON output for programmatic consumption

```bash
python validator.py your_report.json --json-output
```

---

## ⚠️ Common Mistake

The validator takes a **report file** as input — never the schema file itself.

```bash
# ❌ WRONG — this passes the schema into itself
python validator.py pft_alpha_registry_schema.json

# ✅ CORRECT — this validates a report against the schema
python validator.py example_report_storj.json
```

The schema file (`pft_alpha_registry_schema.json`) must sit in the same folder as `validator.py`. It is loaded automatically in the background — you never pass it directly on the command line unless you want to specify a custom path via `--schema`.

---

## Report Structure

### Universal Metadata Block

Every report — regardless of type — must include a `metadata` object:

| Field | Type | Format / Notes |
|---|---|---|
| `report_id` | `string` | `PFT-{TYPE}-{YYYYMMDD}-{4-char hex}` — e.g. `PFT-SECTOR-20260324-5703` |
| `report_type` | `enum` | `tokenomics_scorecard` · `sector_deep_dive` · `airdrop_intelligence` |
| `analyst_id` | `string` | Network analyst identifier or pseudonym |
| `timestamp` | `string` | ISO 8601 UTC datetime |
| `data_as_of` | `string` | Date data was sourced `YYYY-MM-DD` |
| `methodology_version` | `string` | Schema version — e.g. `v1.1.0` |
| `source_urls` | `array[uri]` | Minimum 1 URL — all primary data sources |
| `disclaimer` | `string` | Required legal/risk disclaimer |
| `tags` | `array[string]` | Optional — taxonomy tags for agent routing |

Every report must also contain a top-level `report_type_guard` field:

```json
"report_type_guard": "sector_deep_dive"
```

This is the **routing discriminator** — the validator uses it to determine which sub-schema to apply. Valid values: `tokenomics_scorecard`, `sector_deep_dive`, `airdrop_intelligence`.

---

### Tokenomics Scorecard / Sector Deep Dive

Each protocol entry is scored across 5 weighted sections:

| Section | Weight | Key Dimensions |
|---|---|---|
| Market & Valuation | 21% | FDV vs peers · Circulating % · MC/TVL · VC markup |
| Tokenomics Design | 34% | Vesting · Emissions · Community % · Treasury · Token utility · Anti-dump |
| Technology & Product | 20% | Tech moat · Product readiness · Audit quality · Dev ecosystem |
| Team & Governance | 14% | Team track record · Investor quality · Decentralisation · Regulatory posture |
| Narrative & Catalyst | 11% | Narrative strength · Catalyst pipeline · Community · Exchange listings |

**Scoring scale:** 1 = Poor · 4 = Below Average · 6 = Average · 8 = Strong · 10 = Best-in-Class

**Composite score:** Sum of `score × weight` across all dimensions. Maximum = 10.0.

**Tier thresholds:**

| Tier | Score Range |
|---|---|
| TIER_1 | ≥ 9.0 |
| TIER_2 | 7.0 – 8.9 |
| TIER_3 | 5.0 – 6.9 |
| TIER_4 | < 5.0 |

**Example dimension entry:**

```json
{
  "dimension_id": "TD-02",
  "label": "Emission / inflation rate (Yr 1)",
  "weight": 0.06,
  "score": 9,
  "weighted_score": 0.54,
  "rationale": "~3% net inflation — effectively deflationary at scale via BME mechanics.",
  "raw_data": "Yr1 inflation: ~3% | Type: Burn-and-Mint Equilibrium",
  "scoring_methodology": "<2%=10, 2-5%=9, 5-8%=8, 8-12%=6, 12-20%=4, >20%=2"
}
```

> **Business rule enforced by validator:** All dimension weights across all 5 sections must sum to `1.0 ± 0.02`. The `weighted_score` must equal `score × weight` for every dimension.

---

### Airdrop Intelligence Report

Eight factors scored 1–5. Four factors are **inverted** — a lower raw score means better for the farmer.

| Factor | Weight | Direction |
|---|---|---|
| Token Value Potential | 35% | Higher = better |
| Confirmation Signal | 20% | Higher = better |
| Retroactive vs Prospective | 10% | Higher = better (5 = fully farmable now) |
| Wallet Saturation | 10% | **Inverted** — lower = better (less competition) |
| Sybil Detection Risk | 10% | **Inverted** — lower = better (fewer checks) |
| Cost to Farm | 7% | **Inverted** — lower = better (nearly free) |
| Time Commitment | 5% | **Inverted** — lower = better (minimal time) |
| Unlock Schedule Risk | 3% | Higher = better (favourable vesting) |

**Composite formula:**

```
Score = (Value × 0.35) + (Confirm × 0.20) + (Prosp × 0.10)
      + ((6 - Saturation) × 0.10) + ((6 - Sybil) × 0.10)
      + ((6 - Cost) × 0.07) + ((6 - Time) × 0.05)
      + (Unlock × 0.03)
```

---

## Validator Output

The validator returns three categories of feedback:

| Category | Blocks PASS? | Examples |
|---|---|---|
| `schema_errors` | ✅ Yes | Missing required field · Wrong data type · Enum violation · report_id pattern mismatch |
| `business_rule_violations` | ✅ Yes | Weights don't sum to 1.0 · weighted_score arithmetic mismatch |
| `warnings` | ❌ No (non-blocking) | Composite score rounding delta · Future timestamp |

**Example error output:**

```
SCHEMA ERRORS:
[1] Path: metadata → report_id
    'PFT-SECTOR-20260324-5t0r' does not match '^PFT-(TOKENOMICS|SECTOR|AIRDROP)-[0-9]{8}-[a-f0-9]{4}$'

[2] Path: protocols → 0 → composite_score
    15.5 is greater than the maximum of 10

[3] Path: protocols → 0 → signal
    'BUY_NOW' is not one of ['ACCUMULATE', 'SPECULATIVE', 'MONITOR_ONLY', 'AVOID', 'SELL']
```

---

## DePIN-Specific Fields (added v1.1.0)

When writing DePIN sector reports, eight additional optional fields are available on each protocol entry. All are optional — existing v1.0.0 reports remain fully compliant.

| Field | Type | Why It Matters |
|---|---|---|
| `depin_subcategory` | enum | Structured subcategory routing — `Compute_GPU`, `Storage`, `GPS_Location`, `Vehicle_Data` etc. Replaces unparseable free-text `category` for agent filtering |
| `depin_device_count` | integer | Physical hardware units actively deployed — primary deployment maturity signal |
| `proof_of_work_mechanism` | enum | How physical work is verified — `PoRep_PoSt`, `Proof_of_Coverage`, `AI_Image_Verification`, `GPS_Attestation` etc. |
| `demand_revenue_monthly_usd` | number | Revenue from paying customers (not token emissions) — key signal distinguishing infrastructure-with-revenue from pure subsidy models |
| `physical_coverage_metric` | string | Human-readable deployment claim — e.g. `"20K+ RTK stations in 150+ countries"` |
| `centralised_cloud_cost_discount_pct` | number | % cheaper than AWS/GCP — validates cost-arbitrage thesis |
| `anti_gaming_mechanism` | enum | How spoofing is prevented — `Cryptographic_Proof`, `AI_Quality_Scoring`, `GPS_Cross_Validation` etc. |
| `hardware_operator_cost_usd` | number | Capital cost per hardware unit — enables payback period modelling |

---

## How to Submit a New Report

1. Choose your report type and copy the structure from an example file
2. Fill in `metadata` — generate a unique `report_id` in the format `PFT-{TYPE}-{YYYYMMDD}-{4hex}`
   - The last 4 characters must be **lowercase hex only**: `0–9` and `a–f`
   - Valid: `PFT-SECTOR-20260324-a1b2` · Invalid: `PFT-SECTOR-20260324-5t0r`
3. Set `report_type_guard` to match `metadata.report_type`
4. Ensure all dimension weights across all 5 sections sum to `1.0 ± 0.02`
5. Verify `weighted_score = score × weight` for every dimension
6. Run `python validator.py your_report.json` and resolve all FAIL statuses before submitting
7. Submit to the Alpha Registry via PR

---

## Hive Mind Integration Notes

Key fields used for automated signal routing:

| Field | Purpose |
|---|---|
| `metadata.report_type` | First-level router — determines which agents receive this report |
| `metadata.tags` | Taxonomy routing — e.g. `["DePIN", "compute", "GPU"]` for infrastructure-specific agents |
| `protocols[*].signal` | Action dispatcher — `ACCUMULATE`, `SPECULATIVE`, `MONITOR_ONLY`, `AVOID`, `SELL` |
| `protocols[*].tier` | Quality filter for position sizing logic |
| `protocols[*].depin_subcategory` | DePIN subcategory routing for infrastructure-specific agents |
| `sector_summary.systemic_risks[*].severity` | Risk-gating — `CRITICAL` blocks certain automated actions |
| `top_picks[*].medal` | Priority ordering for capital allocation agents — `GOLD`, `SILVER`, `BRONZE`, `NOTABLE` |
| `catalysts[*].confirmed` | Boolean — confirmed catalysts trigger different agent responses than soft catalysts |

---

## Schema Version History

| Version | Date | Changes |
|---|---|---|
| `v1.1.0` | March 2026 | Added 8 DePIN-specific optional fields · Lowered `sector_deep_dive.protocols` minItems to 1 · Added changelog block to schema root |
| `v1.0.0` | March 2026 | Initial release — 5-section scorecard · 8-factor airdrop rubric v2 · unified metadata block |

---

## Reports Published

| Report | Protocols Covered | Schema | Status |
|---|---|---|---|
| AI Agent Sector Deep Dive | TAO, RENDER, FET, NMR, VIRTUAL, OLAS, ELIZAOS, AGIX, KITE, VVV | v1.0.0 | ✅ Live |
| DePIN Sector Deep Dive | AKT, GEOD, FIL, PEAQ, STORJ, GRASS, ATH, HNT, WXM, DIMO, HONEY, IO | v1.1.0 | ✅ Live |
| Airdrop Intelligence v3 | Polymarket, Base, MetaMask, Myriad, LayerZero, Abstract, YEET | v1.0.0 | ✅ Live |

---

## Disclaimer

Intelligence aggregation only. NOT financial or investment advice. ~88% of airdropped tokens lose value within 3 months (CoinGecko 2025). Never invest more than you can afford to lose. Always conduct your own research (DYOR).

---

*Post Fiat Alpha Registry — Building the data primitive layer for autonomous signal routing.*
