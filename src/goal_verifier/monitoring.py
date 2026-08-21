"""Cross-platform filesystem-event capture for command integrity."""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MAX_FILESYSTEM_EVENTS = 10_000


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class FilesystemMonitor:
    def __init__(self, root: Path, protected_paths: set[str]) -> None:
        self.root = root.resolve()
        self.protected_paths = protected_paths
        self.events: list[dict[str, Any]] = []
        self.overflow = False
        self.error: str | None = None
        self._lock = threading.Lock()
        self._observer: Any = None

    def _relative(self, raw_path: str) -> str | None:
        try:
            relative = Path(raw_path).resolve().relative_to(self.root).as_posix()
        except ValueError:
            return None
        if relative == ".git" or relative.startswith(".git/"):
            return None
        return relative

    def _protected(self, path: str | None) -> bool:
        return bool(
            path
            and (
                path in self.protected_paths
                or path == ".verification"
                or path.startswith(".verification/")
            )
        )

    def _record(self, event: Any) -> None:
        if getattr(event, "is_directory", False):
            return
        event_type = getattr(event, "event_type", "unknown")
        if event_type not in {"created", "modified", "deleted", "moved"}:
            return
        source = self._relative(event.src_path)
        destination = self._relative(event.dest_path) if event_type == "moved" else None
        if source is None and destination is None:
            return
        with self._lock:
            if len(self.events) >= MAX_FILESYSTEM_EVENTS:
                self.overflow = True
                return
            self.events.append(
                {
                    "timestamp": _utc_now(),
                    "event": event_type,
                    "source": source,
                    "destination": destination,
                    "protected": self._protected(source) or self._protected(destination),
                }
            )

    def start(self) -> None:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer

        monitor = self

        class Handler(FileSystemEventHandler):
            def on_any_event(self, event: Any) -> None:
                monitor._record(event)

        observer = Observer()
        observer.schedule(Handler(), str(self.root), recursive=True)
        observer.start()
        if not observer.is_alive():
            observer.stop()
            observer.join()
            raise RuntimeError("filesystem observer did not start")
        self._observer = observer

    def stop(self) -> None:
        if self._observer is None:
            return
        try:
            self._observer.stop()
            self._observer.join(timeout=5)
            if self._observer.is_alive():
                self.error = "filesystem observer did not stop cleanly"
        except Exception as exc:  # pragma: no cover - backend-specific defensive path
            self.error = f"{type(exc).__name__}: {exc}"

    def result(self) -> dict[str, Any]:
        with self._lock:
            events = list(self.events)
        return {
            "events": events,
            "event_count": len(events),
            "protected_events": [item for item in events if item["protected"]],
            "overflow": self.overflow,
            "error": self.error,
        }
