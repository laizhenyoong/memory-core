from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    db_path: str = Field("./memory.db", validation_alias="MEMORY_AGENT_DB")
    admin_key: str | None = Field(None, validation_alias="MEMORY_AGENT_ADMIN_KEY")
