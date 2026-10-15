"""Aggregate repeated JTL rows (load runs)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SampleAggregate:
    label: str
    sample_count: int = 0
    failure_count: int = 0
    elapsed_ms: list[float] = field(default_factory=list)
    response_codes: set[int] = field(default_factory=set)
    last_row: dict | None = None

    @property
    def error_rate(self) -> float:
        if self.sample_count == 0:
            return 0.0
        return self.failure_count / self.sample_count

    @property
    def avg_elapsed_ms(self) -> float | None:
        if not self.elapsed_ms:
            return None
        return sum(self.elapsed_ms) / len(self.elapsed_ms)

    @property
    def max_elapsed_ms(self) -> float | None:
        return max(self.elapsed_ms) if self.elapsed_ms else None

    def p95_elapsed_ms(self) -> float | None:
        if not self.elapsed_ms:
            return None
        sorted_vals = sorted(self.elapsed_ms)
        idx = max(0, int(len(sorted_vals) * 0.95) - 1)
        return sorted_vals[idx]

    def any_failure(self) -> bool:
        return self.failure_count > 0


def ingest_jtl_row(aggregates: dict[str, SampleAggregate], row: dict) -> None:
    label = row.get("label") or row.get("Label") or ""
    if not label:
        return
    agg = aggregates.setdefault(label, SampleAggregate(label=label))
    agg.sample_count += 1
    success = (row.get("success") or row.get("Success") or "").lower() == "true"
    if not success:
        agg.failure_count += 1
    elapsed_raw = row.get("elapsed") or row.get("Elapsed") or "0"
    try:
        agg.elapsed_ms.append(float(elapsed_raw))
    except ValueError:
        pass
    status_raw = row.get("responseCode") or row.get("Response Code") or ""
    try:
        agg.response_codes.add(int(status_raw))
    except ValueError:
        pass
    agg.last_row = row
