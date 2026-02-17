"""
routes/plant_db.py — Plant Database API routes.

Provides:
- GET /plants/ — List all plants
- GET /plants/search — Search plants
- GET /plants/<id> — Get plant details
- POST /plants/add — Add a new plant
- POST /plants/edit — Edit a plant
- POST /plants/delete — Delete a plant
- POST /plants/common-name/add — Add common name
- POST /plants/common-name/edit — Edit common name
- POST /plants/common-name/delete — Delete common name
- POST /plants/synonym/add — Add synonym
- POST /plants/synonym/edit — Edit synonym
- POST /plants/synonym/delete — Delete synonym
- GET /plants/export — Export plant database as JSON
- POST /plants/import — Import plants from JSON
- GET /plants/check-duplicate — Check for duplicate names
- GET /plants/suggestions — Get suggestions for autocomplete
"""

from flask import Blueprint, request, jsonify, flash, redirect, url_for, Response
import json

from plant_database import (
    check_plant_db_health,
    get_all_plants,
    get_plant,
    create_plant,
    update_plant,
    delete_plant,
    add_common_name,
    update_common_name,
    delete_common_name,
    add_synonym,
    update_synonym,
    delete_synonym,
    search_plants,
    check_duplicate,
    export_plants_json,
    import_plants_json,
    get_plant_suggestions,
    get_plant_count,
    set_preferred_name
)
from database import create_crop, get_crops

plant_db_bp = Blueprint('plant_db', __name__, url_prefix='/plants')


# ========================================
# Plant List and Details
# ========================================

@plant_db_bp.route('/')
def list_plants():
    """Get all plants (JSON API)."""
    try:
        plants = get_all_plants()
        return jsonify({'success': True, 'plants': plants})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@plant_db_bp.route('/<int:plant_id>')
def get_plant_detail(plant_id):
    """Get a single plant with all details (JSON API)."""
    try:
        plant = get_plant(plant_id)
        if not plant:
            return jsonify({'success': False, 'error': 'Plante introuvable'}), 404
        return jsonify({'success': True, 'plant': plant})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@plant_db_bp.route('/count')
def plant_count():
    """Get plant count (JSON API)."""
    try:
        count = get_plant_count()
        return jsonify({'success': True, 'count': count})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@plant_db_bp.route('/health')
def plant_db_health():
    """Check plant database health (JSON API)."""
    healthy, message = check_plant_db_health()
    return jsonify({'success': healthy, 'message': message})


# ========================================
# Search and Suggestions
# ========================================

@plant_db_bp.route('/search')
def search():
    """Search plants (JSON API)."""
    query = request.args.get('q', '')
    limit = request.args.get('limit', 20, type=int)

    try:
        results = search_plants(query, limit=limit)
        return jsonify({'success': True, 'results': results})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@plant_db_bp.route('/suggestions')
def suggestions():
    """Get autocomplete suggestions (JSON API)."""
    query = request.args.get('q', '')
    limit = request.args.get('limit', 10, type=int)

    try:
        results = get_plant_suggestions(query, limit=limit)
        return jsonify({'success': True, 'suggestions': results})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@plant_db_bp.route('/check-duplicate')
def check_dup():
    """Check if a name already exists (JSON API)."""
    name = request.args.get('name', '')

    try:
        result = check_duplicate(name)
        if result:
            return jsonify({'success': True, 'duplicate': True, 'info': result})
        return jsonify({'success': True, 'duplicate': False})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ========================================
# Plant CRUD
# ========================================

@plant_db_bp.route('/add', methods=['POST'])
def add_plant():
    """Add a new plant."""
    # Support both JSON and form data
    if request.is_json:
        data = request.get_json()
        scientific_name = data.get('scientific_name', '')
        family = data.get('family', '')
        default_category = data.get('default_category', '')
        common_names = data.get('common_names', [])
        synonyms = data.get('synonyms', [])
    else:
        scientific_name = request.form.get('scientific_name', '').strip()
        family = request.form.get('family', '').strip()
        default_category = request.form.get('default_category', '').strip()

        # Parse preferred name (first, marked as preferred)
        preferred_name = request.form.get('preferred_name', '').strip()

        # Parse common names from form (comma-separated or multiple fields)
        common_names_raw = request.form.get('common_names', '')
        common_names = []

        # Add preferred name first if provided
        if preferred_name:
            common_names.append({'name': preferred_name, 'lang': 'fr', 'is_preferred': True})

        # Add other common names
        # If no preferred_name was given, don't set is_preferred explicitly -
        # let create_plant() use its default logic (first name becomes preferred)
        if common_names_raw:
            for n in common_names_raw.split(','):
                name = n.strip()
                if name and name != preferred_name:
                    # Only explicitly set is_preferred=False if we already have a preferred name
                    if preferred_name:
                        common_names.append({'name': name, 'lang': 'fr', 'is_preferred': False})
                    else:
                        common_names.append({'name': name, 'lang': 'fr'})

        # Parse synonyms from form
        synonyms_raw = request.form.get('synonyms', '')
        if synonyms_raw:
            synonyms = [s.strip() for s in synonyms_raw.split(',') if s.strip()]
        else:
            synonyms = []

    plant_id, error = create_plant(
        scientific_name=scientific_name,
        family=family,
        default_category=default_category,
        common_names=common_names,
        synonyms=synonyms
    )

    if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        if plant_id:
            plant = get_plant(plant_id)
            return jsonify({'success': True, 'plant_id': plant_id, 'plant': plant})
        return jsonify({'success': False, 'error': error}), 400

    # Form submission - redirect
    if plant_id:
        flash(f"Plante « {scientific_name} » ajoutée avec succès.", 'success')
    else:
        flash(error or "Erreur lors de l'ajout de la plante.", 'error')

    return redirect(url_for('settings.index', tab='plantes'))


@plant_db_bp.route('/edit', methods=['POST'])
def edit_plant():
    """Edit a plant's basic information."""
    if request.is_json:
        data = request.get_json()
        plant_id = data.get('plant_id')
        scientific_name = data.get('scientific_name')
        family = data.get('family')
        default_category = data.get('default_category')
    else:
        plant_id = request.form.get('plant_id', type=int)
        scientific_name = request.form.get('scientific_name')
        family = request.form.get('family')
        default_category = request.form.get('default_category')

    if not plant_id:
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': 'ID de plante manquant'}), 400
        flash("ID de plante manquant.", 'error')
        return redirect(url_for('settings.index', tab='plantes'))

    success, error = update_plant(
        plant_id=plant_id,
        scientific_name=scientific_name,
        family=family,
        default_category=default_category
    )

    if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        if success:
            plant = get_plant(plant_id)
            return jsonify({'success': True, 'plant': plant})
        return jsonify({'success': False, 'error': error}), 400

    if success:
        flash("Plante mise à jour avec succès.", 'success')
    else:
        flash(error or "Erreur lors de la mise à jour.", 'error')

    return redirect(url_for('settings.index', tab='plantes'))


@plant_db_bp.route('/delete', methods=['POST'])
def remove_plant():
    """Delete a plant."""
    if request.is_json:
        data = request.get_json()
        plant_id = data.get('plant_id')
    else:
        plant_id = request.form.get('plant_id', type=int)

    if not plant_id:
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': 'ID de plante manquant'}), 400
        flash("ID de plante manquant.", 'error')
        return redirect(url_for('settings.index', tab='plantes'))

    success, error = delete_plant(plant_id)

    if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        if success:
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': error}), 400

    if success:
        flash("Plante supprimée avec succès.", 'success')
    else:
        flash(error or "Erreur lors de la suppression.", 'error')

    return redirect(url_for('settings.index', tab='plantes'))


# ========================================
# Common Names CRUD
# ========================================

@plant_db_bp.route('/common-name/add', methods=['POST'])
def add_cn():
    """Add a common name to a plant."""
    if request.is_json:
        data = request.get_json()
        plant_id = data.get('plant_id')
        name = data.get('name', '')
        lang = data.get('lang', 'fr')
    else:
        plant_id = request.form.get('plant_id', type=int)
        name = request.form.get('name', '').strip()
        lang = request.form.get('lang', 'fr')

    if not plant_id or not name:
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': 'ID de plante et nom requis'}), 400
        flash("ID de plante et nom requis.", 'error')
        return redirect(url_for('settings.index', tab='plantes'))

    cn_id, error = add_common_name(plant_id, name, lang)

    if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        if cn_id:
            return jsonify({'success': True, 'common_name_id': cn_id})
        return jsonify({'success': False, 'error': error}), 400

    if cn_id:
        flash(f"Nom commun « {name} » ajouté.", 'success')
    else:
        flash(error or "Erreur lors de l'ajout.", 'error')

    return redirect(url_for('settings.index', tab='plantes'))


@plant_db_bp.route('/common-name/edit', methods=['POST'])
def edit_cn():
    """Edit a common name."""
    if request.is_json:
        data = request.get_json()
        common_name_id = data.get('common_name_id')
        name = data.get('name', '')
        lang = data.get('lang')
    else:
        common_name_id = request.form.get('common_name_id', type=int)
        name = request.form.get('name', '').strip()
        lang = request.form.get('lang')

    if not common_name_id or not name:
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': 'ID et nom requis'}), 400
        flash("ID et nom requis.", 'error')
        return redirect(url_for('settings.index', tab='plantes'))

    success, error = update_common_name(common_name_id, name, lang)

    if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        if success:
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': error}), 400

    if success:
        flash("Nom commun mis à jour.", 'success')
    else:
        flash(error or "Erreur lors de la mise à jour.", 'error')

    return redirect(url_for('settings.index', tab='plantes'))


@plant_db_bp.route('/common-name/delete', methods=['POST'])
def remove_cn():
    """Delete a common name."""
    if request.is_json:
        data = request.get_json()
        common_name_id = data.get('common_name_id')
    else:
        common_name_id = request.form.get('common_name_id', type=int)

    if not common_name_id:
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': 'ID requis'}), 400
        flash("ID requis.", 'error')
        return redirect(url_for('settings.index', tab='plantes'))

    success, error = delete_common_name(common_name_id)

    if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        if success:
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': error}), 400

    if success:
        flash("Nom commun supprimé.", 'success')
    else:
        flash(error or "Erreur lors de la suppression.", 'error')

    return redirect(url_for('settings.index', tab='plantes'))


@plant_db_bp.route('/common-name/set-preferred', methods=['POST'])
def set_preferred():
    """Set a common name as the preferred name."""
    if request.is_json:
        data = request.get_json()
        common_name_id = data.get('common_name_id')
    else:
        common_name_id = request.form.get('common_name_id', type=int)

    if not common_name_id:
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': 'ID requis'}), 400
        flash("ID requis.", 'error')
        return redirect(url_for('settings.index', tab='plantes'))

    success, error = set_preferred_name(common_name_id)

    if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        if success:
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': error}), 400

    if success:
        flash("Nom préféré mis à jour.", 'success')
    else:
        flash(error or "Erreur lors de la mise à jour.", 'error')

    return redirect(url_for('settings.index', tab='plantes'))


# ========================================
# Synonyms CRUD
# ========================================

@plant_db_bp.route('/synonym/add', methods=['POST'])
def add_syn():
    """Add a synonym to a plant."""
    if request.is_json:
        data = request.get_json()
        plant_id = data.get('plant_id')
        synonym = data.get('synonym', '')
    else:
        plant_id = request.form.get('plant_id', type=int)
        synonym = request.form.get('synonym', '').strip()

    if not plant_id or not synonym:
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': 'ID de plante et synonyme requis'}), 400
        flash("ID de plante et synonyme requis.", 'error')
        return redirect(url_for('settings.index', tab='plantes'))

    syn_id, error = add_synonym(plant_id, synonym)

    if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        if syn_id:
            return jsonify({'success': True, 'synonym_id': syn_id})
        return jsonify({'success': False, 'error': error}), 400

    if syn_id:
        flash(f"Synonyme « {synonym} » ajouté.", 'success')
    else:
        flash(error or "Erreur lors de l'ajout.", 'error')

    return redirect(url_for('settings.index', tab='plantes'))


@plant_db_bp.route('/synonym/edit', methods=['POST'])
def edit_syn():
    """Edit a synonym."""
    if request.is_json:
        data = request.get_json()
        synonym_id = data.get('synonym_id')
        synonym = data.get('synonym', '')
    else:
        synonym_id = request.form.get('synonym_id', type=int)
        synonym = request.form.get('synonym', '').strip()

    if not synonym_id or not synonym:
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': 'ID et synonyme requis'}), 400
        flash("ID et synonyme requis.", 'error')
        return redirect(url_for('settings.index', tab='plantes'))

    success, error = update_synonym(synonym_id, synonym)

    if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        if success:
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': error}), 400

    if success:
        flash("Synonyme mis à jour.", 'success')
    else:
        flash(error or "Erreur lors de la mise à jour.", 'error')

    return redirect(url_for('settings.index', tab='plantes'))


@plant_db_bp.route('/synonym/delete', methods=['POST'])
def remove_syn():
    """Delete a synonym."""
    if request.is_json:
        data = request.get_json()
        synonym_id = data.get('synonym_id')
    else:
        synonym_id = request.form.get('synonym_id', type=int)

    if not synonym_id:
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': 'ID requis'}), 400
        flash("ID requis.", 'error')
        return redirect(url_for('settings.index', tab='plantes'))

    success, error = delete_synonym(synonym_id)

    if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        if success:
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': error}), 400

    if success:
        flash("Synonyme supprimé.", 'success')
    else:
        flash(error or "Erreur lors de la suppression.", 'error')

    return redirect(url_for('settings.index', tab='plantes'))


# ========================================
# JSON Export / Import
# ========================================

@plant_db_bp.route('/export')
def export_json():
    """Export plant database as JSON file download."""
    try:
        data = export_plants_json()

        # Create response with JSON file download
        response = Response(
            json.dumps(data, indent=2, ensure_ascii=False),
            mimetype='application/json',
            headers={
                'Content-Disposition': 'attachment; filename=plant_database.json'
            }
        )
        return response
    except Exception as e:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': str(e)}), 500
        flash(f"Erreur lors de l'export: {str(e)}", 'error')
        return redirect(url_for('settings.index', tab='plantes'))


@plant_db_bp.route('/add-to-crops', methods=['POST'])
def add_to_crops():
    """Add a plant to the crops table for use in rotations."""
    if request.is_json:
        data = request.get_json()
        plant_id = data.get('plant_id')
    else:
        plant_id = request.form.get('plant_id', type=int)

    if not plant_id:
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': 'ID de plante manquant'}), 400
        flash("ID de plante manquant.", 'error')
        return redirect(url_for('settings.index', tab='plantes'))

    # Get plant details
    plant = get_plant(plant_id)
    if not plant:
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': 'Plante introuvable'}), 404
        flash("Plante introuvable.", 'error')
        return redirect(url_for('settings.index', tab='plantes'))

    # Use preferred common name if available, otherwise fall back to scientific name
    crop_name = None
    for cn in plant.get('common_names', []):
        if cn.get('is_preferred'):
            crop_name = cn['name']
            break
    if not crop_name:
        crop_name = plant['scientific_name']

    category = plant.get('default_category', '')
    family = plant.get('family', '')

    if not category:
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': False,
                'error': 'Cette plante n\'a pas de catégorie définie. Modifiez-la d\'abord.'
            }), 400
        flash("Cette plante n'a pas de catégorie définie. Modifiez-la d'abord.", 'error')
        return redirect(url_for('settings.index', tab='plantes'))

    # Check if crop already exists
    existing_crops = get_crops()
    for crop in existing_crops:
        if crop['crop_name'].lower() == crop_name.lower():
            if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'success': False,
                    'error': f'La culture « {crop_name} » existe déjà.'
                }), 400
            flash(f"La culture « {crop_name} » existe déjà.", 'warning')
            return redirect(url_for('settings.index', tab='plantes'))

    # Create the crop
    result = create_crop(crop_name, category, family, plant_id)

    if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        if result:
            return jsonify({
                'success': True,
                'message': f'Culture « {crop_name} » ajoutée avec succès.',
                'crop_name': crop_name,
                'category': category
            })
        return jsonify({'success': False, 'error': 'Erreur lors de la création de la culture'}), 500

    if result:
        flash(f"Culture « {crop_name} » ajoutée avec succès.", 'success')
    else:
        flash("Erreur lors de la création de la culture.", 'error')

    return redirect(url_for('settings.index', tab='plantes'))


@plant_db_bp.route('/import', methods=['POST'])
def import_json():
    """Import plants from JSON file."""
    mode = request.form.get('mode', 'merge')

    if 'file' not in request.files:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': 'Aucun fichier sélectionné'}), 400
        flash("Aucun fichier sélectionné.", 'error')
        return redirect(url_for('settings.index', tab='plantes'))

    file = request.files['file']
    if file.filename == '':
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': 'Aucun fichier sélectionné'}), 400
        flash("Aucun fichier sélectionné.", 'error')
        return redirect(url_for('settings.index', tab='plantes'))

    try:
        data = json.load(file)
    except json.JSONDecodeError as e:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': f'JSON invalide: {str(e)}'}), 400
        flash(f"Fichier JSON invalide: {str(e)}", 'error')
        return redirect(url_for('settings.index', tab='plantes'))

    success, message, stats = import_plants_json(data, mode=mode)

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'success': success,
            'message': message,
            'stats': stats
        })

    if success:
        flash(message, 'success')
    else:
        flash(message, 'error')

    return redirect(url_for('settings.index', tab='plantes'))
