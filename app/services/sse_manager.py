import json
from typing import Any


class SSEStreamManager:
    def __init__(self) -> None:
        self._seq = 0

    def emit(self, event_type: str, payload: dict) -> str:
        self._seq += 1
        data = json.dumps({"event": event_type, **payload})
        return f"id: {self._seq}\nevent: {event_type}\ndata: {data}\n\n"
