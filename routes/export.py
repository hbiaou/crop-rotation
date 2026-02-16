"""
routes/export.py — Excel export and print routes.

Provides:
- GET /export/excel/<garden_id>/<cycle>   — Download Excel for one garden
- GET /export/excel-all/<cycle>           — Download Excel for all gardens

Auto-backup is triggered before every export.
See FEATURES_SPEC.md section F9 and section 6 (Backup Strategy).
"""

from flask import Blueprint, flash, redirect, url_for, send_file

from utils.backup import backup_db
from utils.export import generate_excel, generate_excel_all
from database import get_gardens, get_cycles
from flask import render_template

export_bp = Blueprint('export', __name__, url_prefix='/export')


@export_bp.route('/')
def index():
    """Export page with options."""
    gardens = get_gardens()
    
    # Get all distinct cycles across all gardens
    cycles = get_cycles()
    
    return render_template('export.html', gardens=gardens, cycles=cycles)


@export_bp.route('/excel/<int:garden_id>/<cycle>')
def export_excel(garden_id, cycle):
    """Export a single garden's cycle data as Excel."""
    # Auto-backup before export
    backup_db('export')

    buffer, filename = generate_excel(garden_id, cycle)
    if not buffer:
        flash("Aucune donnée à exporter pour ce cycle.", "warning")
        return redirect(url_for('main.index', garden_id=garden_id))

    return send_file(
        buffer,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


@export_bp.route('/excel-all/<cycle>')
def export_excel_all(cycle):
    """Export all gardens for a cycle as a multi-sheet Excel workbook."""
    # Auto-backup before export
    backup_db('export')

    buffer, filename = generate_excel_all(cycle)
    if not buffer:
        flash("Aucune donnée à exporter pour ce cycle.", "warning")
        return redirect(url_for('main.index'))

    return send_file(
        buffer,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
