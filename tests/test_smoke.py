"""Smoke tests for the FLP plugin scaffold."""

from flp_plugin import FLPEffect


def test_flp_package_imports():
    assert FLPEffect is not None
