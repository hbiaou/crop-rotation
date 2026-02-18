"""
routes/settings.py — Settings and administration routes.

Provides:
- GET /settings — Settings page (tabbed: Jardins, Cultures, Séquence, Cycles, Sauvegardes)
- POST /settings/garden/add — Add a new garden
- POST /settings/garden/edit — Edit existing garden
- POST /settings/garden/delete — Delete a garden
- POST /settings/sub-bed/toggle — Toggle sub-bed reserve status
- POST /settings/crop/add — Add a new crop
- POST /settings/crop/delete — Delete a crop
- POST /settings/crop/category — Change crop category
- POST /settings/rotation/save — Save rotation sequence order
- POST /settings/cycles/save — Save cycles per year
- POST /settings/backup/create — Create a manual backup
- POST /settings/backup/restore — Restore from backup

See FEATURES_SPEC.md sections F10, F11.
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify

from database import (
    get_gardens, get_garden, get_sub_beds, get_crops, get_setting,
    get_rotation_sequence, get_garden_stats, get_categories, get_cycles,
    create_garden, update_garden, delete_garden, toggle_sub_bed_reserve,
    create_crop, delete_crop, update_crop_category,
    save_rotation_sequence, update_setting, reset_garden_history,
    import_garden_cycle_data
)
from plant_database import (
    get_all_plants, check_plant_db_health, get_plant_count
)
from utils.backup import backup_db, list_backups, restore_db, delete_backup
import json

settings_bp = Blueprint('settings', __name__, url_prefix='/settings')


@settings_bp.route('/')
def index():
    """Main settings page with all tabs."""
    gardens = get_gardens()
    crops = get_crops()
    categories = get_categories()
    rotation = get_rotation_sequence()
    cycles_per_year = get_setting('cycles_per_year', '2')
    distribution_defaults_json = get_setting('distribution_defaults', '{}')
    try:
        distribution_defaults = json.loads(distribution_defaults_json)
    except Exception:
        distribution_defaults = {}
    backups = list_backups()

    # Build garden stats with sub-beds for the reserve grid
    garden_data = []
    for g in gardens:
        stats = get_garden_stats(g['id'])
        sub_beds = get_sub_beds(g['id'])
        cycles = get_cycles(g['id'])
        garden_data.append({
            'garden': g,
            'stats': stats,
            'sub_beds': sub_beds,
            'cycles': cycles,
        })

    # Group crops by category
    crops_by_category = {}
    for cat in categories:
        crops_by_category[cat] = [c for c in crops if c['category'] == cat]

    # Get plant database info
    try:
        plant_db_healthy, plant_db_message = check_plant_db_health()
        plants = get_all_plants() if plant_db_healthy else []
        plant_count = get_plant_count() if plant_db_healthy else 0
    except Exception:
        plant_db_healthy = False
        plant_db_message = "Erreur de connexion"
        plants = []
        plant_count = 0

    # Build set of plant_ids already linked to crops (for disabling "Add to crops" button)
    crops_plant_ids = {c['plant_id'] for c in crops if c['plant_id'] is not None}

    return render_template('settings.html',
        gardens=gardens,
        garden_data=garden_data,
        crops=crops,
        crops_by_category=crops_by_category,
        categories=categories,
        rotation=rotation,
        cycles_per_year=cycles_per_year,
        distribution_defaults=distribution_defaults,
        backups=backups,
        plants=plants,
        plant_count=plant_count,
        plant_db_healthy=plant_db_healthy,
        plant_db_message=plant_db_message,
        crops_plant_ids=crops_plant_ids,
    )


# ========================================
# Garden Routes
# ========================================

@settings_bp.route('/garden/add', methods=['POST'])
def garden_add():
    """Add a new garden."""
    garden_code = request.form.get('garden_code', '').strip().upper()
    name = request.form.get('name', '').strip()
    beds = request.form.get('beds', type=int)
    bed_length_m = request.form.get('bed_length_m', type=float)
    bed_width_m = request.form.get('bed_width_m', 1.0, type=float)
    sub_beds_per_bed = request.form.get('sub_beds_per_bed', type=int)

    if not all([garden_code, name, beds, bed_length_m, sub_beds_per_bed]):
        flash("Veuillez remplir tous les champs obligatoires.", 'error')
        return redirect(url_for('settings.index', tab='jardins'))

    if beds <= 0 or sub_beds_per_bed <= 0:
        flash("Le nombre de planches et sous-planches doit être positif.", 'error')
        return redirect(url_for('settings.index', tab='jardins'))

    result = create_garden(garden_code, name, beds, bed_length_m, bed_width_m, sub_beds_per_bed)
    if result:
        flash(f"Jardin « {name} » ({garden_code}) créé avec succès.", 'success')
    else:
        flash(f"Erreur : le code jardin « {garden_code} » existe déjà.", 'error')

    return redirect(url_for('settings.index', tab='jardins'))


@settings_bp.route('/garden/edit', methods=['POST'])
def garden_edit():
    """Edit an existing garden."""
    garden_id = request.form.get('garden_id', type=int)
    name = request.form.get('name', '').strip()
    beds = request.form.get('beds', type=int)
    bed_length_m = request.form.get('bed_length_m', type=float)
    bed_width_m = request.form.get('bed_width_m', 1.0, type=float)
    sub_beds_per_bed = request.form.get('sub_beds_per_bed', type=int)

    if not all([garden_id, name, beds, bed_length_m, sub_beds_per_bed]):
        flash("Veuillez remplir tous les champs obligatoires.", 'error')
        return redirect(url_for('settings.index', tab='jardins'))

    result = update_garden(garden_id, name, beds, bed_length_m, bed_width_m, sub_beds_per_bed)
    if result:
        flash(f"Jardin « {name} » mis à jour avec succès.", 'success')
    else:
        flash("Erreur lors de la mise à jour du jardin.", 'error')

    return redirect(url_for('settings.index', tab='jardins'))


@settings_bp.route('/garden/delete', methods=['POST'])
def garden_delete():
    """Delete a garden."""
    garden_id = request.form.get('garden_id', type=int)
    if not garden_id:
        flash("Jardin non spécifié.", 'error')
        return redirect(url_for('settings.index', tab='jardins'))

    success, error = delete_garden(garden_id)
    if success:
        flash("Jardin supprimé avec succès.", 'success')
    else:
        flash(error or "Erreur lors de la suppression du jardin.", 'error')

    return redirect(url_for('settings.index', tab='jardins'))


@settings_bp.route('/garden/reset', methods=['POST'])
def garden_reset():
    """Reset a garden's history (delete all cycles)."""
    garden_id = request.form.get('garden_id', type=int)
    if not garden_id:
        flash("Jardin non spécifié.", 'error')
        return redirect(url_for('settings.index', tab='danger'))

    garden = get_garden(garden_id)
    if not garden:
        flash("Jardin introuvable.", 'error')
        return redirect(url_for('settings.index', tab='danger'))

    if reset_garden_history(garden_id):
        flash(f"Historique du jardin « {garden['name']} » réinitialisé avec succès.", 'success')
    else:
        flash("Erreur lors de la réinitialisation de l'historique.", 'error')

    return redirect(url_for('settings.index', tab='danger'))


@settings_bp.route('/cycle/delete', methods=['POST'])
def cycle_delete():
    """Delete a specific cycle for a garden."""
    garden_id = request.form.get('garden_id', type=int)
    cycle = request.form.get('cycle', '').strip()

    if not garden_id or not cycle:
        flash("Jardin ou cycle non spécifié.", 'error')
        return redirect(url_for('settings.index', tab='danger'))
    
    from database import delete_cycle_plans, delete_distribution_profiles

    # Check if garden exists
    garden = get_garden(garden_id)
    if not garden:
        flash("Jardin introuvable.", 'error')
        return redirect(url_for('settings.index', tab='danger'))

    # Delete cycle data
    # We delete plans and distribution profiles
    plans_ok = delete_cycle_plans(garden_id, cycle)
    dist_ok = delete_distribution_profiles(garden_id, cycle)

    if plans_ok and dist_ok:
        flash(f"Cycle {cycle} pour le jardin « {garden['name']} » supprimé avec succès.", 'success')
    else:
        # If partial failure, warn user
        flash("Erreur partielle lors de la suppression du cycle.", 'warning')

    return redirect(url_for('settings.index', tab='danger'))


@settings_bp.route('/import_cycle', methods=['POST'])
def import_cycle():
    """Import cycle data from JSON file."""
    if 'file' not in request.files:
        flash("Aucun fichier sélectionné.", 'error')
        return redirect(url_for('settings.index', tab='import'))
    
    file = request.files['file']
    if file.filename == '':
        flash("Aucun fichier sélectionné.", 'error')
        return redirect(url_for('settings.index', tab='import'))
    
    if file:
        try:
            data = json.load(file)
            success, message = import_garden_cycle_data(data)
            if success:
                flash(message, 'success')
            else:
                flash(f"Erreur lors de l'import : {message}", 'error')
        except json.JSONDecodeError:
            flash("Fichier JSON invalide.", 'error')
        except Exception as e:
            flash(f"Erreur inattendue : {str(e)}", 'error')
            
    return redirect(url_for('settings.index', tab='import'))


@settings_bp.route('/sub-bed/toggle', methods=['POST'])
def sub_bed_toggle():
    """Toggle a sub-bed's reserve status. Returns JSON for AJAX calls."""
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    try:
        sub_bed_id = request.form.get('sub_bed_id', type=int)
        is_reserve = request.form.get('is_reserve', '0')
        is_reserve_bool = is_reserve in ('1', 'true', 'on')

        if not sub_bed_id:
            if is_ajax:
                return jsonify({'success': False, 'error': 'ID manquant'}), 400
            flash("Sous-planche non spécifiée.", 'error')
            return redirect(url_for('settings.index', tab='jardins'))

        result = toggle_sub_bed_reserve(sub_bed_id, is_reserve_bool)

        if is_ajax:
            if result:
                # Return updated counts
                from database import get_db
                conn = get_db()
                sb = conn.execute("SELECT garden_id FROM sub_beds WHERE id = ?", (sub_bed_id,)).fetchone()
                if sb:
                    stats = get_garden_stats(sb['garden_id'])
                    conn.close()
                    return jsonify({
                        'success': True,
                        'active': stats['active_sub_beds'],
                        'reserve': stats['reserve_sub_beds'],
                    })
                conn.close()
            return jsonify({'success': False, 'error': 'Erreur lors de la modification'}), 500

        if result:
            flash("Statut de la sous-planche mis à jour.", 'success')
        else:
            flash("Erreur lors de la modification du statut.", 'error')
        return redirect(url_for('settings.index', tab='jardins'))

    except Exception as e:
        if is_ajax:
            return jsonify({'success': False, 'error': str(e)}), 500
        flash(f"Erreur: {str(e)}", 'error')
        return redirect(url_for('settings.index', tab='jardins'))


# ========================================
# Crop Routes
# ========================================

@settings_bp.route('/crop/add', methods=['POST'])
def crop_add():
    """Add a new crop."""
    crop_name = request.form.get('crop_name', '').strip()
    category = request.form.get('category', '').strip()

    if not crop_name or not category:
        flash("Veuillez remplir le nom et la catégorie.", 'error')
        return redirect(url_for('settings.index', tab='cultures'))

    family = request.form.get('family', '').strip()
    plant_id = request.form.get('plant_id', type=int)

    result = create_crop(crop_name, category, family, plant_id)
    if result:
        flash(f"Culture « {crop_name} » ajoutée avec succès.", 'success')
    else:
        flash(f"Erreur : la culture « {crop_name} » existe déjà.", 'error')

    return redirect(url_for('settings.index', tab='cultures'))


@settings_bp.route('/crop/delete', methods=['POST'])
def crop_delete():
    """Delete a crop."""
    crop_id = request.form.get('crop_id', type=int)
    if not crop_id:
        flash("Culture non spécifiée.", 'error')
        return redirect(url_for('settings.index', tab='cultures'))

    success, error = delete_crop(crop_id)
    if success:
        flash("Culture supprimée avec succès.", 'success')
    else:
        flash(error or "Erreur lors de la suppression.", 'error')

    return redirect(url_for('settings.index', tab='cultures'))


@settings_bp.route('/crop/category', methods=['POST'])
def crop_category():
    """Change a crop's category."""
    crop_id = request.form.get('crop_id', type=int)
    new_category = request.form.get('category', '').strip()

    if not crop_id or not new_category:
        flash("Veuillez spécifier la culture et la catégorie.", 'error')
        return redirect(url_for('settings.index', tab='cultures'))

    result = update_crop_category(crop_id, new_category)
    if result:
        flash("Catégorie mise à jour avec succès.", 'success')
    else:
        flash("Erreur lors de la mise à jour de la catégorie.", 'error')

    return redirect(url_for('settings.index', tab='cultures'))


# ========================================
# Rotation Sequence Routes
# ========================================

@settings_bp.route('/rotation/save', methods=['POST'])
def rotation_save():
    """Save the rotation sequence order."""
    # Categories come as a list from the form
    categories = request.form.getlist('categories')

    if not categories or len(categories) < 2:
        flash("La séquence de rotation doit contenir au moins 2 catégories.", 'error')
        return redirect(url_for('settings.index', tab='rotation'))

    result = save_rotation_sequence(categories)
    if result:
        flash("Séquence de rotation mise à jour avec succès.", 'success')
    else:
        flash("Erreur lors de la mise à jour de la séquence.", 'error')

    return redirect(url_for('settings.index', tab='rotation'))


# ========================================
# Cycles per year
# ========================================

@settings_bp.route('/cycles/save', methods=['POST'])
def cycles_save():
    """Save cycles per year setting."""
    cycles = request.form.get('cycles_per_year', '2')
    if cycles not in ('1', '2', '3', '4'):
        flash("Valeur invalide pour les cycles par an.", 'error')
        return redirect(url_for('settings.index', tab='cycles'))

    result = update_setting('cycles_per_year', cycles)
    if result:
        flash(f"Cycles par an mis à jour : {cycles}.", 'success')
    else:
        flash("Erreur lors de la mise à jour.", 'error')

    return redirect(url_for('settings.index', tab='cycles'))


# ========================================
# Backup Routes
# ========================================

@settings_bp.route('/backup/create', methods=['POST'])
def backup_create():
    """Create a manual backup."""
    filename = backup_db('manual')
    if filename:
        flash(f"Sauvegarde créée : {filename}", 'success')
    else:
        flash("Erreur lors de la création de la sauvegarde.", 'error')

    return redirect(url_for('settings.index', tab='sauvegardes'))


@settings_bp.route('/backup/restore', methods=['POST'])
def backup_restore():
    """Restore the database from a backup file."""
    filename = request.form.get('filename', '').strip()
    if not filename:
        flash("Fichier de sauvegarde non spécifié.", 'error')
        return redirect(url_for('settings.index', tab='sauvegardes'))

    # Create a safety backup before restoring
    backup_db('pre_restore')

    result = restore_db(filename)
    if result:
        flash(f"Base de données restaurée depuis {filename}.", 'success')
    else:
        flash("Erreur lors de la restauration. Vérifiez le fichier.", 'error')

    return redirect(url_for('settings.index', tab='sauvegardes'))


@settings_bp.route('/backup/delete', methods=['POST'])
def backup_delete():
    """Delete a backup file."""
    filename = request.form.get('filename', '').strip()
    if not filename:
        flash("Fichier de sauvegarde non spécifié.", 'error')
        return redirect(url_for('settings.index', tab='sauvegardes'))

    result = delete_backup(filename)
    if result:
        flash(f"Sauvegarde {filename} supprimée.", 'success')
    else:
        flash("Erreur lors de la suppression de la sauvegarde.", 'error')

    return redirect(url_for('settings.index', tab='sauvegardes'))


@settings_bp.route('/distribution/save', methods=['POST'])
def distribution_save():
    """Save default distribution percentages."""
    crops = get_crops()
    categories = get_categories()
    
    distribution = {}
    
    # Process each category
    for cat in categories:
        cat_crops = [c for c in crops if c['category'] == cat]
        if not cat_crops:
            continue
            
        cat_dist = {}
        # Iterate relevant crops
        for crop in cat_crops:
            key = f"crop_{crop['id']}"
            val_str = request.form.get(key)
            if val_str is not None:
                try:
                    val = float(val_str)
                except ValueError:
                    val = 0.0
                cat_dist[crop['crop_name']] = val
            
        if cat_dist:
            distribution[cat] = cat_dist

    # Save as JSON string
    update_setting('distribution_defaults', json.dumps(distribution))
    flash("Répartition par défaut enregistrée.", 'success')
    return redirect(url_for('settings.index', tab='distribution'))

