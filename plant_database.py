"""
plant_database.py — Separate Plant Database for canonical plant information.

This module manages a SEPARATE SQLite database for plant data:
- Scientific names with normalized versions for duplicate detection
- Common names (multiple languages)
- Synonyms
- Botanical families and default categories

The plant database is independent from the crop rotation database.
"""

import sqlite3
import os
import unicodedata
import re
from typing import Optional, List, Dict, Any, Tuple


# Default path for plant database (can be overridden via env var)
def get_plant_db_path() -> str:
    """Get the plant database path from environment or default."""
    default_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'plant_database.db')
    return os.environ.get('PLANT_DB_PATH', default_path)


# ========================================
# Normalization Helper
# ========================================

def normalize_name(name: str) -> str:
    """
    Normalize a plant name for duplicate detection and searching.

    Rules:
    - lowercase
    - trim whitespace
    - collapse multiple whitespace to single space
    - remove diacritics (accents)
    - remove hyphens and punctuation
    - strip extra spaces

    Examples:
        "Brassica oleracea" -> "brassica oleracea"
        "Brassica-Oleracea" -> "brassica oleracea"
        "Épinard" -> "epinard"
        "  Tomate   Rouge  " -> "tomate rouge"
    """
    if not name:
        return ""

    # Lowercase and strip
    result = name.lower().strip()

    # Remove diacritics (accents)
    # NFD decomposition separates base characters from combining diacritical marks
    result = unicodedata.normalize('NFD', result)
    result = ''.join(c for c in result if unicodedata.category(c) != 'Mn')

    # Replace hyphens and common punctuation with spaces
    result = re.sub(r'[-_.,;:\'\"()]+', ' ', result)

    # Collapse multiple whitespace to single space
    result = re.sub(r'\s+', ' ', result)

    # Final strip
    return result.strip()


# ========================================
# Database Connection Management
# ========================================

def get_plant_db() -> sqlite3.Connection:
    """
    Get a connection to the plant database.

    Creates the database directory and file if they don't exist.
    Uses WAL mode for concurrent read performance.
    """
    db_path = get_plant_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_plant_db():
    """
    Initialize the plant database schema.

    Creates all tables and indexes if they don't exist.
    This function is idempotent - safe to call multiple times.
    """
    conn = get_plant_db()
    cursor = conn.cursor()

    # Table: plants
    # - scientific_name: Full scientific name including infraspecific details
    # - base_species: Species-level name for rotation grouping (e.g., "Capsicum annuum")
    # - infraspecific_detail: Variety/cultivar group info (e.g., "var. capitata", "Grossum Group")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS plants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scientific_name TEXT NOT NULL,
            scientific_name_norm TEXT NOT NULL UNIQUE,
            base_species TEXT DEFAULT '',
            base_species_norm TEXT DEFAULT '',
            infraspecific_detail TEXT DEFAULT '',
            family TEXT DEFAULT '',
            default_category TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Index on scientific_name_norm for fast lookup
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_plants_scientific_name_norm
        ON plants(scientific_name_norm)
    """)

    # Index on base_species_norm for species-level rotation queries
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_plants_base_species_norm
        ON plants(base_species_norm)
    """)

    # Index on family for family-level rotation queries
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_plants_family
        ON plants(family)
    """)

    # Table: plant_common_names
    # - is_preferred: Marks the preferred display name for UI (one per plant+lang)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS plant_common_names (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plant_id INTEGER NOT NULL REFERENCES plants(id) ON DELETE CASCADE,
            common_name TEXT NOT NULL,
            common_name_norm TEXT NOT NULL,
            lang TEXT DEFAULT 'fr',
            is_preferred INTEGER DEFAULT 0,
            UNIQUE(plant_id, common_name_norm)
        )
    """)

    # Index on common_name_norm for fast search
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_plant_common_names_norm
        ON plant_common_names(common_name_norm)
    """)

    # Table: plant_synonyms
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS plant_synonyms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plant_id INTEGER NOT NULL REFERENCES plants(id) ON DELETE CASCADE,
            synonym TEXT NOT NULL,
            synonym_norm TEXT NOT NULL UNIQUE
        )
    """)

    # Index on synonym_norm for fast search
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_plant_synonyms_norm
        ON plant_synonyms(synonym_norm)
    """)

    conn.commit()
    conn.close()

    # Run migrations for existing databases
    _migrate_plant_db_schema()


def _migrate_plant_db_schema():
    """
    Migrate existing plant database to add new columns.

    Adds:
    - base_species, base_species_norm, infraspecific_detail to plants table
    - is_preferred to plant_common_names table

    This function is idempotent - safe to call multiple times.
    """
    conn = get_plant_db()
    cursor = conn.cursor()

    try:
        # Check plants table columns
        plant_columns = [i[1] for i in cursor.execute("PRAGMA table_info(plants)").fetchall()]

        # Add base_species columns if missing
        if 'base_species' not in plant_columns:
            cursor.execute("ALTER TABLE plants ADD COLUMN base_species TEXT DEFAULT ''")
            cursor.execute("ALTER TABLE plants ADD COLUMN base_species_norm TEXT DEFAULT ''")
            cursor.execute("ALTER TABLE plants ADD COLUMN infraspecific_detail TEXT DEFAULT ''")

            # Populate base_species from scientific_name for existing records
            # For simple species names, base_species = scientific_name
            cursor.execute("""
                UPDATE plants
                SET base_species = scientific_name,
                    base_species_norm = scientific_name_norm
                WHERE base_species = '' OR base_species IS NULL
            """)

            # Create index for base_species lookups
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_plants_base_species_norm
                ON plants(base_species_norm)
            """)

        # Check plant_common_names columns
        cn_columns = [i[1] for i in cursor.execute("PRAGMA table_info(plant_common_names)").fetchall()]

        # Add is_preferred column if missing
        if 'is_preferred' not in cn_columns:
            cursor.execute("ALTER TABLE plant_common_names ADD COLUMN is_preferred INTEGER DEFAULT 0")

            # Set first common name per (plant, lang) as preferred
            cursor.execute("""
                UPDATE plant_common_names
                SET is_preferred = 1
                WHERE id IN (
                    SELECT MIN(id) FROM plant_common_names
                    GROUP BY plant_id, lang
                )
            """)

        conn.commit()

    except Exception as e:
        print(f"Warning: Plant database migration failed: {e}")
        conn.rollback()
    finally:
        conn.close()


def check_plant_db_health() -> Tuple[bool, str]:
    """
    Check if the plant database is healthy and accessible.

    Returns:
        Tuple of (is_healthy, message)
    """
    try:
        conn = get_plant_db()
        # Try to query the plants table
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM plants")
        count = cursor.fetchone()[0]
        conn.close()
        return True, f"Plant database OK ({count} plants)"
    except sqlite3.DatabaseError as e:
        return False, f"Database error: {str(e)}"
    except Exception as e:
        return False, f"Error: {str(e)}"


# ========================================
# Plant CRUD Operations
# ========================================

def create_plant(
    scientific_name: str,
    family: str = '',
    default_category: str = '',
    common_names: Optional[List[Dict[str, str]]] = None,
    synonyms: Optional[List[str]] = None,
    base_species: str = '',
    infraspecific_detail: str = ''
) -> Tuple[Optional[int], Optional[str]]:
    """
    Create a new plant in the database.

    Args:
        scientific_name: Full scientific name (required), e.g., "Capsicum annuum Grossum Group"
        family: Botanical family, e.g., "Solanaceae"
        default_category: Default crop category (Feuille, Graine, Racine, Fruit, Couverture)
        common_names: List of dicts with 'name', optional 'lang', and optional 'is_preferred' keys
        synonyms: List of synonym strings
        base_species: Species-level name for rotation grouping, e.g., "Capsicum annuum"
                      If not provided, defaults to scientific_name
        infraspecific_detail: Variety/cultivar info, e.g., "Grossum Group", "var. capitata"

    Returns:
        Tuple of (plant_id, error_message)
        If successful, plant_id is set and error_message is None
        If failed, plant_id is None and error_message describes the error
    """
    if not scientific_name or not scientific_name.strip():
        return None, "Le nom scientifique est requis."

    scientific_name = scientific_name.strip()
    scientific_name_norm = normalize_name(scientific_name)

    # Default base_species to scientific_name if not provided
    base_species = base_species.strip() if base_species else scientific_name
    base_species_norm = normalize_name(base_species)
    infraspecific_detail = infraspecific_detail.strip() if infraspecific_detail else ''

    conn = get_plant_db()
    cursor = conn.cursor()

    try:
        # Check for existing plant with same normalized name
        existing = cursor.execute(
            "SELECT id, scientific_name FROM plants WHERE scientific_name_norm = ?",
            (scientific_name_norm,)
        ).fetchone()

        if existing:
            return None, f"Cette plante existe déjà: {existing['scientific_name']}"

        # Insert the plant
        cursor.execute(
            """INSERT INTO plants (scientific_name, scientific_name_norm, base_species,
               base_species_norm, infraspecific_detail, family, default_category)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (scientific_name, scientific_name_norm, base_species, base_species_norm,
             infraspecific_detail, family.strip(), default_category.strip())
        )
        plant_id = cursor.lastrowid

        # Add common names
        if common_names:
            # Track if we've set a preferred name for each language
            preferred_set = set()

            for cn in common_names:
                name = cn.get('name', '').strip()
                if name:
                    lang = cn.get('lang', 'fr')
                    name_norm = normalize_name(name)
                    # First name in each language becomes preferred unless explicitly set
                    is_preferred = cn.get('is_preferred', lang not in preferred_set)
                    if is_preferred:
                        preferred_set.add(lang)

                    try:
                        cursor.execute(
                            """INSERT INTO plant_common_names
                               (plant_id, common_name, common_name_norm, lang, is_preferred)
                               VALUES (?, ?, ?, ?, ?)""",
                            (plant_id, name, name_norm, lang, 1 if is_preferred else 0)
                        )
                    except sqlite3.IntegrityError:
                        # Skip duplicate common names for this plant
                        pass

        # Add synonyms
        if synonyms:
            for syn in synonyms:
                syn = syn.strip()
                if syn:
                    syn_norm = normalize_name(syn)
                    try:
                        cursor.execute(
                            """INSERT INTO plant_synonyms (plant_id, synonym, synonym_norm)
                               VALUES (?, ?, ?)""",
                            (plant_id, syn, syn_norm)
                        )
                    except sqlite3.IntegrityError:
                        # Synonym already exists (possibly for another plant)
                        pass

        conn.commit()
        return plant_id, None

    except sqlite3.IntegrityError as e:
        conn.rollback()
        return None, f"Erreur d'intégrité: {str(e)}"
    except Exception as e:
        conn.rollback()
        return None, f"Erreur: {str(e)}"
    finally:
        conn.close()


def get_plant(plant_id: int) -> Optional[Dict[str, Any]]:
    """
    Get a plant by ID with all its common names and synonyms.

    Returns:
        Dict with plant data or None if not found
    """
    conn = get_plant_db()
    cursor = conn.cursor()

    try:
        # Get plant
        plant = cursor.execute(
            "SELECT * FROM plants WHERE id = ?", (plant_id,)
        ).fetchone()

        if not plant:
            return None

        # Get common names
        common_names = cursor.execute(
            "SELECT * FROM plant_common_names WHERE plant_id = ? ORDER BY lang, common_name",
            (plant_id,)
        ).fetchall()

        # Get synonyms
        synonyms = cursor.execute(
            "SELECT * FROM plant_synonyms WHERE plant_id = ? ORDER BY synonym",
            (plant_id,)
        ).fetchall()

        # Find preferred name from common names
        preferred_name = None
        for cn in common_names:
            if 'is_preferred' in cn.keys() and cn['is_preferred']:
                preferred_name = cn['common_name']
                break

        return {
            'id': plant['id'],
            'scientific_name': plant['scientific_name'],
            'scientific_name_norm': plant['scientific_name_norm'],
            'preferred_name': preferred_name,
            'base_species': plant['base_species'] if 'base_species' in plant.keys() else '',
            'base_species_norm': plant['base_species_norm'] if 'base_species_norm' in plant.keys() else '',
            'infraspecific_detail': plant['infraspecific_detail'] if 'infraspecific_detail' in plant.keys() else '',
            'family': plant['family'],
            'default_category': plant['default_category'],
            'created_at': plant['created_at'],
            'updated_at': plant['updated_at'],
            'common_names': [
                {
                    'id': cn['id'],
                    'name': cn['common_name'],
                    'lang': cn['lang'],
                    'is_preferred': bool(cn['is_preferred']) if 'is_preferred' in cn.keys() else False
                }
                for cn in common_names
            ],
            'synonyms': [
                {'id': s['id'], 'synonym': s['synonym']}
                for s in synonyms
            ]
        }
    finally:
        conn.close()


def get_all_plants() -> List[Dict[str, Any]]:
    """
    Get all plants with their common names count, synonyms count, and search text.

    Returns:
        List of plant dicts with counts and search_text for client-side filtering
    """
    conn = get_plant_db()
    cursor = conn.cursor()

    try:
        plants = cursor.execute("""
            SELECT
                p.*,
                (SELECT COUNT(*) FROM plant_common_names WHERE plant_id = p.id) as common_names_count,
                (SELECT COUNT(*) FROM plant_synonyms WHERE plant_id = p.id) as synonyms_count,
                (SELECT GROUP_CONCAT(common_name, ' ') FROM plant_common_names WHERE plant_id = p.id) as common_names_text,
                (SELECT GROUP_CONCAT(synonym, ' ') FROM plant_synonyms WHERE plant_id = p.id) as synonyms_text,
                (SELECT common_name FROM plant_common_names WHERE plant_id = p.id AND lang = 'fr' AND is_preferred = 1 LIMIT 1) as preferred_name
            FROM plants p
            ORDER BY p.scientific_name
        """).fetchall()

        result = []
        for p in plants:
            plant_dict = dict(p)
            # Build search text including all searchable fields
            search_parts = [
                plant_dict.get('scientific_name', ''),
                plant_dict.get('family', ''),
                plant_dict.get('default_category', ''),
                plant_dict.get('common_names_text', '') or '',
                plant_dict.get('synonyms_text', '') or '',
                plant_dict.get('preferred_name', '') or ''
            ]
            plant_dict['search_text'] = ' '.join(search_parts).lower()
            result.append(plant_dict)

        return result
    finally:
        conn.close()


def update_plant(
    plant_id: int,
    scientific_name: Optional[str] = None,
    family: Optional[str] = None,
    default_category: Optional[str] = None,
    base_species: Optional[str] = None,
    infraspecific_detail: Optional[str] = None
) -> Tuple[bool, Optional[str]]:
    """
    Update a plant's basic information.

    Args:
        plant_id: ID of the plant to update
        scientific_name: New scientific name (optional)
        family: New family (optional)
        default_category: New default category (optional)
        base_species: New base species for rotation grouping (optional)
        infraspecific_detail: New infraspecific detail (optional)

    Returns:
        Tuple of (success, error_message)
    """
    conn = get_plant_db()
    cursor = conn.cursor()

    try:
        # Check plant exists
        existing = cursor.execute(
            "SELECT * FROM plants WHERE id = ?", (plant_id,)
        ).fetchone()

        if not existing:
            return False, "Plante introuvable."

        updates = []
        params = []

        if scientific_name is not None:
            scientific_name = scientific_name.strip()
            if not scientific_name:
                return False, "Le nom scientifique ne peut pas être vide."

            scientific_name_norm = normalize_name(scientific_name)

            # Check for duplicate (excluding current plant)
            dup = cursor.execute(
                "SELECT id FROM plants WHERE scientific_name_norm = ? AND id != ?",
                (scientific_name_norm, plant_id)
            ).fetchone()

            if dup:
                return False, "Une autre plante avec ce nom scientifique existe déjà."

            updates.append("scientific_name = ?")
            params.append(scientific_name)
            updates.append("scientific_name_norm = ?")
            params.append(scientific_name_norm)

        if family is not None:
            updates.append("family = ?")
            params.append(family.strip())

        if default_category is not None:
            updates.append("default_category = ?")
            params.append(default_category.strip())

        if base_species is not None:
            base_species = base_species.strip()
            updates.append("base_species = ?")
            params.append(base_species)
            updates.append("base_species_norm = ?")
            params.append(normalize_name(base_species))

        if infraspecific_detail is not None:
            updates.append("infraspecific_detail = ?")
            params.append(infraspecific_detail.strip())

        if updates:
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(plant_id)

            cursor.execute(
                f"UPDATE plants SET {', '.join(updates)} WHERE id = ?",
                params
            )
            conn.commit()

        return True, None

    except Exception as e:
        conn.rollback()
        return False, f"Erreur: {str(e)}"
    finally:
        conn.close()


def delete_plant(plant_id: int, check_crop_links: bool = True) -> Tuple[bool, Optional[str]]:
    """
    Delete a plant from the database.

    Args:
        plant_id: ID of the plant to delete
        check_crop_links: If True, check if plant is linked to crops (requires integration)

    Returns:
        Tuple of (success, error_message)
    """
    conn = get_plant_db()
    cursor = conn.cursor()

    try:
        # Check plant exists
        existing = cursor.execute(
            "SELECT * FROM plants WHERE id = ?", (plant_id,)
        ).fetchone()

        if not existing:
            return False, "Plante introuvable."

        # Delete plant (cascade will delete common names and synonyms)
        cursor.execute("DELETE FROM plants WHERE id = ?", (plant_id,))
        conn.commit()

        return True, None

    except Exception as e:
        conn.rollback()
        return False, f"Erreur: {str(e)}"
    finally:
        conn.close()


# ========================================
# Common Names CRUD
# ========================================

def add_common_name(plant_id: int, name: str, lang: str = 'fr', is_preferred: bool = False) -> Tuple[Optional[int], Optional[str]]:
    """
    Add a common name to a plant.

    Args:
        plant_id: ID of the plant
        name: The common name to add
        lang: Language code (default 'fr')
        is_preferred: If True, this becomes the preferred name for this language
                      (clears is_preferred on other names in same language)

    Returns:
        Tuple of (common_name_id, error_message)
    """
    if not name or not name.strip():
        return None, "Le nom commun est requis."

    name = name.strip()
    name_norm = normalize_name(name)

    conn = get_plant_db()
    cursor = conn.cursor()

    try:
        # Check plant exists
        plant = cursor.execute(
            "SELECT id FROM plants WHERE id = ?", (plant_id,)
        ).fetchone()

        if not plant:
            return None, "Plante introuvable."

        # Check for duplicate
        existing = cursor.execute(
            "SELECT id FROM plant_common_names WHERE plant_id = ? AND common_name_norm = ?",
            (plant_id, name_norm)
        ).fetchone()

        if existing:
            return None, "Ce nom commun existe déjà pour cette plante."

        # If this is preferred, clear is_preferred on other names in same language
        if is_preferred:
            cursor.execute(
                "UPDATE plant_common_names SET is_preferred = 0 WHERE plant_id = ? AND lang = ?",
                (plant_id, lang)
            )

        cursor.execute(
            """INSERT INTO plant_common_names (plant_id, common_name, common_name_norm, lang, is_preferred)
               VALUES (?, ?, ?, ?, ?)""",
            (plant_id, name, name_norm, lang, 1 if is_preferred else 0)
        )
        cn_id = cursor.lastrowid
        conn.commit()

        return cn_id, None

    except Exception as e:
        conn.rollback()
        return None, f"Erreur: {str(e)}"
    finally:
        conn.close()


def update_common_name(
    common_name_id: int,
    name: str,
    lang: Optional[str] = None,
    is_preferred: Optional[bool] = None
) -> Tuple[bool, Optional[str]]:
    """
    Update a common name.

    Args:
        common_name_id: ID of the common name to update
        name: New name value
        lang: New language code (optional)
        is_preferred: If True, this becomes the preferred name for this language

    Returns:
        Tuple of (success, error_message)
    """
    if not name or not name.strip():
        return False, "Le nom commun est requis."

    name = name.strip()
    name_norm = normalize_name(name)

    conn = get_plant_db()
    cursor = conn.cursor()

    try:
        # Get existing
        existing = cursor.execute(
            "SELECT * FROM plant_common_names WHERE id = ?", (common_name_id,)
        ).fetchone()

        if not existing:
            return False, "Nom commun introuvable."

        # Check for duplicate (excluding current)
        dup = cursor.execute(
            "SELECT id FROM plant_common_names WHERE plant_id = ? AND common_name_norm = ? AND id != ?",
            (existing['plant_id'], name_norm, common_name_id)
        ).fetchone()

        if dup:
            return False, "Ce nom commun existe déjà pour cette plante."

        # Determine the effective language
        effective_lang = lang if lang is not None else existing['lang']

        # If setting as preferred, clear is_preferred on other names in same language
        if is_preferred:
            cursor.execute(
                "UPDATE plant_common_names SET is_preferred = 0 WHERE plant_id = ? AND lang = ? AND id != ?",
                (existing['plant_id'], effective_lang, common_name_id)
            )

        # Build update query
        if lang is not None and is_preferred is not None:
            cursor.execute(
                "UPDATE plant_common_names SET common_name = ?, common_name_norm = ?, lang = ?, is_preferred = ? WHERE id = ?",
                (name, name_norm, lang, 1 if is_preferred else 0, common_name_id)
            )
        elif lang is not None:
            cursor.execute(
                "UPDATE plant_common_names SET common_name = ?, common_name_norm = ?, lang = ? WHERE id = ?",
                (name, name_norm, lang, common_name_id)
            )
        elif is_preferred is not None:
            cursor.execute(
                "UPDATE plant_common_names SET common_name = ?, common_name_norm = ?, is_preferred = ? WHERE id = ?",
                (name, name_norm, 1 if is_preferred else 0, common_name_id)
            )
        else:
            cursor.execute(
                "UPDATE plant_common_names SET common_name = ?, common_name_norm = ? WHERE id = ?",
                (name, name_norm, common_name_id)
            )

        conn.commit()
        return True, None

    except Exception as e:
        conn.rollback()
        return False, f"Erreur: {str(e)}"
    finally:
        conn.close()


def delete_common_name(common_name_id: int) -> Tuple[bool, Optional[str]]:
    """
    Delete a common name.

    Returns:
        Tuple of (success, error_message)
    """
    conn = get_plant_db()
    cursor = conn.cursor()

    try:
        cursor.execute("DELETE FROM plant_common_names WHERE id = ?", (common_name_id,))
        if cursor.rowcount == 0:
            return False, "Nom commun introuvable."

        conn.commit()
        return True, None

    except Exception as e:
        conn.rollback()
        return False, f"Erreur: {str(e)}"
    finally:
        conn.close()


# ========================================
# Synonyms CRUD
# ========================================

def add_synonym(plant_id: int, synonym: str) -> Tuple[Optional[int], Optional[str]]:
    """
    Add a synonym to a plant.

    Returns:
        Tuple of (synonym_id, error_message)
    """
    if not synonym or not synonym.strip():
        return None, "Le synonyme est requis."

    synonym = synonym.strip()
    synonym_norm = normalize_name(synonym)

    conn = get_plant_db()
    cursor = conn.cursor()

    try:
        # Check plant exists
        plant = cursor.execute(
            "SELECT id FROM plants WHERE id = ?", (plant_id,)
        ).fetchone()

        if not plant:
            return None, "Plante introuvable."

        # Check for duplicate (globally - synonyms must be unique across all plants)
        existing = cursor.execute(
            "SELECT ps.id, p.scientific_name FROM plant_synonyms ps JOIN plants p ON ps.plant_id = p.id WHERE ps.synonym_norm = ?",
            (synonym_norm,)
        ).fetchone()

        if existing:
            return None, f"Ce synonyme est déjà utilisé pour: {existing['scientific_name']}"

        # Also check if this matches a scientific name
        sci_match = cursor.execute(
            "SELECT scientific_name FROM plants WHERE scientific_name_norm = ?",
            (synonym_norm,)
        ).fetchone()

        if sci_match:
            return None, f"Ce nom est déjà un nom scientifique: {sci_match['scientific_name']}"

        cursor.execute(
            """INSERT INTO plant_synonyms (plant_id, synonym, synonym_norm)
               VALUES (?, ?, ?)""",
            (plant_id, synonym, synonym_norm)
        )
        syn_id = cursor.lastrowid
        conn.commit()

        return syn_id, None

    except Exception as e:
        conn.rollback()
        return None, f"Erreur: {str(e)}"
    finally:
        conn.close()


def update_synonym(synonym_id: int, synonym: str) -> Tuple[bool, Optional[str]]:
    """
    Update a synonym.

    Returns:
        Tuple of (success, error_message)
    """
    if not synonym or not synonym.strip():
        return False, "Le synonyme est requis."

    synonym = synonym.strip()
    synonym_norm = normalize_name(synonym)

    conn = get_plant_db()
    cursor = conn.cursor()

    try:
        # Get existing
        existing = cursor.execute(
            "SELECT * FROM plant_synonyms WHERE id = ?", (synonym_id,)
        ).fetchone()

        if not existing:
            return False, "Synonyme introuvable."

        # Check for duplicate (excluding current)
        dup = cursor.execute(
            "SELECT id FROM plant_synonyms WHERE synonym_norm = ? AND id != ?",
            (synonym_norm, synonym_id)
        ).fetchone()

        if dup:
            return False, "Ce synonyme est déjà utilisé."

        # Check if this matches a scientific name
        sci_match = cursor.execute(
            "SELECT scientific_name FROM plants WHERE scientific_name_norm = ?",
            (synonym_norm,)
        ).fetchone()

        if sci_match:
            return False, f"Ce nom est déjà un nom scientifique: {sci_match['scientific_name']}"

        cursor.execute(
            "UPDATE plant_synonyms SET synonym = ?, synonym_norm = ? WHERE id = ?",
            (synonym, synonym_norm, synonym_id)
        )

        conn.commit()
        return True, None

    except Exception as e:
        conn.rollback()
        return False, f"Erreur: {str(e)}"
    finally:
        conn.close()


def delete_synonym(synonym_id: int) -> Tuple[bool, Optional[str]]:
    """
    Delete a synonym.

    Returns:
        Tuple of (success, error_message)
    """
    conn = get_plant_db()
    cursor = conn.cursor()

    try:
        cursor.execute("DELETE FROM plant_synonyms WHERE id = ?", (synonym_id,))
        if cursor.rowcount == 0:
            return False, "Synonyme introuvable."

        conn.commit()
        return True, None

    except Exception as e:
        conn.rollback()
        return False, f"Erreur: {str(e)}"
    finally:
        conn.close()


# ========================================
# Search Function
# ========================================

def search_plants(query: str, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Search for plants across multiple fields.

    Search fields (in priority order):
    - Scientific names
    - Common names
    - Synonyms
    - Family
    - Default category

    Ranking:
    1) Exact match (normalized)
    2) Prefix match
    3) Substring match

    Args:
        query: Search query string
        limit: Maximum number of results

    Returns:
        List of match results with plant info
    """
    if not query or not query.strip():
        return []

    query_norm = normalize_name(query)
    if not query_norm:
        return []

    conn = get_plant_db()
    cursor = conn.cursor()

    try:
        results = []
        seen_plants = set()

        # Helper to add results without duplicates
        def add_results(rows, ranking):
            for row in rows:
                if row['id'] not in seen_plants:
                    results.append(_build_search_result(cursor, row, ranking))
                    seen_plants.add(row['id'])

        # ============ EXACT MATCHES ============

        # 1. Exact matches on scientific name
        exact_sci = cursor.execute("""
            SELECT p.*, 'scientific_name' as match_type, p.scientific_name as matched_name
            FROM plants p
            WHERE p.scientific_name_norm = ?
        """, (query_norm,)).fetchall()
        add_results(exact_sci, 'exact')

        # 2. Exact matches on common names
        exact_cn = cursor.execute("""
            SELECT p.*, 'common_name' as match_type, cn.common_name as matched_name
            FROM plants p
            JOIN plant_common_names cn ON p.id = cn.plant_id
            WHERE cn.common_name_norm = ?
        """, (query_norm,)).fetchall()
        add_results(exact_cn, 'exact')

        # 3. Exact matches on synonyms
        exact_syn = cursor.execute("""
            SELECT p.*, 'synonym' as match_type, s.synonym as matched_name
            FROM plants p
            JOIN plant_synonyms s ON p.id = s.plant_id
            WHERE s.synonym_norm = ?
        """, (query_norm,)).fetchall()
        add_results(exact_syn, 'exact')

        # 4. Exact matches on family (case-insensitive)
        exact_fam = cursor.execute("""
            SELECT p.*, 'family' as match_type, p.family as matched_name
            FROM plants p
            WHERE LOWER(p.family) = LOWER(?)
        """, (query.strip(),)).fetchall()
        add_results(exact_fam, 'exact')

        # 5. Exact matches on default_category (case-insensitive)
        exact_cat = cursor.execute("""
            SELECT p.*, 'category' as match_type, p.default_category as matched_name
            FROM plants p
            WHERE LOWER(p.default_category) = LOWER(?)
        """, (query.strip(),)).fetchall()
        add_results(exact_cat, 'exact')

        if len(results) >= limit:
            return results[:limit]

        # ============ PREFIX MATCHES ============

        # 6. Prefix matches on scientific name
        prefix_sci = cursor.execute("""
            SELECT p.*, 'scientific_name' as match_type, p.scientific_name as matched_name
            FROM plants p
            WHERE p.scientific_name_norm LIKE ? || '%'
            AND p.scientific_name_norm != ?
        """, (query_norm, query_norm)).fetchall()
        add_results(prefix_sci, 'prefix')

        # 7. Prefix matches on common names
        prefix_cn = cursor.execute("""
            SELECT p.*, 'common_name' as match_type, cn.common_name as matched_name
            FROM plants p
            JOIN plant_common_names cn ON p.id = cn.plant_id
            WHERE cn.common_name_norm LIKE ? || '%'
            AND cn.common_name_norm != ?
        """, (query_norm, query_norm)).fetchall()
        add_results(prefix_cn, 'prefix')

        # 8. Prefix matches on synonyms
        prefix_syn = cursor.execute("""
            SELECT p.*, 'synonym' as match_type, s.synonym as matched_name
            FROM plants p
            JOIN plant_synonyms s ON p.id = s.plant_id
            WHERE s.synonym_norm LIKE ? || '%'
            AND s.synonym_norm != ?
        """, (query_norm, query_norm)).fetchall()
        add_results(prefix_syn, 'prefix')

        # 9. Prefix matches on family
        prefix_fam = cursor.execute("""
            SELECT p.*, 'family' as match_type, p.family as matched_name
            FROM plants p
            WHERE LOWER(p.family) LIKE LOWER(?) || '%'
            AND LOWER(p.family) != LOWER(?)
        """, (query.strip(), query.strip())).fetchall()
        add_results(prefix_fam, 'prefix')

        # 10. Prefix matches on default_category
        prefix_cat = cursor.execute("""
            SELECT p.*, 'category' as match_type, p.default_category as matched_name
            FROM plants p
            WHERE LOWER(p.default_category) LIKE LOWER(?) || '%'
            AND LOWER(p.default_category) != LOWER(?)
        """, (query.strip(), query.strip())).fetchall()
        add_results(prefix_cat, 'prefix')

        if len(results) >= limit:
            return results[:limit]

        # ============ SUBSTRING MATCHES ============

        # 11. Substring matches on scientific name
        substr_sci = cursor.execute("""
            SELECT p.*, 'scientific_name' as match_type, p.scientific_name as matched_name
            FROM plants p
            WHERE p.scientific_name_norm LIKE '%' || ? || '%'
            AND p.scientific_name_norm NOT LIKE ? || '%'
        """, (query_norm, query_norm)).fetchall()
        add_results(substr_sci, 'substring')

        # 12. Substring matches on common names
        substr_cn = cursor.execute("""
            SELECT p.*, 'common_name' as match_type, cn.common_name as matched_name
            FROM plants p
            JOIN plant_common_names cn ON p.id = cn.plant_id
            WHERE cn.common_name_norm LIKE '%' || ? || '%'
            AND cn.common_name_norm NOT LIKE ? || '%'
        """, (query_norm, query_norm)).fetchall()
        add_results(substr_cn, 'substring')

        # 13. Substring matches on synonyms
        substr_syn = cursor.execute("""
            SELECT p.*, 'synonym' as match_type, s.synonym as matched_name
            FROM plants p
            JOIN plant_synonyms s ON p.id = s.plant_id
            WHERE s.synonym_norm LIKE '%' || ? || '%'
            AND s.synonym_norm NOT LIKE ? || '%'
        """, (query_norm, query_norm)).fetchall()
        add_results(substr_syn, 'substring')

        # 14. Substring matches on family
        substr_fam = cursor.execute("""
            SELECT p.*, 'family' as match_type, p.family as matched_name
            FROM plants p
            WHERE LOWER(p.family) LIKE '%' || LOWER(?) || '%'
            AND LOWER(p.family) NOT LIKE LOWER(?) || '%'
        """, (query.strip(), query.strip())).fetchall()
        add_results(substr_fam, 'substring')

        # 15. Substring matches on default_category
        substr_cat = cursor.execute("""
            SELECT p.*, 'category' as match_type, p.default_category as matched_name
            FROM plants p
            WHERE LOWER(p.default_category) LIKE '%' || LOWER(?) || '%'
            AND LOWER(p.default_category) NOT LIKE LOWER(?) || '%'
        """, (query.strip(), query.strip())).fetchall()
        add_results(substr_cat, 'substring')

        return results[:limit]

    finally:
        conn.close()


def _build_search_result(cursor, row, ranking: str) -> Dict[str, Any]:
    """Build a search result dict from a row."""
    # Get common names for this plant
    common_names = cursor.execute(
        "SELECT common_name, lang, is_preferred FROM plant_common_names WHERE plant_id = ?",
        (row['id'],)
    ).fetchall()

    # Find preferred name
    preferred_name = None
    for cn in common_names:
        if cn['is_preferred']:
            preferred_name = cn['common_name']
            break

    return {
        'plant_id': row['id'],
        'scientific_name': row['scientific_name'],
        'matched_name': row['matched_name'],
        'match_type': row['match_type'],
        'ranking': ranking,
        'family': row['family'],
        'default_category': row['default_category'],
        'preferred_name': preferred_name,
        'common_names': [{'name': cn['common_name'], 'lang': cn['lang']} for cn in common_names]
    }


def check_duplicate(name: str) -> Optional[Dict[str, Any]]:
    """
    Check if a name already exists as a scientific name, common name, or synonym.

    Args:
        name: Name to check

    Returns:
        Dict with info about the existing entry, or None if no duplicate
    """
    if not name or not name.strip():
        return None

    name_norm = normalize_name(name)

    conn = get_plant_db()
    cursor = conn.cursor()

    try:
        # Check scientific names
        sci = cursor.execute(
            "SELECT id, scientific_name FROM plants WHERE scientific_name_norm = ?",
            (name_norm,)
        ).fetchone()

        if sci:
            return {
                'type': 'scientific_name',
                'plant_id': sci['id'],
                'name': sci['scientific_name'],
                'message': f"Ce nom correspond au nom scientifique: {sci['scientific_name']}"
            }

        # Check common names
        cn = cursor.execute("""
            SELECT cn.id, cn.common_name, cn.plant_id, p.scientific_name
            FROM plant_common_names cn
            JOIN plants p ON cn.plant_id = p.id
            WHERE cn.common_name_norm = ?
        """, (name_norm,)).fetchone()

        if cn:
            return {
                'type': 'common_name',
                'plant_id': cn['plant_id'],
                'name': cn['common_name'],
                'scientific_name': cn['scientific_name'],
                'message': f"Ce nom correspond au nom commun '{cn['common_name']}' de {cn['scientific_name']}"
            }

        # Check synonyms
        syn = cursor.execute("""
            SELECT s.id, s.synonym, s.plant_id, p.scientific_name
            FROM plant_synonyms s
            JOIN plants p ON s.plant_id = p.id
            WHERE s.synonym_norm = ?
        """, (name_norm,)).fetchone()

        if syn:
            return {
                'type': 'synonym',
                'plant_id': syn['plant_id'],
                'name': syn['synonym'],
                'scientific_name': syn['scientific_name'],
                'message': f"Ce nom est un synonyme de: {syn['scientific_name']}"
            }

        return None

    finally:
        conn.close()


# ========================================
# JSON Export / Import
# ========================================

def export_plants_json() -> Dict[str, Any]:
    """
    Export the entire plant database as JSON.

    Returns:
        Dict with 'plants' key containing list of plant objects
    """
    conn = get_plant_db()
    cursor = conn.cursor()

    try:
        plants = cursor.execute("SELECT * FROM plants ORDER BY scientific_name").fetchall()

        result = []
        for plant in plants:
            # Get common names
            common_names = cursor.execute(
                "SELECT common_name, lang, is_preferred FROM plant_common_names WHERE plant_id = ? ORDER BY lang, common_name",
                (plant['id'],)
            ).fetchall()

            # Get synonyms
            synonyms = cursor.execute(
                "SELECT synonym FROM plant_synonyms WHERE plant_id = ? ORDER BY synonym",
                (plant['id'],)
            ).fetchall()

            result.append({
                'scientific_name': plant['scientific_name'],
                'base_species': plant['base_species'] if 'base_species' in plant.keys() else '',
                'infraspecific_detail': plant['infraspecific_detail'] if 'infraspecific_detail' in plant.keys() else '',
                'family': plant['family'],
                'default_category': plant['default_category'],
                'common_names': [
                    {
                        'name': cn['common_name'],
                        'lang': cn['lang'],
                        'is_preferred': bool(cn['is_preferred']) if 'is_preferred' in cn.keys() else False
                    }
                    for cn in common_names
                ],
                'synonyms': [s['synonym'] for s in synonyms]
            })

        return {'plants': result}

    finally:
        conn.close()


def import_plants_json(
    data: Dict[str, Any],
    mode: str = 'merge'
) -> Tuple[bool, str, Dict[str, int]]:
    """
    Import plants from JSON data.

    Args:
        data: JSON data with 'plants' key
        mode: 'merge' to add/update, 'replace' to clear and replace all

    Returns:
        Tuple of (success, message, stats)
        stats contains: added, updated, skipped, errors
    """
    if not data or 'plants' not in data:
        return False, "Format JSON invalide: clé 'plants' manquante.", {}

    plants_data = data['plants']
    if not isinstance(plants_data, list):
        return False, "Format JSON invalide: 'plants' doit être une liste.", {}

    stats = {'added': 0, 'updated': 0, 'skipped': 0, 'errors': 0}
    errors = []

    conn = get_plant_db()
    cursor = conn.cursor()

    try:
        if mode == 'replace':
            # Clear all existing data
            cursor.execute("DELETE FROM plant_synonyms")
            cursor.execute("DELETE FROM plant_common_names")
            cursor.execute("DELETE FROM plants")
            conn.commit()

        for plant_data in plants_data:
            if not isinstance(plant_data, dict):
                stats['errors'] += 1
                errors.append("Entrée invalide (pas un objet)")
                continue

            scientific_name = plant_data.get('scientific_name', '').strip()
            if not scientific_name:
                stats['errors'] += 1
                errors.append("Entrée sans nom scientifique")
                continue

            scientific_name_norm = normalize_name(scientific_name)
            family = plant_data.get('family', '')
            default_category = plant_data.get('default_category', '')
            common_names = plant_data.get('common_names', [])
            synonyms = plant_data.get('synonyms', [])

            # New fields for infraspecific taxa support
            base_species = plant_data.get('base_species', '').strip()
            infraspecific_detail = plant_data.get('infraspecific_detail', '').strip()
            # Default base_species to scientific_name if not provided
            if not base_species:
                base_species = scientific_name
            base_species_norm = normalize_name(base_species)

            # Check if plant exists
            existing = cursor.execute(
                "SELECT id FROM plants WHERE scientific_name_norm = ?",
                (scientific_name_norm,)
            ).fetchone()

            if existing:
                plant_id = existing['id']

                if mode == 'merge':
                    # Update existing plant
                    cursor.execute("""
                        UPDATE plants
                        SET family = COALESCE(NULLIF(?, ''), family),
                            default_category = COALESCE(NULLIF(?, ''), default_category),
                            base_species = COALESCE(NULLIF(?, ''), base_species),
                            base_species_norm = COALESCE(NULLIF(?, ''), base_species_norm),
                            infraspecific_detail = COALESCE(NULLIF(?, ''), infraspecific_detail),
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (family, default_category, base_species, base_species_norm,
                          infraspecific_detail, plant_id))
                    stats['updated'] += 1
                else:
                    stats['skipped'] += 1
                    continue
            else:
                # Insert new plant
                cursor.execute("""
                    INSERT INTO plants (scientific_name, scientific_name_norm, family, default_category,
                                       base_species, base_species_norm, infraspecific_detail)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (scientific_name, scientific_name_norm, family, default_category,
                      base_species, base_species_norm, infraspecific_detail))
                plant_id = cursor.lastrowid
                stats['added'] += 1

            # Process common names
            if isinstance(common_names, list):
                # Track preferred names by language to set first one as preferred if none specified
                preferred_set_by_lang = set()

                for cn in common_names:
                    if isinstance(cn, dict):
                        name = cn.get('name', '').strip()
                        lang = cn.get('lang', 'fr')
                        is_preferred = cn.get('is_preferred', False)
                    elif isinstance(cn, str):
                        name = cn.strip()
                        lang = 'fr'
                        is_preferred = False
                    else:
                        continue

                    if name:
                        name_norm = normalize_name(name)
                        # Auto-set first name in each language as preferred if not explicitly set
                        if not is_preferred and lang not in preferred_set_by_lang:
                            is_preferred = True
                        if is_preferred:
                            preferred_set_by_lang.add(lang)

                        try:
                            cursor.execute("""
                                INSERT OR IGNORE INTO plant_common_names
                                (plant_id, common_name, common_name_norm, lang, is_preferred)
                                VALUES (?, ?, ?, ?, ?)
                            """, (plant_id, name, name_norm, lang, 1 if is_preferred else 0))
                        except sqlite3.IntegrityError:
                            pass

            # Process synonyms
            if isinstance(synonyms, list):
                for syn in synonyms:
                    if isinstance(syn, str):
                        syn = syn.strip()
                        if syn:
                            syn_norm = normalize_name(syn)
                            try:
                                cursor.execute("""
                                    INSERT OR IGNORE INTO plant_synonyms
                                    (plant_id, synonym, synonym_norm)
                                    VALUES (?, ?, ?)
                                """, (plant_id, syn, syn_norm))
                            except sqlite3.IntegrityError:
                                pass

        conn.commit()

        message = f"Import terminé: {stats['added']} ajoutés, {stats['updated']} mis à jour, {stats['skipped']} ignorés"
        if stats['errors'] > 0:
            message += f", {stats['errors']} erreurs"

        return True, message, stats

    except Exception as e:
        conn.rollback()
        return False, f"Erreur lors de l'import: {str(e)}", stats
    finally:
        conn.close()


def get_plant_count() -> int:
    """Get the total number of plants in the database."""
    conn = get_plant_db()
    try:
        count = conn.execute("SELECT COUNT(*) FROM plants").fetchone()[0]
        return count
    finally:
        conn.close()


# ========================================
# Utility Functions for Crop Integration
# ========================================

def find_plant_by_name(name: str) -> Optional[Dict[str, Any]]:
    """
    Find a plant by any of its names (scientific, common, or synonym).

    Returns the first exact match found, or None.
    """
    results = search_plants(name, limit=1)
    if results and results[0]['ranking'] == 'exact':
        return get_plant(results[0]['plant_id'])
    return None


def get_plant_suggestions(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Get plant suggestions for autocomplete.

    Returns a simplified list suitable for UI autocomplete.
    """
    results = search_plants(query, limit=limit)
    return [
        {
            'plant_id': r['plant_id'],
            'scientific_name': r['scientific_name'],
            'display_name': r['matched_name'],
            'preferred_name': r.get('preferred_name'),
            'family': r['family'],
            'default_category': r['default_category'],
            'match_type': r['match_type']
        }
        for r in results
    ]


# ========================================
# Preferred Name and Species Lookup
# ========================================

def get_preferred_name(plant_id: int, lang: str = 'fr') -> Optional[str]:
    """
    Get the preferred display name for a plant in the given language.

    Falls back to:
    1. First common name in that language if no preferred is set
    2. Scientific name if no common names exist

    Args:
        plant_id: ID of the plant
        lang: Language code (default 'fr')

    Returns:
        The preferred name string, or None if plant not found
    """
    conn = get_plant_db()
    try:
        # First try preferred name in requested language
        result = conn.execute("""
            SELECT common_name FROM plant_common_names
            WHERE plant_id = ? AND lang = ? AND is_preferred = 1
        """, (plant_id, lang)).fetchone()

        if result:
            return result[0]

        # Fallback: first common name in that language
        result = conn.execute("""
            SELECT common_name FROM plant_common_names
            WHERE plant_id = ? AND lang = ?
            ORDER BY id LIMIT 1
        """, (plant_id, lang)).fetchone()

        if result:
            return result[0]

        # Final fallback: scientific name
        result = conn.execute(
            "SELECT scientific_name FROM plants WHERE id = ?", (plant_id,)
        ).fetchone()

        return result[0] if result else None

    finally:
        conn.close()


def set_preferred_name(common_name_id: int) -> Tuple[bool, Optional[str]]:
    """
    Set a common name as the preferred name for its plant and language.

    Automatically clears is_preferred on other names in the same language.

    Args:
        common_name_id: ID of the common name to set as preferred

    Returns:
        Tuple of (success, error_message)
    """
    conn = get_plant_db()
    cursor = conn.cursor()

    try:
        # Get the common name details
        cn = cursor.execute(
            "SELECT plant_id, lang FROM plant_common_names WHERE id = ?",
            (common_name_id,)
        ).fetchone()

        if not cn:
            return False, "Nom commun introuvable."

        # Clear is_preferred on other names in same language
        cursor.execute(
            "UPDATE plant_common_names SET is_preferred = 0 WHERE plant_id = ? AND lang = ?",
            (cn['plant_id'], cn['lang'])
        )

        # Set this one as preferred
        cursor.execute(
            "UPDATE plant_common_names SET is_preferred = 1 WHERE id = ?",
            (common_name_id,)
        )

        conn.commit()
        return True, None

    except Exception as e:
        conn.rollback()
        return False, f"Erreur: {str(e)}"
    finally:
        conn.close()


def get_plants_by_species(base_species: str) -> List[Dict[str, Any]]:
    """
    Get all plants that share the same base species.

    Useful for rotation logic to find related varieties/cultivars.

    Args:
        base_species: The base species name (e.g., "Capsicum annuum")

    Returns:
        List of plant dicts with id, scientific_name, infraspecific_detail
    """
    if not base_species:
        return []

    base_species_norm = normalize_name(base_species)
    conn = get_plant_db()

    try:
        plants = conn.execute("""
            SELECT id, scientific_name, infraspecific_detail, family, default_category
            FROM plants
            WHERE base_species_norm = ?
            ORDER BY scientific_name
        """, (base_species_norm,)).fetchall()

        return [dict(p) for p in plants]

    finally:
        conn.close()


def get_plants_by_family(family: str) -> List[Dict[str, Any]]:
    """
    Get all plants in a botanical family.

    Useful for rotation logic to find plants that should not follow each other.

    Args:
        family: The botanical family name (e.g., "Solanaceae")

    Returns:
        List of plant dicts with id, scientific_name, base_species
    """
    if not family:
        return []

    conn = get_plant_db()

    try:
        plants = conn.execute("""
            SELECT id, scientific_name, base_species, infraspecific_detail, default_category
            FROM plants
            WHERE family = ?
            ORDER BY scientific_name
        """, (family,)).fetchall()

        return [dict(p) for p in plants]

    finally:
        conn.close()


def get_rotation_groups() -> Dict[str, Any]:
    """
    Get all plants organized by family and species for rotation planning.

    Returns a structure like:
    {
        'by_family': {
            'Solanaceae': [plant_ids...],
            'Brassicaceae': [plant_ids...],
        },
        'by_species': {
            'capsicum annuum': [plant_ids...],
            'brassica oleracea': [plant_ids...],
        }
    }
    """
    conn = get_plant_db()

    try:
        plants = conn.execute("""
            SELECT id, family, base_species_norm
            FROM plants
            WHERE family != '' OR base_species_norm != ''
        """).fetchall()

        by_family: Dict[str, List[int]] = {}
        by_species: Dict[str, List[int]] = {}

        for p in plants:
            plant_id = p['id']

            if p['family']:
                if p['family'] not in by_family:
                    by_family[p['family']] = []
                by_family[p['family']].append(plant_id)

            if p['base_species_norm']:
                if p['base_species_norm'] not in by_species:
                    by_species[p['base_species_norm']] = []
                by_species[p['base_species_norm']].append(plant_id)

        return {
            'by_family': by_family,
            'by_species': by_species
        }

    finally:
        conn.close()
