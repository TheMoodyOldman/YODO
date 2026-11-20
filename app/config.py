from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    secret_key: str = "dev-secret"
    session_https_only: bool = False  # True behind public HTTPS; False for local HTTP development
    database_url: str = "sqlite:///./app.db"
    steam_api_key: str = ""
    lastfm_api_key: str = ""
    lastfm_shared_secret: str = ""  # needed for Last.fm sign-in (auth.getSession signature)
    # https://www.themoviedb.org/settings/api (v3 API key or v4 read access token)
    tmdb_api_key: str = ""
    # Optional: Google Books works without a key at low volume
    google_books_api_key: str = ""
    google_books_client_id: str = ""
    google_books_client_secret: str = ""
    google_books_redirect_uri: str = ""
    # Optional CJK font files for the monthly card; common system fonts are tried otherwise.
    card_font_regular: str = ""
    card_font_bold: str = ""
    # Comma-separated usernames allowed to review reports at /admin/reports.
    admin_usernames: str = ""
    # Background genre lookups (Steam / AniList / Last.fm); tests turn this off.
    background_jobs: bool = True
    # Outgoing mail for email verification and password resets (e.g. Gmail: smtp.gmail.com, port 587,
    # your address, and an app password). Verification is only enforced once mail is configured.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    mail_from: str = ""
    # Address used in emailed links, e.g. https://yodo.example.com (defaults to the request's own address)
    public_url: str = ""
    # Demo without the network: folder of downloaded covers / song previews (scripts.cache_covers),
    # e.g. "demo_assets". Pages use a local copy when there is one. Empty = off.
    local_assets_dir: str = ""


settings = Settings()
