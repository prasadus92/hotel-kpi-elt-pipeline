"""Tests for the CLI argument parsing and validation."""

import argparse

import pytest

import run_pipeline


def test_defaults_reproduce_the_headline_deliverable():
    args = run_pipeline.parse_args([])
    assert args.hotel_id == "1035"
    assert args.from_date == "2026-05-01"
    assert args.to_date == "2026-05-31"


def test_custom_arguments_are_parsed():
    args = run_pipeline.parse_args(
        ["--hotel-id", "1036", "--from-date", "2026-04-01", "--to-date", "2026-04-30"]
    )
    assert args.hotel_id == "1036"
    assert args.from_date == "2026-04-01"
    assert args.to_date == "2026-04-30"


def test_invalid_date_is_rejected():
    with pytest.raises(argparse.ArgumentTypeError):
        run_pipeline._valid_date("2026-13-01")


def test_from_after_to_is_rejected():
    with pytest.raises(SystemExit):
        run_pipeline.parse_args(["--from-date", "2026-05-31", "--to-date", "2026-05-01"])
