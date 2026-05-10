import logging
import threading

from sshtunnel import SSHTunnelForwarder

from config import settings

logger = logging.getLogger(__name__)


class TunnelManager:
    """Manages an SSH tunnel with auto-reconnect and exponential backoff."""

    def __init__(self) -> None:
        self._tunnel: SSHTunnelForwarder | None = None
        self._lock = threading.Lock()
        self._monitor_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._consecutive_failures = 0

    # ── public API ──────────────────────────────────────────

    def start(self) -> None:
        with self._lock:
            self._create_tunnel()
            assert self._tunnel is not None
            self._tunnel.start()
            logger.info(
                "SSH tunnel open: localhost:%s → %s:%s via %s@%s:%s",
                self._tunnel.local_bind_port,
                settings.remote_host,
                settings.remote_port,
                settings.ssh_user,
                settings.ssh_host,
                settings.ssh_port,
            )
        self._stop_event.clear()
        self._consecutive_failures = 0
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        with self._lock:
            if self._tunnel and self._tunnel.is_active:
                self._tunnel.stop()
                logger.info("SSH tunnel closed.")

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self._tunnel is not None and self._tunnel.is_active

    @property
    def local_bind_port(self) -> int:
        with self._lock:
            if self._tunnel is None:
                raise RuntimeError("Tunnel not started")
            return self._tunnel.local_bind_port

    # ── internals ───────────────────────────────────────────

    def _create_tunnel(self) -> None:
        kwargs: dict = {
            "ssh_address_or_host": (settings.ssh_host, settings.ssh_port),
            "ssh_username": settings.ssh_user,
            "remote_bind_address": (settings.remote_host, settings.remote_port),
            "local_bind_address": ("127.0.0.1", settings.tunnel_port),
            "set_keepalive": settings.ssh_keepalive,
        }
        if settings.ssh_key_path.exists():
            kwargs["ssh_pkey"] = str(settings.ssh_key_path)
        if settings.ssh_password:
            kwargs["ssh_password"] = settings.ssh_password
        self._tunnel = SSHTunnelForwarder(**kwargs)

    def _reconnect(self) -> bool:
        """Attempt to reconnect. Returns True on success."""
        try:
            if self._tunnel:
                self._tunnel.stop()
        except Exception:
            pass
        try:
            self._create_tunnel()
            assert self._tunnel is not None
            self._tunnel.start()
            self._consecutive_failures = 0
            logger.info("SSH tunnel reconnected successfully.")
            return True
        except Exception:
            self._consecutive_failures += 1
            logger.exception(
                "Reconnect failed (consecutive failures: %d).",
                self._consecutive_failures,
            )
            return False

    def _monitor_loop(self) -> None:
        """Periodically check tunnel health and reconnect with backoff."""
        while not self._stop_event.is_set():
            # Wait (interruptible) for the next health check
            self._stop_event.wait(settings.tunnel_check_interval)
            if self._stop_event.is_set():
                break

            with self._lock:
                if self._tunnel and not self._tunnel.is_active:
                    logger.warning("SSH tunnel dropped — reconnecting...")
                    if not self._reconnect():
                        # Exponential backoff capped at max delay
                        backoff = min(
                            settings.retry_base_delay * (2**self._consecutive_failures),
                            settings.tunnel_max_reconnect_delay,
                        )
                        logger.info("Next reconnect attempt in %.1fs", backoff)
                        self._stop_event.wait(backoff)


tunnel_manager = TunnelManager()
