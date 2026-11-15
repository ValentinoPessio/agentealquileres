import pytest


@pytest.fixture(autouse=True)
def _db_conversaciones_temporal(tmp_path, monkeypatch):
    """Ningún test escribe en data/conversaciones.sqlite real."""
    monkeypatch.setenv("CONVERSACIONES_DB", str(tmp_path / "conv.sqlite"))
