# 🍆 QROP / Brinjel — Companion Tool for Crop Rotation

## Overview

The **Crop Rotation Map Generator** and **[QROP](https://gitlab.com/mxhfs/qrop)** (or its successor **[Brinjel](https://brinjel.com/)**) are complementary tools with almost no feature overlap. This app automates *rotation rule enforcement*, while QROP/Brinjel handles *season-level operational planning*.

Together they form a complete workflow: **decide what goes where** (this app) → **plan how and when to grow it** (QROP/Brinjel).

---

## Feature Comparison

| Capability | This App | QROP / Brinjel |
|---|:---:|:---:|
| **Automated category rotation** (5-category sequence) | ✅ Core | ❌ Manual |
| **Scoring-based crop assignment** (history lookback) | ✅ Core | ❌ |
| **Distribution adjustment** (% targets per crop) | ✅ Core | ❌ |
| **Rotation rule enforcement** | ✅ Automatic | ⚠️ Visual only |
| **Garden map visualization** | ✅ Category-colored grid | ✅ Timeline-based field map |
| **Override recording** (actual vs. planned) | ✅ Core | ✅ Via notes/harvest |
| **Season planning** (sowing/transplanting dates) | ❌ | ✅ Core |
| **Weekly task calendar** | ❌ | ✅ Core |
| **Seed & transplant ordering lists** | ❌ | ✅ Auto-generated |
| **Harvest tracking & yield analytics** | ❌ | ✅ Core |
| **Notes & photos per planting** | ❌ | ✅ Core |
| **Multi-user collaboration** | ❌ | ✅ (Brinjel) |
| **Charts & analytics** | ❌ | ✅ Core |
| **Print-ready maps** | ✅ A4 landscape | ✅ One-click print |
| **Excel export** | ✅ `.xlsx` | ✅ CSV |

---

## Why They Complement Each Other

### This App Automates What QROP Leaves Manual

QROP/Brinjel shows crop-family history per bed and lets you *visually check* rotation compliance, but it **does not auto-generate** the next rotation. You must manually drag plantings onto beds while mentally tracking the rotation rules.

This app does exactly that: it reads the previous cycle, applies the configured sequence (`Feuille → Graine → Racine → Fruit → Couverture`), runs a distance-weighted scoring algorithm, and produces the full next-cycle plan automatically.

### QROP/Brinjel Covers the Operational Layer This App Doesn't

Once you know "bed P03 will grow Tomate this cycle," you still need to plan:

- **When** to sow, transplant, and harvest
- **What tasks** to do each week (weeding, irrigating, trellising)
- **How many seeds/transplants** to order
- **What the actual yield was** at the end

This app intentionally stops at the *what-goes-where* level. QROP/Brinjel picks up exactly where this app leaves off.

---

## Recommended Workflow

1. **Start of season** → Open this app → generate the next cycle → adjust distribution → confirm crop assignment
2. **Export** → Print the map or download the Excel file
3. **Open QROP/Brinjel** → Create plantings based on the rotation plan → set sowing, transplanting, and harvest dates → assign them to beds
4. **During the season** → Use QROP/Brinjel for weekly tasks, seed orders, and harvest logging
5. **End of season** → Back in this app: record any overrides (actual ≠ planned) → finalize cycle → the next generation will account for what actually happened

---

## Links

- **QROP** (desktop, free, open-source): [gitlab.com/mxhfs/qrop](https://gitlab.com/mxhfs/qrop)
- **Brinjel** (web, freemium, successor to QROP): [brinjel.com](https://brinjel.com/)
- **QROP documentation**: [qrop.frama.io](https://qrop.frama.io/)
