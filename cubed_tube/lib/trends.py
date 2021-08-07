"""
Houses high-level trend interface for linear data-point storage/retrieval.
"""

from os import times
from cubed_tube.lib import common
from cubed_tube.lib import models as m

from time import time
from typing import List, Tuple

VIDEO_TRENDS = {
    'views': 100,
    'likes': 100,
    'dislikes': 100,
    'favorites': 100,
    'comments': 100,
}

def add_point(series: m.TrendSeries, timestamp: int, value: int):
    """Add a point to a series."""
    series.raw_count += 1
    if value is None:
        return
    if series.pivot is None:
        series.pivot = m.TrendPoint.create(
            timestamp=timestamp,
            value=value,
            series_id=series.series_id
        )
        series.current = None
        series.point_count = 1
        series.save()
        return series.pivot

    if series.current is None:
        _set_current(series, timestamp, value, reset=True)
        series.save()
        return series.current

    if _is_between_slopes(series, timestamp, value):
        _replace_current(series, timestamp, value)
        _set_bounds(series, timestamp, value)
        series.current.save()
        series.save()
        return series.current
    series.pivot = series.current
    _set_current(series, timestamp, value, reset=True)
    series.save()
    return series.current

def add_points(series: m.TrendSeries, pts: List[Tuple[int, int]]):
    while series.raw_count < 2:
        add_point(series, *pts.pop(0))
    for timestamp, value in pts:
        if value is None:
            continue
        series.raw_count += 1
        if _is_between_slopes(series, timestamp, value):
            _replace_current(series, timestamp, value)
        else:
            series.pivot = series.current
            series.pivot.save()
            _set_current(series, timestamp, value, reset=True)
            series.save()
    if series.current:
        series.current.save()
    series.save()
    
def _is_between_slopes(series: m.TrendSeries, timestamp: int, value: int):
    delta_ts = timestamp - series.current.timestamp
    assert delta_ts > 0, f'{timestamp} < {series.current.timestamp}'
    max_value = series.current.value + delta_ts * series.upper
    min_value = series.current.value + delta_ts * series.lower
    return max_value >= value >= min_value

def _replace_current(series: m.TrendSeries, timestamp: int, value: int):
    series.current.timestamp = timestamp
    series.current.value = value
    _set_bounds(series, timestamp, value)

def _set_current(series: m.TrendSeries, timestamp: int, value: int,
                 reset=False):
    """Sets the given point as the current point and sets the bounds."""
    series.point_count += 1
    pt = m.TrendPoint.create(
        timestamp=timestamp,
        value=value,
        series_id=series.series_id,
    )
    series.current = pt
    _set_bounds(series, pt.timestamp, pt.value, reset=reset)

def _set_bounds(series: m.TrendSeries, timestamp, value, reset = False):
    """Sets upper and lower bounds."""
    delta = _dynamic_delta(series, timestamp, value)
    upper = _calc_slope(series, timestamp, value + delta)
    lower = _calc_slope(series, timestamp, value - delta)
    if reset:
        series.upper = upper
        series.lower = lower
    else:
        series.upper = min(series.upper, upper)
        series.lower = max(series.lower, lower)

def _dynamic_delta(series: m.TrendSeries, timestamp, value):
    """Calculate a delta based on current slope within 10%"""
    # TODO: replace 600 with scan period (currently 10m)
    return max(series.delta, _calc_slope(series, timestamp, value) * 600 * 2)

def _calc_slope(series: m.TrendSeries, timestamp: int, value: int):
    """Good 'ol rise over run."""
    return (value - series.pivot.value) / (
        timestamp - series.pivot.timestamp)

def get_video_trend(video: m.Video, trend: str):
    trends, _ = m.VideoTrends.get_or_create(video_id=video)
    if trend not in VIDEO_TRENDS.keys():
        ValueError(f'Trend {trend} must be one of {list(VIDEO_TRENDS)}')
    if getattr(trends, trend) == None:
        setattr(trends, trend, m.TrendSeries.create(
            delta=VIDEO_TRENDS[trend]
        ))
        trends.save()
    return getattr(trends, trend)

def compress_trends(rules: List[Tuple[int, int]]):
    m.init_database()
    now = int(time())

    rules = sorted(rules, key=lambda r: r[0])
    def _get_horizon_frequency(timestamp) -> Tuple[int, int]:
        """Returns the horizon and frequency for a given timestamp"""
        delta = now - timestamp
        horizon = None
        frequency = None
        for h, f in rules:
            if h > delta:
                continue
            horizon = h
            frequency = f
        return horizon, frequency

    status = '\rChecking trend {} of {}'
    query = m.TrendSeries.select()
    total = m.TrendSeries.select(m.pw.fn.Count()).scalar()
    print()
    i = 0

    for chunk in common.chunk(query, total, 100):
        with m.db.atomic():
            print(status.format(i, total), end='')
            for series in chunk:
                i += 1
                pt_query = m.TrendPoint.select().where(
                    m.TrendPoint.series_id == series.series_id
                ).order_by(m.TrendPoint.timestamp.desc())

                prev = None
                prev_timestamp = None
                pt_count = 0

                for pt in pt_query:
                    pt_count += 1
                    horizon, frequency = _get_horizon_frequency(pt.timestamp)
                    if not horizon:
                        continue

                    timestamp = pt.timestamp // frequency * frequency
                    if not prev_timestamp:
                        prev_timestamp = timestamp
                        prev = pt

                    if pt.point_id in (series.pivot_id, series.current_id):
                        # don't touch points in foreign keys
                        prev = pt
                        prev_timestamp = timestamp
                    elif timestamp != prev_timestamp:
                        # timestamp window boundary, recalc and delete
                        if timestamp % frequency != 0:
                            dt = prev.timestamp - pt.timestamp
                            dy = prev.value - pt.value
                            val = dy / dt  * (timestamp - pt.timestamp) + pt.value
                            prev = m.TrendPoint.create(timestamp=timestamp, value=val)
                            prev.save()
                            pt.delete_instance()
                        else:
                            prev = pt
                        prev_timestamp = timestamp
                    else:
                        # none of the above, delete
                        pt_count -= 1
                        pt.delete_instance()
                if pt_count != series.point_count:
                    series.point_count = pt_count
                    series.save()
    print("\nVacuuming...")
    m.db.execute_sql('VACUUM')
