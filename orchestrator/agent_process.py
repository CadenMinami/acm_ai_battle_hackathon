import json
import os
import queue
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional


class AgentProcess:
    """Wraps one persistent agent subprocess: sends JSON-line requests,
    collects JSON-line responses on a background thread, and enforces a
    per-request wall-clock deadline measured with a monotonic clock."""

    def __init__(self, command: List[str]):
        self._proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        if self._proc.stdin is not None:
            os.set_blocking(self._proc.stdin.fileno(), False)
        self._pending = b""
        self._responses: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._reader_thread.start()

    def _read_loop(self) -> None:
        assert self._proc.stdout is not None
        for line in self._proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            self._responses.put(message)

    def _flush_pending(self) -> bool:
        assert self._proc.stdin is not None
        fd = self._proc.stdin.fileno()
        while self._pending:
            try:
                written = os.write(fd, self._pending)
            except BlockingIOError:
                return False
            except (BrokenPipeError, OSError):
                return False
            if written <= 0:
                return False
            self._pending = self._pending[written:]
        return True

    def send_request(self, payload: Dict[str, Any]) -> bool:
        """Write one request without waiting. Split from await_response
        so the orchestrator can open both players' deadline windows at
        the same moment: send to both agents first, then collect both."""
        if self._proc.poll() is not None or self._proc.stdin is None:
            return False
        if not self._flush_pending() or self._pending:
            return False
        message = (json.dumps(payload) + "\n").encode()
        try:
            written = os.write(self._proc.stdin.fileno(), message)
            self._pending = message[written:]
            return True
        except BlockingIOError:
            return False
        except (BrokenPipeError, OSError):
            return False

    def await_response(self, request_id: Any, deadline: float) -> Optional[Dict[str, Any]]:
        """Wait until `deadline` (an absolute time.monotonic() value) for
        the response matching request_id. Returns None on timeout, a dead
        process, or malformed output — all three are treated identically
        by the caller (a missed poll), so this method doesn't distinguish
        them. Uses max(0, remaining) rather than returning early on
        remaining <= 0, so a response that arrived in time but hasn't been
        drained from the queue yet is still accepted."""
        while True:
            remaining = max(0.0, deadline - time.monotonic())
            try:
                message = self._responses.get(timeout=remaining)
            except queue.Empty:
                return None
            if message.get("request_id") == request_id:
                return message
            # Stale response from a prior tick — discard and keep waiting.

    def request(self, payload: Dict[str, Any], deadline_seconds: float) -> Optional[Dict[str, Any]]:
        """Convenience wrapper: send one request and wait up to
        deadline_seconds for its response."""
        if not self.send_request(payload):
            return None
        return self.await_response(payload.get("request_id"), time.monotonic() + deadline_seconds)

    def close(self) -> None:
        if self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                self._proc.kill()
