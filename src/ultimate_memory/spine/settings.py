"""Typed settings for the PostgreSQL spine."""

from pydantic import SecretStr
from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """Validated database connection settings read at the spine boundary."""

    model_config = SettingsConfigDict(env_prefix="UGM_", extra="ignore")

    database_url: SecretStr

    def sqlalchemy_url(self) -> str:
        """Return the database URL only at the SQLAlchemy connection call site."""
        return self.database_url.get_secret_value()


def load_database_settings() -> DatabaseSettings:
    """Load database settings from their typed environment-backed source."""
    return DatabaseSettings.model_validate({})


class ApiClientSettings(BaseSettings):
    """How the `ugm query` CLI reaches the running query API.

    `api_url` is where the API lives (UGM_API_URL). `api_authorization` is the
    optional `Authorization` header value (UGM_API_AUTHORIZATION, e.g.
    ``Bearer <token>``) — required only when the API runs behind an auth
    perimeter; without it the CLI sends no credential.
    """

    model_config = SettingsConfigDict(env_prefix="UGM_", extra="ignore")

    api_url: str = "http://127.0.0.1:8000"
    api_authorization: SecretStr | None = None


def load_api_client_settings() -> ApiClientSettings:
    """Load the query-API client settings from their environment source."""
    return ApiClientSettings.model_validate({})
