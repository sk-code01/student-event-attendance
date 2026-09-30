"""
Time-series and statistical trend analysis.

**This is statistics, not machine learning.** Everything here is arithmetic over
grouped counts: period totals, period-over-period change, percentage change,
a simple moving average, and a direction label derived from comparing the last
two periods. There is no model, no training, no fitting, no persistence and no
scikit-learn import anywhere in this module — KNN, Isolation Forest, K-Means and
recommendation/anomaly scoring belong to Phase 8.

The output is deliberately shaped so Phase 8 can consume it as a feature source
without this layer being rewritten.

**Timezone:** `TIME_ZONE` (default `Asia/Kolkata`, via `APP_TIMEZONE`) with
`USE_TZ=True`. `Trunc*` on a timezone-aware DateTimeField is evaluated by
Postgres in that timezone, so a record created at 23:30 IST on the 1st falls in
the 1st, not the 2nd — the same "what day is it" rule the rest of the project
uses via `timezone.localdate()`. `Event.event_date` is a plain DateField and
needs no conversion.
"""

from django.db.models import Count, Q
from django.db.models.functions import TruncDay, TruncMonth, TruncWeek
from django.utils import timezone

from apps.achievements.models import Achievement
from apps.attendance.models import Attendance
from apps.od.models import ODRequest
from apps.verification.models import Evidence

from .scope import AnalyticsScope

TRUNC = {'daily': TruncDay, 'weekly': TruncWeek, 'monthly': TruncMonth}
LABEL_FORMAT = {'daily': '%Y-%m-%d', 'weekly': '%Y-W%V', 'monthly': '%Y-%m'}
MAX_PERIODS = 400  # Bounded so a wide daily range cannot return an unusable payload.


def _series(queryset, *, date_field, period, extra_filter=None):
    """Groups a scoped queryset into {period_label: count} with one query."""
    trunc = TRUNC[period]
    queryset = queryset.annotate(_bucket=trunc(date_field))
    if extra_filter is not None:
        queryset = queryset.filter(extra_filter)
    rows = queryset.values('_bucket').annotate(total=Count('id')).order_by('_bucket')
    out = {}
    for row in rows:
        bucket = row['_bucket']
        if bucket is None:
            continue
        out[_label(bucket, period)] = row['total']
    return out


def _label(value, period) -> str:
    # Trunc on a DateTimeField returns an aware datetime; localise before
    # formatting so the bucket label matches the timezone it was grouped in.
    if hasattr(value, 'tzinfo') and value.tzinfo is not None:
        value = timezone.localtime(value)
    return value.strftime(LABEL_FORMAT[period])


def build_trends(scope: AnalyticsScope, *, period: str = 'monthly') -> dict:
    """Chart-ready time series plus lightweight statistics.

    One grouped query per metric — six in total, regardless of how many rows
    or periods exist.
    """
    registrations = _series(scope.registrations(), date_field='registered_at', period=period)
    participations = _series(scope.participations(), date_field='created_at', period=period)
    verified = _series(
        scope.evidence(), date_field='created_at', period=period,
        extra_filter=Q(status=Evidence.Status.VERIFIED),
    )
    attendance_approved = _series(
        scope.attendance(), date_field='requested_at', period=period,
        extra_filter=Q(status=Attendance.Status.APPROVED),
    )
    od_approved = _series(
        scope.od_requests(), date_field='requested_at', period=period,
        extra_filter=Q(status=ODRequest.Status.APPROVED),
    )
    achievements = _series(
        scope.achievements(), date_field='created_at', period=period,
        extra_filter=Q(status=Achievement.Status.APPROVED),
    )

    labels = sorted(
        set(registrations) | set(participations) | set(verified)
        | set(attendance_approved) | set(od_approved) | set(achievements)
    )[-MAX_PERIODS:]

    series = [
        {
            'period': label,
            'registrations': registrations.get(label, 0),
            'participations': participations.get(label, 0),
            'verified': verified.get(label, 0),
            'attendance_approved': attendance_approved.get(label, 0),
            'od_approved': od_approved.get(label, 0),
            'achievements': achievements.get(label, 0),
        }
        for label in labels
    ]

    return {
        'period': period,
        'timezone': str(timezone.get_current_timezone()),
        'series': series,
        'statistics': {
            metric: summarise([row[metric] for row in series])
            for metric in ('registrations', 'participations', 'verified',
                           'attendance_approved', 'od_approved', 'achievements')
        },
    }


def summarise(values) -> dict:
    """Plain descriptive statistics over one series.

    `direction` compares the most recent period with the one before it:
    'rising', 'falling', 'steady', or 'insufficient_data' when there are fewer
    than two periods. `change_percent` is None when the previous period was
    zero, because growth from zero has no meaningful percentage — reporting it
    as 100% or infinity would be inventing a number.
    """
    count = len(values)
    if count == 0:
        return {
            'total': 0, 'periods': 0, 'average': None, 'latest': None, 'previous': None,
            'change': None, 'change_percent': None, 'direction': 'insufficient_data',
            'moving_average_3': [],
        }

    total = sum(values)
    latest = values[-1]
    previous = values[-2] if count >= 2 else None

    if previous is None:
        change = None
        change_percent = None
        direction = 'insufficient_data'
    else:
        change = latest - previous
        change_percent = None if previous == 0 else round(change * 100.0 / previous, 2)
        direction = 'rising' if change > 0 else ('falling' if change < 0 else 'steady')

    return {
        'total': total,
        'periods': count,
        'average': round(total / count, 2),
        'latest': latest,
        'previous': previous,
        'change': change,
        'change_percent': change_percent,
        'direction': direction,
        'moving_average_3': moving_average(values, window=3),
    }


def moving_average(values, *, window: int = 3):
    """Trailing moving average. Returns [] when there are fewer values than the
    window, rather than padding with partial averages that would read as real
    data points."""
    if window <= 0 or len(values) < window:
        return []
    return [
        round(sum(values[i - window + 1:i + 1]) / window, 2)
        for i in range(window - 1, len(values))
    ]
