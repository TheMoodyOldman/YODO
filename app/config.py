from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    secret_key: str = "dev-secret"
    database_url: str = "sqlite:///./app.db"
    steam_api_key: str = ""
    lastfm_api_key: str = ""
    lastfm_shared_secret: str = ""  # needed for Last.fm sign-in (auth.getSession signature)
    # https://www.themoviedb.org/settings/api (v3 API key or v4 read access token)
    tmdb_api_key: str = ""
    # Optional: Google Books works without a key at low volume
    google_books_api_key: str = ""
    # Optional CJK font files for the monthly card; common system fonts are tried otherwise.
    card_font_regular: str = ""
    card_font_bold: str = ""
    # Comma-separated usernames allowed to review reports at /admin/reports.
    admin_usernames: str = ""
    # Background genre lookups (Steam / AniList / Last.fm); tests turn this off.
    background_jobs: bool = True


settings = Settings()
