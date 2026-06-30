"""Session-scoped pytest fixtures that generate .docx test files on the fly."""
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from tests.fixtures.make_fixtures import make_verbatim, make_generic, make_malformed


@pytest.fixture(scope="session")
def verbatim_docx(tmp_path_factory):
    path = tmp_path_factory.mktemp("fixtures") / "verbatim_sample.docx"
    make_verbatim(path)
    return path


@pytest.fixture(scope="session")
def generic_docx(tmp_path_factory):
    path = tmp_path_factory.mktemp("fixtures") / "generic_sample.docx"
    make_generic(path)
    return path


@pytest.fixture(scope="session")
def malformed_docx(tmp_path_factory):
    path = tmp_path_factory.mktemp("fixtures") / "malformed_sample.docx"
    make_malformed(path)
    return path
