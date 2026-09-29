from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "sqlite:///./evidence.db"
    redis_url: str = "redis://localhost:6379/0"
    s3_endpoint: str = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "evidence"
    storage_backend: str = "s3"
    local_storage_path: str = "storage/evidence"
    queue_mode: str = "celery"
    app_secret: str = "development-only-change-me-before-deployment-32-bytes"
    admin_password: str = "development-only"
    analyst_password: str | None = None
    viewer_password: str | None = None
    store_raw_identifiers: bool = False
    screenshot_threshold: int = 50
    normal_profile_ttl_days: int = 30
    suspicious_profile_ttl_days: int = 7
    high_risk_profile_ttl_days: int = 1
    evidence_retention_days: int = 180
    max_browser_contexts: int = 2
    max_pages_per_context: int = 2
    max_capture_concurrency: int = 3
    browser_max_jobs: int = 200
    browser_proxy_server: str | None = None
    browser_proxy_username: str | None = None
    browser_proxy_password: str | None = None
    browser_storage_state_path: str | None = None
    capture_full_page: bool = False
    avatar_phash_distance_strong: int = 5
    avatar_phash_distance_possible: int = 10
    burst_window_seconds: int = 60
    burst_min_actors: int = 10
    max_pairwise_post_actors: int = 500
    max_cluster_edges: int = 5000


settings = Settings()
