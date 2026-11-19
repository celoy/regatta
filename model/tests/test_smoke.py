"""Phase 0 smoke test: the package and its only dependency import."""

import numpy as np

import regatta_model


def test_package_imports() -> None:
    assert regatta_model.__version__ == "0.0.0"


def test_numpy_available() -> None:
    assert np.isclose(np.sin(np.pi / 2), 1.0)
