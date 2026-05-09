from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
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
    remote_port: int = 11434      # Ollama default port on remote

    # ── Local proxy ─────────────────────────────────────────
    local_host: str = "127.0.0.1"
    local_port: int = 11435       # port exposed to VS Code / Copilot
    tunnel_port: int = 11436      # internal port for SSH tunnel → remote Ollama

    # ── Model info ──────────────────────────────────────────
    model_name: str = "qwen2.5:14b"

    @property
    def ollama_base_url(self) -> str:
        return f"http://127.0.0.1:{self.tunnel_port}"


settings = Settings()
