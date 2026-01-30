from typing import Callable, Dict, List, Any

class EventBus:
    def __init__(self):
        self._subs: Dict[str, List[Callable[[dict], None]]] = {}

    def subscribe(self, topic: str, handler: Callable[[dict], None]) -> None:
        self._subs.setdefault(topic, []).append(handler)

    def publish(self, topic: str, event: dict) -> None:
        # fan-out
        for handler in self._subs.get(topic, []):
            handler(event)
