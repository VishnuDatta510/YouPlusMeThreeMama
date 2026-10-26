from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/minirayyan"
    jwt_secret: str = "dev-secret-change-me"  # app refuses to start with this on Railway
    jwt_expire_minutes: int = 720
    cors_origins: str = "http://localhost:3000"
    cors_origin_regex: str = ""  # e.g. https://mini-rayyan-.*\.vercel\.app for Vercel preview URLs
    ncbi_tool: str = "mini-rayyan"
    ncbi_email: str = ""
    ncbi_api_key: str = ""
    max_fetch: int = 200
    pico_method: str = "rules"
    screening_criteria: str = "non_english,non_human,case_report,simulation"
    seed_email: str = "demo@minirayyan.dev"
    seed_password: str = "demo1234"

    @property
    def sqlalchemy_url(self) -> str:
        # Railway hands out postgres:// or postgresql:// URLs; SQLAlchemy needs the psycopg driver named.
        url = self.database_url.replace("postgres://", "postgresql://", 1)
        return url.replace("postgresql://", "postgresql+psycopg://", 1)

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
