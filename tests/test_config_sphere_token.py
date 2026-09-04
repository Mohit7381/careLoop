"""Settings.sphere_platform_app_token — a real key placed in .env under the
name .env.example actually documents (SPHERE_PLATFORM_API_KEY) has to reach
this field. It didn't: the field's own name made pydantic-settings look for
SPHERE_PLATFORM_APP_TOKEN instead, so every live sphere call went out with an
empty token and failed as an auth error, not a config error. Constructs
Settings directly with _env_file=None so this doesn't depend on (or leak
into) the developer's real .env.
"""
from app.config import Settings


def test_documented_env_var_name_binds_the_token():
    s = Settings(_env_file=None, SPHERE_PLATFORM_API_KEY="a-real-key")
    assert s.sphere_platform_app_token == "a-real-key"


def test_field_name_still_binds_too():
    s = Settings(_env_file=None, sphere_platform_app_token="a-real-key")
    assert s.sphere_platform_app_token == "a-real-key"


def test_unset_is_still_an_honest_empty_string():
    s = Settings(_env_file=None)
    assert s.sphere_platform_app_token == ""
