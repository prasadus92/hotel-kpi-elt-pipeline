"""Tests for the export/serve helpers."""

from pipeline import export


def test_output_filename_matches_contract():
    assert (
        export.output_filename("1035", "2026-05-01", "2026-05-31")
        == "kpi_1035_2026_05_01_to_2026_05_31.csv"
    )


def test_output_filename_other_hotel_and_range():
    assert (
        export.output_filename("1036", "2026-04-01", "2026-04-30")
        == "kpi_1036_2026_04_01_to_2026_04_30.csv"
    )
