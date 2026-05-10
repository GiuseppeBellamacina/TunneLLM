from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env relative to the project root (one level up from local/)
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── SSH connection ──────────────────────────────────────
    ssh_host: str = "localhost"
    ssh_port: int = 22
    ssh_user: str = "root"
    ssh_key_path: Path = Path.home() / ".ssh" / "id_rsa"
    ssh_password: str | None = None  # only if key is encrypted or no key
    ssh_keepalive: float = 10.0

    # ── Remote Ollama server ────────────────────────────────
    remote_host: str = "127.0.0.1"
    remote_port: int = 11434  # Ollama default port on remote

    # ── Local proxy ─────────────────────────────────────────
    local_host: str = "127.0.0.1"
    local_port: int = 11434  # port exposed to VS Code / Copilot
    tunnel_port: int = 11435  # internal port for SSH tunnel → remote Ollama

    # ── Model info ──────────────────────────────────────────
    model_name: str = "qwen3-coder:30b"

    # ── Retry / resilience ──────────────────────────────────
    max_retries: int = 3
    retry_base_delay: float = 1.0  # seconds, exponential backoff base

    # ── Concurrency ─────────────────────────────────────────
    max_concurrent_inferences: int = 4  # max inference requests in flight

    # ── Timeouts (seconds) ──────────────────────────────────
    connect_timeout: float = 10.0
    read_timeout: float = 600.0  # 10 min for long generations
    write_timeout: float = 10.0

    # ── Tunnel monitor ──────────────────────────────────────
    tunnel_check_interval: float = 5.0  # seconds between health checks
    tunnel_max_reconnect_delay: float = 30.0  # cap for exponential backoff

    @property
    def ollama_base_url(self) -> str:
        return f"http://127.0.0.1:{self.tunnel_port}"


settings = Settings()
