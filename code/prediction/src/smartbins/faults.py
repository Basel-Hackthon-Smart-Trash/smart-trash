"""Sensor fault detection with simple, explainable rules (no labels needed).

Each check returns a short English reason, so the dashboard
and the maintenance view can show WHY a sensor is flagged.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta

import pandas as pd

from . import config


@dataclass
class Issue:
    code: str          # machine-readable, e.g. "stuck"
    severity: str      # "fault" (don't trust the reading) or "warning"
    message: str       # short text for the dashboard


def _day_mask(ts: pd.Series) -> pd.Series:
    return ts.dt.hour.between(config.DAY_START_H, config.DAY_END_H - 1)


def check_sensor(readings: pd.DataFrame, now: datetime) -> list[Issue]:
    """readings: one sensor, columns timestamp, fill_percent, battery_percent."""
    issues: list[Issue] = []
    if readings.empty:
        return [Issue("no_data", "fault", "No readings received")]

    r = readings.sort_values("timestamp")
    last = r.iloc[-1]

    # 1. Offline: no new reading for too long
    if now - last.timestamp > timedelta(hours=config.NO_DATA_HOURS):
        hours = (now - last.timestamp).total_seconds() / 3600
        issues.append(Issue("offline", "fault", f"No data for {hours:.0f} h"))

    # 2. Out of range: impossible values
    if ((r.fill_percent < 0) | (r.fill_percent > 100)).any():
        issues.append(Issue("out_of_range", "fault", "Value outside 0-100 %"))

    # 3. Stuck: no change over the last 8 DAYTIME hours, although people use the bin.
    #    (Night hours are skipped: a bin can legitimately stay still at night.)
    day = r[(r.timestamp >= last.timestamp - timedelta(hours=36)) & _day_mask(r.timestamp)]
    if not day.empty:
        window = day[day.timestamp >= day.timestamp.max() - timedelta(hours=config.STUCK_HOURS)]
        span = window.timestamp.max() - window.timestamp.min()
        if (
            span >= timedelta(hours=config.STUCK_HOURS - 0.5)
            and window.fill_percent.max() - window.fill_percent.min() < config.STUCK_MAX_RANGE
            and window.fill_percent.iloc[-1] < config.FULL_IS_NOT_STUCK   # a full bin may sit still (bug #2)
        ):
            issues.append(Issue("stuck", "fault",
                                f"Same value ({window.fill_percent.iloc[-1]:.0f} %) for {config.STUCK_HOURS}+ daytime hours"))

    # 4. Jump-and-freeze: sudden big rise, then no change at all
    diffs = r.fill_percent.diff()
    jumps = diffs[diffs >= config.JUMP_POINTS].index
    for j in jumps:
        pos = r.index.get_loc(j)
        after = r.iloc[pos: pos + config.JUMP_FREEZE_READINGS + 1]
        if len(after) > config.JUMP_FREEZE_READINGS and after.fill_percent.max() - after.fill_percent.min() < config.STUCK_MAX_RANGE:
            issues.append(Issue("jump_freeze", "fault",
                                f"Jumped +{diffs[j]:.0f} points, then froze"))
            break

    # 5. Partial drop: bins are emptied fully, they don't lose 8-30 points on their own
    recent = r[r.timestamp >= now - timedelta(hours=24)]
    d = recent.fill_percent.diff()
    if ((d <= -config.PARTIAL_DROP_MIN) & (d > -config.EMPTY_DROP_POINTS)).any():
        issues.append(Issue("partial_drop", "warning", "Unusual drop without emptying"))

    # 6. Battery
    if last.battery_percent < config.LOW_BATTERY:
        issues.append(Issue("low_battery", "warning", f"Battery {last.battery_percent:.0f} %"))

    return issues


def has_fault(issues: list[Issue]) -> bool:
    return any(i.severity == "fault" for i in issues)
