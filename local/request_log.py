"""Request/response logging for the dashboard."""

import threading
import time
from dataclasses import dataclass, field


@dataclass
class LogEntry:
    """A single proxied request with full request/response bodies."""

    id: str
    timestamp: float = field(default_factory=time.time)
    method: str = "POST"
    url: str = ""
    model_original: str = ""
    model_resolved: str = ""

    # Request
    request_body: dict | None = None

    # Response
    response_status: int = 0
    response_body: dict | str | None = None
    response_chunks: list[str] = field(default_factory=list)

    # Timing
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None
    first_token_time: float | None = None

    # Status
    status: str = "in_progress"  # in_progress | completed | failed
    error: str | None = None
    streaming: bool = False

    @property
    def latency_ms(self) -> float | None:
        if self.end_time:
            return round((self.end_time - self.start_time) * 1000, 1)
        return None

    @property
    def ttft_ms(self) -> float | None:
        if self.first_token_time:
            return round((self.first_token_time - self.start_time) * 1000, 1)
        return None

    def to_summary(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "method": self.method,
            "url": self.url,
            "model_original": self.model_original,
            "model_resolved": self.model_resolved,
            "status": self.status,
            "response_status": self.response_status,
            "streaming": self.streaming,
            "latency_ms": self.latency_ms,
            "ttft_ms": self.ttft_ms,
            "error": self.error,
        }

    def to_detail(self) -> dict:
        d = self.to_summary()
        d["request_body"] = self.request_body

        if self.streaming and self.response_chunks:
            # Assemble streamed content
            d["response_body"] = self._assemble_stream()
            d["response_chunks_count"] = len(self.response_chunks)
        else:
            d["response_body"] = self.response_body

        return d

    def _assemble_stream(self) -> dict | str:
        """Parse SSE/NDJSON chunks and assemble the full response."""
        import json

        contents: list[str] = []
        tool_calls: list[dict] = []
        usage: dict | None = None
        finish_reason: str | None = None

        for raw in self.response_chunks:
            for line in raw.split("\n"):
                line = line.strip()
                if not line:
                    continue
                if line.startswith("data: "):
                    line = line[6:]
                if line == "[DONE]":
                    continue
                try:
                    chunk = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue

                # OpenAI SSE format
                choices = chunk.get("choices", [])
                for c in choices:
                    delta = c.get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        contents.append(content)
                    # Tool calls
                    tc = delta.get("tool_calls")
                    if tc:
                        for t in tc:
                            idx = t.get("index", 0)
                            while len(tool_calls) <= idx:
                                tool_calls.append(
                                    {
                                        "id": "",
                                        "type": "function",
                                        "function": {"name": "", "arguments": ""},
                                    }
                                )
                            if "id" in t:
                                tool_calls[idx]["id"] = t["id"]
                            if "function" in t:
                                if "name" in t["function"]:
                                    tool_calls[idx]["function"]["name"] = t["function"][
                                        "name"
                                    ]
                                if "arguments" in t["function"]:
                                    tool_calls[idx]["function"]["arguments"] += t[
                                        "function"
                                    ]["arguments"]
                    fr = c.get("finish_reason")
                    if fr:
                        finish_reason = fr

                u = chunk.get("usage")
                if u:
                    usage = u

                # Ollama NDJSON format
                msg = chunk.get("message", {})
                if msg.get("content"):
                    contents.append(msg["content"])

        result: dict = {
            "role": "assistant",
            "content": "".join(contents),
        }
        if tool_calls:
            result["tool_calls"] = tool_calls
        if finish_reason:
            result["finish_reason"] = finish_reason
        if usage:
            result["usage"] = usage
        return result


class RequestLog:
    """Thread-safe circular buffer of request/response logs."""

    def __init__(self, max_entries: int = 200) -> None:
        self._entries: list[LogEntry] = []
        self._lock = threading.Lock()
        self._max = max_entries

    def new_entry(self, entry_id: str, **kwargs) -> LogEntry:
        entry = LogEntry(id=entry_id, **kwargs)
        with self._lock:
            self._entries.append(entry)
            if len(self._entries) > self._max:
                self._entries = self._entries[-self._max :]
        return entry

    def get_all_summaries(self) -> list[dict]:
        with self._lock:
            return [e.to_summary() for e in reversed(self._entries)]

    def get_detail(self, entry_id: str) -> dict | None:
        with self._lock:
            for e in self._entries:
                if e.id == entry_id:
                    return e.to_detail()
        return None


request_log = RequestLog()
