# Roadmap

This document outlines planned improvements for the Crop Rotation Map Generator. Items are organized by priority and complexity.

---

## Phase 1: Core Improvements (Stability & Usability)

### Bed History Timeline
View all crops planted in a specific bed over time to track rotation compliance and identify patterns.

### Cycle Comparison View
Side-by-side diff of two cycles to easily see what changed between planning periods.

### PDF Export
Generate print-ready PDF maps without relying on the browser print dialog. Planned implementation using weasyprint or reportlab.

### Snapshot Viewer
Browse and compare historical JSON snapshots directly from the UI, instead of manually opening files.

---

## Phase 2: Data Quality & Validation

### Input Validation Hardening
Sanitize crop names and prevent special character issues that could cause database or display problems.

### Expanded Test Coverage
Unit tests for the rotation engine, database operations, and edge cases beyond current smoke tests.

### Debug Logging
Add logging system for troubleshooting cycle generation, crop assignment, and override propagation issues.

---

## Phase 3: Enhanced Features

### Agronomic Data in Plant Database
Add days to maturity and yield estimates to the plant database for better planning and forecasting.

### Advanced Crop Filtering
Filter and search crops by plant family, species, category, and other attributes for easier management.

### Bulk Operations
Edit multiple crops or beds at once to speed up configuration and adjustments.

### Configurable Rotation Rules
Make the rotation algorithm configurable via the Settings interface:
- **History size**: Configurable lookback cycles (currently hardcoded at `LOOKBACK_CYCLES = 5`)
- **Penalty adjustments**: Allow modification of same-crop, same-species, and same-family penalties
- **Diversity bonus**: Allow adjustment of the diversity bonus weighting

---

## Phase 4: Advanced Features

### Intercropping Support (Associations)
Allow planning multiple crops on the same sub-plot (e.g., Lettuce + Onion).

**Implementation details:**
- Modify the `cycle_plans` table to allow a "Many-to-Many" relationship with crops
- Adapt the rotation algorithm to check the compatibility of the families of the two associated crops
- Update the map visualization to display multiple crops per sub-bed

### Multi-language Support
Add English UI translation alongside the existing French interface.

---

## Phase 5: Convenience Features (Nice-to-Have)

### Dark Mode
CSS theme switching for better visibility in different lighting conditions.

### CSV Import
Import historical planting data from spreadsheets for easier migration from other systems.

### PyInstaller Standalone
Single Windows executable for easy distribution without requiring Python installation.

---

## Completed Features

Features that have been implemented and released:

- [x] Bootstrap wizard (v1.0.0)
- [x] Cycle generation with 5-category rotation (v1.0.0)
- [x] Map visualization with color coding (v1.0.0)
- [x] Excel export (v1.0.0)
- [x] Plant database with scientific names (v1.1.0)
- [x] Smart rotation algorithm with multi-level penalties (v1.2.0)
- [x] Bed-first auto-distribution (v1.3.0)
- [x] Override recording and propagation (v1.0.0)
- [x] Database auto-backups (v1.0.0)
- [x] Undo generation (v1.0.0)

---

## Contributing

Have ideas for new features? Feel free to [open an issue](https://github.com/hbiaou/crop-rotation/issues) to discuss.
