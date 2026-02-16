"""
tests/test_plant_database.py — Tests for the plant database module.

Tests cover:
- Normalization function
- Plant CRUD operations
- Search ranking
- Duplicate detection
- JSON import/export
"""

import pytest
import os
import tempfile
import json

# Import the plant database module
from plant_database import (
    normalize_name,
    init_plant_db,
    get_plant_db,
    create_plant,
    get_plant,
    get_all_plants,
    update_plant,
    delete_plant,
    add_common_name,
    delete_common_name,
    add_synonym,
    delete_synonym,
    search_plants,
    check_duplicate,
    export_plants_json,
    import_plants_json,
    get_plant_count
)


@pytest.fixture
def temp_plant_db(monkeypatch):
    """Create a temporary plant database for testing."""
    db_fd, db_path = tempfile.mkstemp(suffix='.db')

    # Monkeypatch the database path
    monkeypatch.setenv('PLANT_DB_PATH', db_path)

    # Re-import to pick up new path (or use direct path function)
    from plant_database import get_plant_db_path
    assert get_plant_db_path() == db_path

    # Initialize the database
    init_plant_db()

    yield db_path

    # Cleanup
    os.close(db_fd)
    try:
        os.unlink(db_path)
    except PermissionError:
        pass  # Windows may hold the file


# ========================================
# Normalization Tests
# ========================================

class TestNormalization:
    """Tests for the normalize_name function."""

    def test_basic_lowercase(self):
        assert normalize_name("TOMATO") == "tomato"
        assert normalize_name("Solanum Lycopersicum") == "solanum lycopersicum"

    def test_trim_whitespace(self):
        assert normalize_name("  tomato  ") == "tomato"
        assert normalize_name("\ttomato\n") == "tomato"

    def test_collapse_whitespace(self):
        assert normalize_name("tomato   rouge") == "tomato rouge"
        assert normalize_name("solanum   lycopersicum   var") == "solanum lycopersicum var"

    def test_remove_diacritics(self):
        assert normalize_name("Épinard") == "epinard"
        assert normalize_name("café") == "cafe"
        assert normalize_name("niébé") == "niebe"
        assert normalize_name("maïs") == "mais"

    def test_remove_hyphens_punctuation(self):
        assert normalize_name("haricot-vert") == "haricot vert"
        assert normalize_name("Brassica oleracea var. capitata") == "brassica oleracea var capitata"
        assert normalize_name("tomate (rouge)") == "tomate rouge"

    def test_empty_string(self):
        assert normalize_name("") == ""
        assert normalize_name(None) == ""

    def test_combined(self):
        assert normalize_name("  Épinard-Rouge  ") == "epinard rouge"
        assert normalize_name("BRASSICA OLERACEA") == "brassica oleracea"


# ========================================
# Plant CRUD Tests
# ========================================

class TestPlantCRUD:
    """Tests for plant CRUD operations."""

    def test_create_plant_basic(self, temp_plant_db):
        plant_id, error = create_plant("Solanum lycopersicum", "Solanacées", "Fruit")
        assert plant_id is not None
        assert error is None

    def test_create_plant_with_common_names(self, temp_plant_db):
        plant_id, error = create_plant(
            "Solanum lycopersicum",
            "Solanacées",
            "Fruit",
            common_names=[
                {"name": "Tomate", "lang": "fr"},
                {"name": "Tomato", "lang": "en"}
            ]
        )
        assert plant_id is not None

        plant = get_plant(plant_id)
        assert plant is not None
        assert len(plant['common_names']) == 2

    def test_create_plant_with_synonyms(self, temp_plant_db):
        plant_id, error = create_plant(
            "Solanum lycopersicum",
            "Solanacées",
            "Fruit",
            synonyms=["Lycopersicon esculentum", "Lycopersicon lycopersicum"]
        )
        assert plant_id is not None

        plant = get_plant(plant_id)
        assert len(plant['synonyms']) == 2

    def test_create_plant_duplicate(self, temp_plant_db):
        plant_id1, _ = create_plant("Solanum lycopersicum")
        plant_id2, error = create_plant("Solanum lycopersicum")

        assert plant_id1 is not None
        assert plant_id2 is None
        assert "existe déjà" in error

    def test_create_plant_normalized_duplicate(self, temp_plant_db):
        """Test that normalized names are used for duplicate detection."""
        plant_id1, _ = create_plant("Solanum Lycopersicum")
        plant_id2, error = create_plant("SOLANUM LYCOPERSICUM")

        assert plant_id1 is not None
        assert plant_id2 is None

    def test_get_plant(self, temp_plant_db):
        plant_id, _ = create_plant("Brassica oleracea", "Brassicacées", "Feuille")

        plant = get_plant(plant_id)
        assert plant is not None
        assert plant['scientific_name'] == "Brassica oleracea"
        assert plant['family'] == "Brassicacées"

    def test_get_plant_not_found(self, temp_plant_db):
        plant = get_plant(9999)
        assert plant is None

    def test_get_all_plants(self, temp_plant_db):
        create_plant("Plant A")
        create_plant("Plant B")
        create_plant("Plant C")

        plants = get_all_plants()
        assert len(plants) == 3

    def test_update_plant(self, temp_plant_db):
        plant_id, _ = create_plant("Solanum lycopersicum")

        success, error = update_plant(plant_id, family="Solanacées", default_category="Fruit")
        assert success

        plant = get_plant(plant_id)
        assert plant['family'] == "Solanacées"
        assert plant['default_category'] == "Fruit"

    def test_update_plant_scientific_name(self, temp_plant_db):
        plant_id, _ = create_plant("Old Name")

        success, _ = update_plant(plant_id, scientific_name="New Name")
        assert success

        plant = get_plant(plant_id)
        assert plant['scientific_name'] == "New Name"

    def test_delete_plant(self, temp_plant_db):
        plant_id, _ = create_plant("To Delete")

        success, _ = delete_plant(plant_id)
        assert success

        plant = get_plant(plant_id)
        assert plant is None


# ========================================
# Common Names Tests
# ========================================

class TestCommonNames:
    """Tests for common names CRUD."""

    def test_add_common_name(self, temp_plant_db):
        plant_id, _ = create_plant("Solanum lycopersicum")

        cn_id, error = add_common_name(plant_id, "Tomate", "fr")
        assert cn_id is not None
        assert error is None

        plant = get_plant(plant_id)
        assert len(plant['common_names']) == 1
        assert plant['common_names'][0]['name'] == "Tomate"

    def test_add_duplicate_common_name(self, temp_plant_db):
        plant_id, _ = create_plant("Solanum lycopersicum")

        add_common_name(plant_id, "Tomate", "fr")
        cn_id, error = add_common_name(plant_id, "TOMATE", "fr")  # Normalized same

        assert cn_id is None
        assert "existe déjà" in error

    def test_delete_common_name(self, temp_plant_db):
        plant_id, _ = create_plant("Solanum lycopersicum")
        cn_id, _ = add_common_name(plant_id, "Tomate", "fr")

        success, _ = delete_common_name(cn_id)
        assert success

        plant = get_plant(plant_id)
        assert len(plant['common_names']) == 0


# ========================================
# Synonyms Tests
# ========================================

class TestSynonyms:
    """Tests for synonyms CRUD."""

    def test_add_synonym(self, temp_plant_db):
        plant_id, _ = create_plant("Solanum lycopersicum")

        syn_id, error = add_synonym(plant_id, "Lycopersicon esculentum")
        assert syn_id is not None
        assert error is None

    def test_add_duplicate_synonym(self, temp_plant_db):
        plant_id, _ = create_plant("Solanum lycopersicum")

        add_synonym(plant_id, "Lycopersicon esculentum")
        syn_id, error = add_synonym(plant_id, "Lycopersicon esculentum")

        assert syn_id is None
        assert "déjà utilisé" in error

    def test_synonym_conflicts_with_scientific_name(self, temp_plant_db):
        create_plant("Solanum lycopersicum")
        plant_id2, _ = create_plant("Another Plant")

        syn_id, error = add_synonym(plant_id2, "Solanum lycopersicum")

        assert syn_id is None
        assert "nom scientifique" in error


# ========================================
# Search Tests
# ========================================

class TestSearch:
    """Tests for search functionality."""

    def test_search_by_scientific_name(self, temp_plant_db):
        create_plant("Solanum lycopersicum")

        results = search_plants("Solanum")
        assert len(results) >= 1
        assert results[0]['scientific_name'] == "Solanum lycopersicum"

    def test_search_by_common_name(self, temp_plant_db):
        plant_id, _ = create_plant("Solanum lycopersicum")
        add_common_name(plant_id, "Tomate", "fr")

        results = search_plants("Tomate")
        assert len(results) >= 1
        assert results[0]['match_type'] == 'common_name'

    def test_search_by_synonym(self, temp_plant_db):
        plant_id, _ = create_plant("Solanum lycopersicum")
        add_synonym(plant_id, "Lycopersicon esculentum")

        results = search_plants("Lycopersicon")
        assert len(results) >= 1
        assert results[0]['match_type'] == 'synonym'

    def test_search_ranking_exact_first(self, temp_plant_db):
        create_plant("Tomate")  # Exact match as scientific name
        plant_id2, _ = create_plant("Solanum lycopersicum")
        add_common_name(plant_id2, "Tomate rouge", "fr")

        results = search_plants("tomate")
        assert len(results) >= 1
        # Exact match should be first
        assert results[0]['ranking'] == 'exact'

    def test_search_empty_query(self, temp_plant_db):
        results = search_plants("")
        assert len(results) == 0

    def test_search_no_results(self, temp_plant_db):
        create_plant("Solanum lycopersicum")

        results = search_plants("xyz123nonexistent")
        assert len(results) == 0


# ========================================
# Duplicate Detection Tests
# ========================================

class TestDuplicateDetection:
    """Tests for check_duplicate function."""

    def test_check_duplicate_scientific_name(self, temp_plant_db):
        create_plant("Solanum lycopersicum")

        result = check_duplicate("Solanum lycopersicum")
        assert result is not None
        assert result['type'] == 'scientific_name'

    def test_check_duplicate_common_name(self, temp_plant_db):
        plant_id, _ = create_plant("Solanum lycopersicum")
        add_common_name(plant_id, "Tomate", "fr")

        result = check_duplicate("Tomate")
        assert result is not None
        assert result['type'] == 'common_name'

    def test_check_duplicate_synonym(self, temp_plant_db):
        plant_id, _ = create_plant("Solanum lycopersicum")
        add_synonym(plant_id, "Lycopersicon esculentum")

        result = check_duplicate("Lycopersicon esculentum")
        assert result is not None
        assert result['type'] == 'synonym'

    def test_check_no_duplicate(self, temp_plant_db):
        result = check_duplicate("Completely New Name")
        assert result is None


# ========================================
# JSON Export/Import Tests
# ========================================

class TestJSONExportImport:
    """Tests for JSON export and import functionality."""

    def test_export_plants(self, temp_plant_db):
        plant_id, _ = create_plant(
            "Solanum lycopersicum",
            "Solanacées",
            "Fruit",
            common_names=[{"name": "Tomate", "lang": "fr"}],
            synonyms=["Lycopersicon esculentum"]
        )

        data = export_plants_json()

        assert 'plants' in data
        assert len(data['plants']) == 1
        assert data['plants'][0]['scientific_name'] == "Solanum lycopersicum"
        assert len(data['plants'][0]['common_names']) == 1
        assert len(data['plants'][0]['synonyms']) == 1

    def test_import_plants_merge(self, temp_plant_db):
        # Create an existing plant
        create_plant("Existing Plant", "Family A")

        # Import new plants
        import_data = {
            "plants": [
                {
                    "scientific_name": "New Plant 1",
                    "family": "Family B",
                    "default_category": "Feuille"
                },
                {
                    "scientific_name": "New Plant 2",
                    "family": "Family C"
                }
            ]
        }

        success, message, stats = import_plants_json(import_data, mode='merge')

        assert success
        assert stats['added'] == 2
        assert get_plant_count() == 3

    def test_import_plants_replace(self, temp_plant_db):
        # Create existing plants
        create_plant("Plant 1")
        create_plant("Plant 2")

        # Replace with new data
        import_data = {
            "plants": [
                {"scientific_name": "New Plant Only"}
            ]
        }

        success, message, stats = import_plants_json(import_data, mode='replace')

        assert success
        assert get_plant_count() == 1

    def test_import_plants_merge_updates_existing(self, temp_plant_db):
        # Create plant without family
        create_plant("Test Plant")

        # Import with family
        import_data = {
            "plants": [
                {
                    "scientific_name": "Test Plant",
                    "family": "New Family"
                }
            ]
        }

        success, _, stats = import_plants_json(import_data, mode='merge')

        assert success
        assert stats['updated'] == 1

        # Verify family was updated
        plants = get_all_plants()
        assert plants[0]['family'] == "New Family"

    def test_import_invalid_json(self, temp_plant_db):
        success, message, stats = import_plants_json({}, mode='merge')

        assert not success
        assert "plants" in message.lower()

    def test_roundtrip_export_import(self, temp_plant_db):
        """Test that exporting and importing preserves data."""
        # Create initial data
        plant_id, _ = create_plant(
            "Solanum lycopersicum",
            "Solanacées",
            "Fruit",
            common_names=[{"name": "Tomate", "lang": "fr"}, {"name": "Tomato", "lang": "en"}],
            synonyms=["Lycopersicon esculentum"]
        )

        # Export
        exported = export_plants_json()

        # Clear and re-import
        success, _, _ = import_plants_json(exported, mode='replace')
        assert success

        # Verify
        plants = get_all_plants()
        assert len(plants) == 1

        plant = get_plant(plants[0]['id'])
        assert plant['scientific_name'] == "Solanum lycopersicum"
        assert plant['family'] == "Solanacées"
        assert len(plant['common_names']) == 2
        assert len(plant['synonyms']) == 1
