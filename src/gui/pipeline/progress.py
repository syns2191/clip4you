"""Thread-safe stdout capture for streaming progress to Gradio."""

import io
import sys
import threading
import queue
from contextlib import contextmanager


class ProgressCapture:
    def __init__(self):
        self._lines = []
        self._queue = queue.Queue()
        self._lock = threading.Lock()

    @contextmanager
    def capture(self):
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        writer = _QueueWriter(self._queue)
        sys.stdout = writer
        sys.stderr = writer
        try:
            yield
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

    def get_log(self) -> str:
        while True:
            try:
                line = self._queue.get_nowait()
                self._lines.append(line)
            except queue.Empty:
                break
        return "".join(self._lines)

    def clear(self):
        with self._lock:
            self._lines.clear()
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    break


class _QueueWriter(io.TextIOBase):
    def __init__(self, q: queue.Queue):
        self._queue = q

    def write(self, text: str) -> int:
        if text:
            self._queue.put(text)
        return len(text) if text else 0

    def flush(self):
        pass
