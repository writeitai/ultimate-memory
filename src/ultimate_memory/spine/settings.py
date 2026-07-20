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
