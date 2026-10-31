from datetime import datetime, timedelta

import pandas as pd

from smartbins import faults

NOW = datetime(2026, 11, 1, 20, 0)


def series(values, start=datetime(2026, 11, 1, 8, 0), battery=80):
    t = [start + timedelta(minutes=30 * i) for i in range(len(values))]
    return pd.DataFrame({"timestamp": t, "fill_percent": values, "battery_percent": battery})


def codes(df, now=None):
    return {i.code for i in faults.check_sensor(df, now or df.timestamp.max())}


def test_full_bin_is_not_stuck():
    # Bug #2: a bin that is simply full must NOT be flagged as faulty
    assert "stuck" not in codes(series([100.0] * 25))


def test_stuck_sensor_detected():
    assert "stuck" in codes(series([42.0] * 25))


def test_normal_filling_is_ok():
    assert not faults.has_fault(faults.check_sensor(series([10 + 3 * i for i in range(25)]), NOW))


def test_jump_and_freeze_detected():
    assert "jump_freeze" in codes(series([20, 22, 24, 80] + [80.0] * 8))


def test_emptying_is_not_a_fault():
    df = series([60, 65, 70, 3, 5, 8, 11, 14])
    assert not faults.has_fault(faults.check_sensor(df, df.timestamp.max()))


def test_offline_detected():
    df = series([10, 12, 14])
    assert "offline" in codes(df, now=df.timestamp.max() + timedelta(hours=8))


def test_normal_gap_between_batches_is_not_offline():
    # Option 1: batches arrive every 3 h, so a 3 h old last reading is normal
    df = series([10, 12, 14])
    assert "offline" not in codes(df, now=df.timestamp.max() + timedelta(hours=3))
