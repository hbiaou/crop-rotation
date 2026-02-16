# 🌿 Crop Rotation Map Generator

A web application for planning and managing crop rotation in market gardens. Built for small-scale farmers and garden managers who need to track multi-year rotation cycles, visualize planting plans on interactive maps, and export data for field use.

> **Note**: This application was built for my personal use as a farmer in Benin, but it is available for anyone to use and adapt for their own needs. I am planning to add more features in the future depending on my needs.

## Features

- **🚀 Bootstrap** — Initial setup wizard to assign categories and crops to every sub-bed in a garden
- **⚡ Cycle Generation** — Automatic rotation based on a configurable 5-category sequence (Feuille → Graine → Racine → Fruit → Couverture)
- **🌿 Crop Families** — Group crops by botanical family (e.g., Solanacées, Fabacées) for better rotation planning
- **🎲 Smart Randomization** — Randomized starting point for new gardens to ensure diverse initial layouts
- **📊 Distribution Adjustment** — Fine-tune crop percentages per category with live preview of bed counts
- **🗺️ Map Visualization** — Color-coded garden map showing planned and actual crops, with override indicators
- **📍 Scroll Preservation** — Map view remembers your scroll position after editing sub-beds
- **📝 Override Recording** — Record field changes when actual planting differs from the plan
- **🖨️ Print-Ready Map** — A4 landscape-optimized view for use in the field
- **📥 Excel Export** — Download rotation data as styled `.xlsx` workbooks (per-garden or all gardens)
- **🔙 History Import** — Import historical cycle data from JSON to restore past states
- **🧨 Danger Zone** — Delete specific cycles or reset garden history entirely
- **⏪ Undo Generation** — Safely roll back the most recent cycle if needed
- **✅ Finalize Cycle** — Save a JSON snapshot of actual planting data to `history/`
- **⚙️ Settings** — Manage gardens, crops, rotation sequence, cycles per year, and database backups
- **💾 Auto-Backups** — Database is backed up automatically before cycle generation and exports

## Quick Start

### Prerequisites

- Python 3.10+
- pip

### Installation

```bash
git clone https://github.com/YOUR_USERNAME/crop-rotation.git
cd crop-rotation
pip install -r requirements.txt
```

### Running the App

```bash
python app.py
```

Open [http://localhost:5000](http://localhost:5000) in your browser.

### First Use

1. The app comes pre-configured with two gardens (G1: Grand Jardin, G2: Petit Jardin) and 22 crops across 5 categories
2. Click **"Démarrage à zéro"** to bootstrap your first garden with initial planting data
3. Use **"Auto-distribuer"** on the bootstrap page to fill in crops automatically, or assign them manually
4. Once bootstrapped, view your garden map, generate the next cycle, and adjust distributions
5. Records of historical cycles (e.g. from previous years) can be entered by manually setting the cycle ID during bootstrap (see below).

### Historical Data & Imbalance Correction

If you have data from a previous year (e.g., 2025B) and want to start your rotation from there:
1.  **Bootstrap**: In the bootstrap page, change the default cycle (e.g., `2026A`) to your specific past cycle (e.g., `2025B`).
2.  **Enter Data**: Fill in what was planted during that cycle.
3.  **Generate**: When you generate the next cycle, the system will correctly rotate from `2025B` to `2026A`.
4.  **Correct Imbalances**: If your history had category imbalances, the system will adapt.
5.  **JSON Import**: You can also upload a JSON file containing the full history of a cycle via **Settings > Import**. This is useful for bulk-importing past data without manual entry.
6.  **Reset History**: If you made a mistake with the cycle ID (e.g., started with `2026A` instead of `2025B`), go to **Settings > Danger Zone** to clear the history and start over.

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend | Flask 3.x (Python) |
| Database | SQLite (WAL mode) |
| Templates | Jinja2 |
| Styling | Vanilla CSS (custom design system) |
| Export | pandas + openpyxl |
| Fonts | Inter (Google Fonts) |

## Project Structure

```
crop-rotation/
├── app.py                  # Flask entry point
├── database.py             # SQLite schema, seed data, CRUD operations
├── rotation_engine.py      # Core rotation algorithm & crop assignment
├── requirements.txt
├── config/
│   └── defaults.json       # Default gardens, crops, rotation sequence
├── i18n/
│   └── fr.json             # French UI strings
├── routes/
│   ├── main.py             # Homepage, map view, print, override
│   ├── cycle.py            # Bootstrap, generate, undo, finalize
│   ├── distribution.py     # Distribution adjustment
│   ├── settings.py         # Settings CRUD
│   └── export.py           # Excel export
├── utils/
│   ├── backup.py           # Database backup & restore
│   ├── export.py           # Excel generation
│   └── snapshots.py        # JSON snapshot for finalized cycles
├── templates/              # Jinja2 HTML templates
├── static/
│   ├── css/
│   │   ├── style.css       # Main design system
│   │   └── print.css       # Print-optimized styles
│   └── js/
│       └── app.js          # Client-side interactions
├── data/                   # SQLite database (auto-created)
├── backups/                # Database backups (auto-created)
└── history/                # Finalized cycle snapshots (auto-created)
```

## Data Backup

The app automatically backs up the database:
- **Before cycle generation** — tagged `pre_generate`
- **Before Excel export** — tagged `export`
- **Manual** — from the Settings page, tagged `manual`

Backups are stored in `backups/` as timestamped `.db` files. You can restore any backup from the Settings page.

## Category Colors

| Category | French | Color |
|----------|--------|-------|
| Leaf | Feuille | 🟢 Green |
| Seed | Graine | 🟡 Amber |
| Root | Racine | 🟤 Teal |
| Fruit | Fruit | 🔴 Red |
| Cover | Couverture | 🟣 Purple |

## 🍆 Companion Tool: QROP / Brinjel

This app handles **automated crop rotation** — deciding which category and crop goes to which bed, cycle after cycle. It does not cover season scheduling, task management, or harvest tracking.

For those needs, we recommend **[QROP](https://gitlab.com/mxhfs/qrop)** (free, open-source desktop app) or its successor **[Brinjel](https://brinjel.com/)** (web-based). Use the rotation plan generated by this app as input for your QROP/Brinjel season plan.

| This app handles | QROP / Brinjel handles |
|---|---|
| Category rotation (automated) | Sowing & transplanting dates |
| Crop assignment (scored) | Weekly task calendar |
| Distribution adjustment | Seed & transplant ordering |
| Override recording | Harvest tracking & yield analytics |
| Map visualization & print | Notes, photos, collaboration |

👉 **[Detailed comparison →](docs/QROP_COMPANION.md)**

## Language

All user-facing text is in **French**. UI strings are centralized in `i18n/fr.json`.

## License

This project is provided as-is for personal and educational use.
