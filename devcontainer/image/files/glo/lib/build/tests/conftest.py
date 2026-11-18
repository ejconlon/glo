"""Own and clean private temporary files for this test suite."""

from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest


@pytest.fixture
def tmp_path() -> Iterator[Path]:
    """Remove each test's private files on success or failure."""
    with TemporaryDirectory(prefix="vp-glo-build-test-") as directory:
        yield Path(directory)
