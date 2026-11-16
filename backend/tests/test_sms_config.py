"""Server secret configuration only; no provider, database or network calls."""
from dataclasses import asdict
from unittest.mock import patch
from backend.app.config import Settings


def test_melipayamak_key_is_optional_and_hidden_from_diagnostics():
    with patch.dict('os.environ', {}, clear=True):
        assert Settings().melipayamak_api_key.get_secret_value() == ''
    fixture = 'offline-fixture-key-never-send'
    with patch.dict('os.environ', {'MELIPAYAMAK_API_KEY': fixture}, clear=True):
        settings = Settings()
    assert settings.melipayamak_api_key.get_secret_value() == fixture
    assert fixture not in repr(settings)
    assert fixture not in str(asdict(settings))
    assert fixture not in str(settings.melipayamak_api_key)
