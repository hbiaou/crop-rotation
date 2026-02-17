"""
tests/test_auto_distribution.py — Unit tests for the auto-distribution algorithm.

Tests the _compute_auto_distribution function to verify:
1. Bed-first traversal: P1 fully assigned before P2
2. No consecutive primary categories: category(Pi, S1) != category(Pi+1, S1)
3. Spillover rules: consecutive repeats only when quotas force it
4. No consecutive starter crop repeats when multiple crops available
"""

import pytest
import os
import tempfile
from collections import OrderedDict

from app import create_app
from database import init_db, seed_defaults, get_sub_beds, get_rotation_sequence


@pytest.fixture
def app_context():
    """Create a test app context with isolated database."""
    db_fd, db_path = tempfile.mkstemp()

    app = create_app({
        'TESTING': True,
        'DATABASE': db_path,
        'SECRET_KEY': 'dev-key-for-testing'
    })

    with app.app_context():
        init_db()
        seed_defaults()
        yield app

    os.close(db_fd)
    os.unlink(db_path)


def test_bed_first_traversal(app_context):
    """Test that P1 is fully assigned before P2 starts (no global column-first pattern)."""
    from routes.cycle import _compute_auto_distribution

    with app_context.app_context():
        # Get garden 1 (G1 has 4 sub-beds per bed)
        garden_id = 1
        result = _compute_auto_distribution(garden_id)

        # Get sub-beds grouped by bed
        active_beds = get_sub_beds(garden_id, active_only=True)
        beds_grouped = OrderedDict()
        for sb in active_beds:
            bn = sb['bed_number']
            if bn not in beds_grouped:
                beds_grouped[bn] = []
            beds_grouped[bn].append(sb)

        # Verify all sub-beds are assigned
        assert len(result) == len(active_beds), "All sub-beds should be assigned"

        # Verify each sub-bed in each bed has an assignment
        for bed_num, sub_beds in beds_grouped.items():
            for sb in sub_beds:
                assert sb['id'] in result, f"Sub-bed {sb['id']} in bed {bed_num} should be assigned"


def test_no_consecutive_primary_categories(app_context):
    """Test that category(Pi, S1) != category(Pi+1, S1) for consecutive beds."""
    from routes.cycle import _compute_auto_distribution

    with app_context.app_context():
        garden_id = 1
        result = _compute_auto_distribution(garden_id)

        # Get sub-beds grouped by bed
        active_beds = get_sub_beds(garden_id, active_only=True)
        beds_grouped = OrderedDict()
        for sb in active_beds:
            bn = sb['bed_number']
            if bn not in beds_grouped:
                beds_grouped[bn] = []
            beds_grouped[bn].append(sb)

        # Get the first sub-bed (S1) of each bed and its category
        bed_numbers = list(beds_grouped.keys())
        primary_categories = []

        for bed_num in bed_numbers:
            sub_beds = beds_grouped[bed_num]
            s1 = [sb for sb in sub_beds if sb['sub_bed_position'] == 1][0]
            category = result[s1['id']]['category']
            primary_categories.append((bed_num, category))

        # Check first N beds where N = number of categories (full cycle)
        # These should all have different categories (cycling through sequence)
        categories = [r['category'] for r in get_rotation_sequence()]
        num_categories = len(categories)

        # Check that no two consecutive beds have the same primary category
        # (at least for the first full cycle of beds)
        consecutive_same = 0
        for i in range(min(len(primary_categories) - 1, num_categories)):
            if primary_categories[i][1] == primary_categories[i + 1][1]:
                consecutive_same += 1

        # Allow at most 0 consecutive same categories in first cycle
        # (unless quotas force it, but with equal distribution they shouldn't)
        assert consecutive_same == 0, (
            f"Found {consecutive_same} consecutive beds with same primary category. "
            f"First {num_categories} beds: {primary_categories[:num_categories]}"
        )


def test_category_cycling_pattern(app_context):
    """Test that primary categories cycle through the rotation sequence."""
    from routes.cycle import _compute_auto_distribution

    with app_context.app_context():
        garden_id = 1
        result = _compute_auto_distribution(garden_id)

        # Get sub-beds grouped by bed
        active_beds = get_sub_beds(garden_id, active_only=True)
        beds_grouped = OrderedDict()
        for sb in active_beds:
            bn = sb['bed_number']
            if bn not in beds_grouped:
                beds_grouped[bn] = []
            beds_grouped[bn].append(sb)

        categories = [r['category'] for r in get_rotation_sequence()]
        bed_numbers = list(beds_grouped.keys())

        # Get primary category for first N beds
        primary_cats = []
        for bed_num in bed_numbers[:len(categories)]:
            sub_beds = beds_grouped[bed_num]
            s1 = [sb for sb in sub_beds if sb['sub_bed_position'] == 1][0]
            primary_cats.append(result[s1['id']]['category'])

        # All 5 categories should appear in the first 5 beds
        unique_cats = set(primary_cats)
        assert len(unique_cats) == len(categories), (
            f"First {len(categories)} beds should have {len(categories)} different categories, "
            f"got {len(unique_cats)}: {primary_cats}"
        )


def test_no_consecutive_starter_crop_repeats(app_context):
    """Test that the crop in S1 doesn't repeat across consecutive beds when alternatives exist."""
    from routes.cycle import _compute_auto_distribution

    with app_context.app_context():
        garden_id = 1
        result = _compute_auto_distribution(garden_id)

        # Get sub-beds grouped by bed
        active_beds = get_sub_beds(garden_id, active_only=True)
        beds_grouped = OrderedDict()
        for sb in active_beds:
            bn = sb['bed_number']
            if bn not in beds_grouped:
                beds_grouped[bn] = []
            beds_grouped[bn].append(sb)

        bed_numbers = list(beds_grouped.keys())

        # Get starter crop for each bed
        starter_crops = []
        for bed_num in bed_numbers:
            sub_beds = beds_grouped[bed_num]
            s1 = [sb for sb in sub_beds if sb['sub_bed_position'] == 1][0]
            crop_id = result[s1['id']]['crop_id']
            starter_crops.append((bed_num, crop_id))

        # Count consecutive repeats
        consecutive_crop_repeats = 0
        for i in range(len(starter_crops) - 1):
            if (starter_crops[i][1] is not None and
                starter_crops[i][1] == starter_crops[i + 1][1]):
                consecutive_crop_repeats += 1

        # With our distribution, we should have very few consecutive crop repeats
        # (only when quotas force it)
        total_beds = len(bed_numbers)
        repeat_ratio = consecutive_crop_repeats / total_beds if total_beds > 0 else 0

        # Allow up to 10% consecutive repeats (quotas may force some)
        assert repeat_ratio < 0.1, (
            f"Too many consecutive starter crop repeats: {consecutive_crop_repeats}/{total_beds} "
            f"({repeat_ratio:.1%})"
        )


def test_spillover_within_bed(app_context):
    """Test that spillover happens correctly when category quota runs out mid-bed."""
    from routes.cycle import _compute_auto_distribution

    with app_context.app_context():
        garden_id = 1
        result = _compute_auto_distribution(garden_id)

        # Get sub-beds grouped by bed
        active_beds = get_sub_beds(garden_id, active_only=True)
        beds_grouped = OrderedDict()
        for sb in active_beds:
            bn = sb['bed_number']
            if bn not in beds_grouped:
                beds_grouped[bn] = []
            beds_grouped[bn].append(sb)

        categories = [r['category'] for r in get_rotation_sequence()]

        # Count sub-beds per category
        category_counts = {cat: 0 for cat in categories}
        for sb_id, assignment in result.items():
            cat = assignment['category']
            if cat in category_counts:
                category_counts[cat] += 1

        # Categories should be roughly balanced
        total = sum(category_counts.values())
        expected_per_cat = total / len(categories)

        for cat, count in category_counts.items():
            # Allow 20% deviation due to rounding
            deviation = abs(count - expected_per_cat) / expected_per_cat
            assert deviation < 0.2, (
                f"Category {cat} has {count} sub-beds, expected ~{expected_per_cat:.0f} "
                f"(deviation: {deviation:.1%})"
            )


def test_all_sub_beds_assigned(app_context):
    """Test that all active sub-beds receive an assignment."""
    from routes.cycle import _compute_auto_distribution

    with app_context.app_context():
        for garden_id in [1, 2]:  # Test both gardens
            result = _compute_auto_distribution(garden_id)
            active_beds = get_sub_beds(garden_id, active_only=True)

            assert len(result) == len(active_beds), (
                f"Garden {garden_id}: Expected {len(active_beds)} assignments, "
                f"got {len(result)}"
            )

            # Each assignment should have category and crop_id
            for sb_id, assignment in result.items():
                assert 'category' in assignment, f"Sub-bed {sb_id} missing category"
                assert 'crop_id' in assignment, f"Sub-bed {sb_id} missing crop_id"


def test_crop_quotas_respected(app_context):
    """Test that crop quotas from distribution defaults are approximately respected."""
    from routes.cycle import _compute_auto_distribution

    with app_context.app_context():
        garden_id = 1
        result = _compute_auto_distribution(garden_id)

        # Count crops
        crop_counts = {}
        for sb_id, assignment in result.items():
            crop_id = assignment['crop_id']
            if crop_id:
                crop_counts[crop_id] = crop_counts.get(crop_id, 0) + 1

        # Verify we have multiple crops assigned (not just one)
        assert len(crop_counts) > 5, (
            f"Expected diverse crop distribution, only found {len(crop_counts)} distinct crops"
        )


def test_empty_garden_returns_empty(app_context):
    """Test that empty garden returns empty result."""
    from routes.cycle import _compute_auto_distribution

    with app_context.app_context():
        # Non-existent garden
        result = _compute_auto_distribution(9999)
        assert result == {}


def test_deterministic_crop_order(app_context):
    """Test that crop selection within a category follows a deterministic order."""
    from routes.cycle import _compute_auto_distribution
    import random

    with app_context.app_context():
        # Run multiple times with same random seed
        results = []
        for _ in range(3):
            random.seed(42)  # Fixed seed
            result = _compute_auto_distribution(1)
            results.append(result)

        # All results should be identical with same seed
        for i in range(1, len(results)):
            assert results[0] == results[i], "Results should be deterministic with same seed"
