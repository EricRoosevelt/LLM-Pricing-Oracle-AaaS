from collections import defaultdict
from threading import Lock
from typing import Dict, Iterable, Tuple


LabelSet = Tuple[Tuple[str, str], ...]


def _labels_key(labels: Dict[str, str] | None) -> LabelSet:
    if not labels:
        return tuple()
    return tuple(sorted((str(key), str(value)) for key, value in labels.items()))


def _format_labels(labels: LabelSet) -> str:
    if not labels:
        return ""
    rendered = ",".join(f'{key}="{value}"' for key, value in labels)
    return f"{{{rendered}}}"


class MetricsStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._counters: Dict[str, Dict[LabelSet, float]] = defaultdict(lambda: defaultdict(float))
        self._gauges: Dict[str, Dict[LabelSet, float]] = defaultdict(dict)
        self._summaries: Dict[str, Dict[LabelSet, Dict[str, float]]] = defaultdict(
            lambda: defaultdict(lambda: {"count": 0.0, "sum": 0.0})
        )

    def incr(self, name: str, amount: float = 1.0, labels: Dict[str, str] | None = None) -> None:
        with self._lock:
            self._counters[name][_labels_key(labels)] += amount

    def set_gauge(self, name: str, value: float, labels: Dict[str, str] | None = None) -> None:
        with self._lock:
            self._gauges[name][_labels_key(labels)] = value

    def observe(self, name: str, value: float, labels: Dict[str, str] | None = None) -> None:
        with self._lock:
            summary = self._summaries[name][_labels_key(labels)]
            summary["count"] += 1
            summary["sum"] += value

    def render_prometheus(self) -> str:
        lines: list[str] = []
        with self._lock:
            for name, series in sorted(self._counters.items()):
                lines.append(f"# TYPE {name} counter")
                for labels, value in sorted(series.items()):
                    lines.append(f"{name}{_format_labels(labels)} {value}")
            for name, series in sorted(self._gauges.items()):
                lines.append(f"# TYPE {name} gauge")
                for labels, value in sorted(series.items()):
                    lines.append(f"{name}{_format_labels(labels)} {value}")
            for name, series in sorted(self._summaries.items()):
                lines.append(f"# TYPE {name}_count counter")
                lines.append(f"# TYPE {name}_sum counter")
                for labels, value in sorted(series.items()):
                    label_text = _format_labels(labels)
                    lines.append(f"{name}_count{label_text} {value['count']}")
                    lines.append(f"{name}_sum{label_text} {value['sum']}")
        return "\n".join(lines) + ("\n" if lines else "")


metrics_store = MetricsStore()
