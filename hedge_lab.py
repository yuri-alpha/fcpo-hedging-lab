"""Walk-forward evaluation of short FCPO hedges for a long inventory exposure."""

import csv
import math
import re
import statistics as stats
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Month:
    date: str
    spot: float
    changes: tuple


@dataclass(frozen=True)
class Market:
    contracts: tuple[str, ...]
    months: tuple[Month, ...]


def parse_month(value):
    if not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", value):
        raise ValueError(f"Invalid month: {value!r}. Expected YYYY-MM.")
    return int(value[:4]) * 12 + int(value[5:])


def read_market(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        header = reader.fieldnames or []
        valid = {"month", "spot_myr_t", "futures_change_c1", "futures_change_c2"}
        if (
            not {"month", "spot_myr_t", "futures_change_c1"} <= set(header)
            or not set(header) <= valid
            or len(header) != len(set(header))
        ):
            raise ValueError("Invalid CSV header. See data/README.md for the schema.")
        contracts = tuple(name for name in ("C1", "C2") if f"futures_change_{name.lower()}" in header)
        months = []
        previous = None
        for line, row in enumerate(reader, start=2):
            try:
                if None in row or None in row.values():
                    raise ValueError("Unexpected number of columns")
                date = row["month"]
                serial = parse_month(date)
                if previous is not None and serial != previous + 1:
                    raise ValueError("Months must be consecutive and strictly increasing")
                spot = float(row["spot_myr_t"])
                if not math.isfinite(spot) or spot <= 0:
                    raise ValueError("Spot must be finite and positive")
                raw = tuple(row[f"futures_change_{name.lower()}"] for name in contracts)
                if not months and any(raw):
                    raise ValueError("Futures changes must be blank in the baseline row")
                changes = tuple(float(value) for value in raw) if months else ()
                if not all(math.isfinite(value) for value in changes):
                    raise ValueError("Futures changes must be finite")
                months.append(Month(date, spot, changes))
                previous = serial
            except ValueError as exc:
                raise ValueError(f"CSV row {line}: {exc}") from exc
        if len(months) < 3:
            raise ValueError("Provide a baseline and at least two monthly intervals.")
        return Market(contracts, tuple(months))


def hedge_ratio(spot, futures):
    """Use OLS with an intercept and cap the target at 150% of inventory."""
    variance = stats.variance(futures)
    if variance == 0:
        return 0.0
    beta = stats.covariance(spot, futures) / variance
    return max(0.0, min(1.5, beta))


def walk_forward(market, contract, window, start, end, cost):
    """Use changes strictly before each realized interval to size that interval's hedge."""
    if window < 2:
        raise ValueError("The estimation window must have at least two intervals.")
    if not math.isfinite(cost) or cost < 0:
        raise ValueError("Round-trip cost must be finite and nonnegative.")
    if parse_month(start) > parse_month(end):
        raise ValueError("Evaluation end must be on or after the start.")
    try:
        first = next(i for i, month in enumerate(market.months) if month.date == start) - 1
        last = next(i for i, month in enumerate(market.months) if month.date == end) - 1
    except StopIteration as exc:
        raise ValueError("Both evaluation endpoints must be present in the CSV.") from exc
    if first < window or last - first < 1:
        raise ValueError(f"Need {window} pre-evaluation changes and at least two evaluation intervals.")
    column = market.contracts.index(contract)
    spot = [right.spot - left.spot for left, right in zip(market.months, market.months[1:])]
    futures = [month.changes[column] for month in market.months[1:]]
    rows = []
    for i in range(first, last + 1):
        ratio = hedge_ratio(spot[i-window:i], futures[i-window:i])
        rows.append({
            "month": market.months[i + 1].date,
            "spot": spot[i],
            "futures": futures[i],
            "ratio": ratio,
            "unhedged": spot[i],
            "full": spot[i] - futures[i] - cost,
            "rolling": spot[i] - ratio * (futures[i] + cost),
        })
    return rows


def summarize(rows):
    reference = stats.variance(row["unhedged"] for row in rows)
    tail_count = math.ceil(0.05 * len(rows))
    summary = {}
    for key in ("unhedged", "full", "rolling"):
        values = [row[key] for row in rows]
        variance = stats.variance(values)
        summary[key] = {
            "volatility": math.sqrt(variance),
            "effectiveness": 1 - variance / reference if reference else None,
            "tail": stats.mean(sorted(values)[:tail_count]),
            "worst": min(values),
            "added_loss": sum(row[key] < min(row["unhedged"], 0) - 1e-9 for row in rows),
        }
    return summary
