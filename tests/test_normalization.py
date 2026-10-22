import pytest
from ingestion.normalization import normalize_unit

def test_normalize_unit_noop():
    assert normalize_unit("13.5", "g/dL") == ("13.5", "g/dL")

def test_normalize_unit_gl_to_gdl():
    assert normalize_unit("135", "g/L") == ("13.5", "g/dL")
    assert normalize_unit("140", "gram/liter") == ("14.0", "g/dL")

def test_normalize_unit_temp():
    assert normalize_unit("98.6", "degF") == ("37.0", "Cel")
    assert normalize_unit("100.4", "F") == ("38.0", "Cel")

def test_normalize_unit_invalid():
    assert normalize_unit("abc", "g/L") == ("abc", "g/L")
    assert normalize_unit(None, None) == (None, None)
