from __future__ import annotations

import pytest

from app.config import Settings

PRODUCTION = {
    "ENVIRONMENT": "production",
    "DATABASE_URL": "postgresql+psycopg://allocator:secret@db:5432/allocator",
    "SMARTTT_BASE_URL": "https://api.nextup.co.ke",
    "SMARTTT_API_KEY": "s" * 48,
    "GENERATOR_BASE_URL": "https://generator.example",
    "GENERATOR_API_KEY": "g" * 48,
    "COOKIE_SECURE": "true",
}


def test_production_starts_with_everything_set(monkeypatch):
    for name, value in PRODUCTION.items():
        monkeypatch.setenv(name, value)
    assert Settings(_env_file=None).generator_base_url == "https://generator.example"  # type: ignore[call-arg]


@pytest.mark.parametrize(
    "unset", ["GENERATOR_API_KEY", "GENERATOR_BASE_URL", "SMARTTT_BASE_URL", "DATABASE_URL"]
)
def test_production_refuses_to_start_without(monkeypatch, unset):
    for name, value in PRODUCTION.items():
        if name != unset:
            monkeypatch.setenv(name, value)
    monkeypatch.delenv(unset, raising=False)
    with pytest.raises(ValueError, match=unset):
        Settings(_env_file=None)  # type: ignore[call-arg]
