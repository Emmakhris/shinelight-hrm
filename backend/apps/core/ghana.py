"""Ghana localisation helpers: statutory public holidays.

The list reflects the Public Holidays and Commemorative Days Act as amended (verify each year
against the Ministry of the Interior's gazette). Eid al-Fitr and Eid al-Adha dates depend on the
lunar calendar and are announced annually - HR adds them in Settings > Holidays.
"""

import datetime as dt

from .models import PublicHoliday

FIXED = [
    (1, 1, "New Year's Day"),
    (1, 7, "Constitution Day"),
    (3, 6, "Independence Day"),
    (5, 1, "May Day (Workers' Day)"),
    (7, 1, "Republic Day"),
    (8, 4, "Founders' Day"),
    (9, 21, "Kwame Nkrumah Memorial Day"),
    (12, 25, "Christmas Day"),
    (12, 26, "Boxing Day"),
]


def easter_sunday(year: int) -> dt.date:
    """Anonymous Gregorian algorithm."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 22 * m) // 451
    month = (h + m - 7 * n + 114) // 31
    day = (h + m - 7 * n + 114) % 31 + 1
    return dt.date(year, month, day)


def first_friday_of_december(year: int) -> dt.date:
    d = dt.date(year, 12, 1)
    while d.weekday() != 4:
        d += dt.timedelta(days=1)
    return d


def ghana_holidays(year: int, observe_weekend=True):
    days = [(dt.date(year, m, d), name) for m, d, name in FIXED]
    easter = easter_sunday(year)
    days += [(easter - dt.timedelta(days=2), "Good Friday"), (easter + dt.timedelta(days=1), "Easter Monday"),
             (first_friday_of_december(year), "Farmers' Day")]
    out = list(days)
    if observe_weekend:
        taken = {d for d, _ in days}
        for d, name in days:
            if d.weekday() >= 5 and name not in ("Good Friday", "Easter Monday"):
                obs = d + dt.timedelta(days=7 - d.weekday())
                while obs in taken:
                    obs += dt.timedelta(days=1)
                taken.add(obs)
                out.append((obs, f"{name} (observed)"))
    return sorted(out)


def seed_public_holidays(year: int) -> int:
    created = 0
    for d, name in ghana_holidays(year):
        _, was_created = PublicHoliday.objects.get_or_create(date=d, name=name)
        created += int(was_created)
    return created
