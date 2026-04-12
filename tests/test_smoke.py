from pathlib import Path


def test_package_exports_version():
    import paperlab

    assert paperlab.__version__ == "0.2.1"


def test_runtime_dependencies_are_declared():
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")

    assert 'openai>=1.0' in text
    assert 'requests>=2.28' in text
    assert 'PyMuPDF' in text
    assert 'deepxiv-sdk' in text
