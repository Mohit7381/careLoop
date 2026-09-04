"""The sphere token has three names in the wild (SPHERE_APP_TOKEN in shells,
SPHERE_PLATFORM_APP_TOKEN in older .env files, SPHERE_PLATFORM_API_KEY in
.env.example). All must work, and an EMPTY placeholder for one name must not
shadow a real value under another — run 25 on main went out with "" and got
HTTP 401 because `.env` had `SPHERE_PLATFORM_API_KEY=` above a real
SPHERE_PLATFORM_APP_TOKEN."""
import pytest

from app.config import get_settings
from app.integrations import sphere


@pytest.fixture(autouse=True)
def _clean(monkeypatch, tmp_path):
    for k in ("SPHERE_APP_TOKEN", "SPHERE_PLATFORM_APP_TOKEN", "SPHERE_PLATFORM_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.chdir(tmp_path)               # no real .env in reach
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_old_env_name_still_works(monkeypatch):
    monkeypatch.setenv("SPHERE_PLATFORM_APP_TOKEN", "old-name-token")
    assert sphere._app_token() == "old-name-token"


def test_documented_name_works(monkeypatch):
    monkeypatch.setenv("SPHERE_PLATFORM_API_KEY", "documented-token")
    assert sphere._app_token() == "documented-token"


def test_an_empty_placeholder_does_not_shadow_a_real_token(monkeypatch):
    monkeypatch.setenv("SPHERE_PLATFORM_API_KEY", "")
    monkeypatch.setenv("SPHERE_PLATFORM_APP_TOKEN", "real-token")
    assert sphere._app_token() == "real-token"


def test_dotenv_file_is_read_when_nothing_is_exported(tmp_path):
    (tmp_path / ".env").write_text("SPHERE_PLATFORM_API_KEY=\nSPHERE_PLATFORM_APP_TOKEN=from-dotenv\n")
    assert sphere._app_token() == "from-dotenv"


def test_unset_is_an_honest_empty_string():
    assert sphere._app_token() == ""
