import datetime as dt

from django.db import transaction

from .models import NumberSequence, PublicHoliday


@transaction.atomic
def next_number(key: str, default_prefix: str = "", default_pattern: str = "{prefix}{seq:05d}") -> str:
    """Generate the next number in a configurable, tenant-scoped sequence (row-locked)."""
    seq, _ = NumberSequence.objects.get_or_create(
        key=key, defaults={"prefix": default_prefix, "pattern": default_pattern}
    )
    seq = NumberSequence.objects.select_for_update().get(pk=seq.pk)
    year = dt.date.today().year
    if seq.reset_yearly and seq.last_year != year:
        seq.next_value = 1
    value = seq.pattern.format(prefix=seq.prefix, seq=seq.next_value, year=year, yy=str(year)[-2:])
    seq.next_value += 1
    seq.last_year = year
    seq.save(update_fields=["next_value", "last_year", "updated_at"])
    return value


def holiday_dates(start: dt.date, end: dt.date) -> set[dt.date]:
    dates = set(PublicHoliday.objects.filter(date__range=(start, end), is_recurring=False).values_list("date", flat=True))
    for h in PublicHoliday.objects.filter(is_recurring=True):
        for year in range(start.year, end.year + 1):
            try:
                d = h.date.replace(year=year)
            except ValueError:
                continue
            if start <= d <= end:
                dates.add(d)
    return dates


def working_days(start: dt.date, end: dt.date, weekend=(5, 6), exclude_holidays=True) -> int:
    """Count working days inclusive of start and end, excluding weekends and public holidays."""
    if end < start:
        return 0
    holidays = holiday_dates(start, end) if exclude_holidays else set()
    count = 0
    d = start
    while d <= end:
        if d.weekday() not in weekend and d not in holidays:
            count += 1
        d += dt.timedelta(days=1)
    return count


def daterange(start: dt.date, end: dt.date):
    d = start
    while d <= end:
        yield d
        d += dt.timedelta(days=1)
