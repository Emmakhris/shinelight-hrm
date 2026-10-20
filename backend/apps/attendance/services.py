"""Attendance capture, daily processing, overtime classification and payroll summaries."""

import datetime as dt
import math
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import BusinessRuleError
from apps.core.services import daterange, holiday_dates

from .models import (
    AttendanceDay,
    AttendancePeriodSummary,
    AttendancePolicy,
    ClockEvent,
    RosterEntry,
    Shift,
    ShiftPattern,
)

DEFAULT_WEEKEND = [5, 6]


def policy_for(employee) -> AttendancePolicy | None:
    for p in AttendancePolicy.objects.filter(is_active=True).order_by("priority", "id"):
        if p.matches(employee):
            return p
    return None


def weekend_days(policy):
    return policy.weekend_days if policy and policy.weekend_days else DEFAULT_WEEKEND


def scheduled_shift(employee, date, policy=None):
    """Returns (shift or None, rostered: bool, on_call: bool)."""
    entry = RosterEntry.objects.filter(employee=employee, date=date).select_related("shift").first()
    if entry is not None:
        return entry.shift, True, entry.is_on_call
    policy = policy or policy_for(employee)
    if date.weekday() in weekend_days(policy):
        return None, False, False
    return (policy.default_shift if policy else None), False, False


def shift_window(shift: Shift, date):
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(dt.datetime.combine(date, shift.start_time), tz)
    end_date = date + dt.timedelta(days=1) if shift.crosses_midnight else date
    end = timezone.make_aware(dt.datetime.combine(end_date, shift.end_time), tz)
    return start, end


def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000
    p1, p2 = math.radians(float(lat1)), math.radians(float(lat2))
    dp = math.radians(float(lat2) - float(lat1))
    dl = math.radians(float(lon2) - float(lon1))
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


@transaction.atomic
def clock(employee, source="web", direction="auto", latitude=None, longitude=None, ip=None, timestamp=None):
    policy = policy_for(employee)
    if source in ("web", "mobile") and policy and not policy.allow_web_clock:
        raise BusinessRuleError("Web/mobile clock-in is not enabled for your attendance policy.")
    within = None
    loc = employee.location
    if loc and loc.latitude is not None and latitude is not None and longitude is not None:
        within = haversine_m(latitude, longitude, loc.latitude, loc.longitude) <= loc.geofence_radius_m
    org = employee.organization
    if source in ("web", "mobile") and policy and policy.require_geofence and org.has_feature("geofence"):
        if latitude is None or longitude is None:
            raise BusinessRuleError("Location is required to clock in. Allow location access and try again.")
        if within is False:
            raise BusinessRuleError(f"You are outside the permitted area for {loc.name}.")
    ts = timestamp or timezone.now()
    if direction == "auto":
        last = ClockEvent.objects.filter(employee=employee, is_void=False,
                                         timestamp__gte=ts - dt.timedelta(hours=16)).order_by("-timestamp").first()
        direction = "out" if last and last.direction == "in" else "in"
    event = ClockEvent.objects.create(employee=employee, timestamp=ts, direction=direction, source=source,
                                      latitude=latitude, longitude=longitude, within_geofence=within, ip_address=ip)
    return event


def _round_down(minutes, block):
    return (minutes // block) * block if block else minutes


@transaction.atomic
def process_day(employee, date) -> AttendanceDay:
    """Compute the attendance record for one employee/day from clock events, roster, leave and holidays."""
    from apps.leave.services import on_leave_on

    day, _ = AttendanceDay.objects.get_or_create(employee=employee, date=date)
    if day.locked:
        return day
    policy = policy_for(employee)
    shift, rostered, on_call = scheduled_shift(employee, date, policy)
    is_holiday = date in holiday_dates(date, date)
    on_leave = on_leave_on(date).filter(employee=employee).exists()

    if shift is not None:
        start, end = shift_window(shift, date)
        window = (start - dt.timedelta(hours=4), end + dt.timedelta(hours=6))
    else:
        tz = timezone.get_current_timezone()
        start = end = None
        window = (timezone.make_aware(dt.datetime.combine(date, dt.time(0, 0)), tz),
                  timezone.make_aware(dt.datetime.combine(date, dt.time(23, 59, 59)), tz))
    events = list(ClockEvent.objects.filter(employee=employee, is_void=False,
                                            timestamp__range=window).order_by("timestamp"))
    ins = [e.timestamp for e in events if e.direction in ("in", "auto")]
    outs = [e.timestamp for e in events if e.direction == "out"]
    first_in = min(ins) if ins else (events[0].timestamp if events else None)
    last_out = max(outs) if outs else (events[-1].timestamp if len(events) > 1 else None)
    if last_out and first_in and last_out <= first_in:
        last_out = None

    day.shift = shift
    day.scheduled_start, day.scheduled_end = start, end
    day.first_in, day.last_out = first_in, last_out
    day.worked_minutes = day.late_minutes = day.early_leave_minutes = day.overtime_minutes = 0
    day.overtime_category = ""
    day.is_exception = False

    if first_in and last_out:
        gross = int((last_out - first_in).total_seconds() // 60)
        brk = shift.break_minutes if shift and gross > 300 else 0
        day.worked_minutes = max(gross - brk, 0)

    if on_leave and not events:
        day.status = "on_leave"
    elif is_holiday and not events:
        day.status = "holiday"
    elif shift is None and not events:
        day.status = "off"
    elif not events:
        day.status = "absent"
        day.is_exception = True
    elif not (first_in and last_out):
        day.status = "incomplete"
        day.is_exception = True
    else:
        day.status = "present"
        if shift is not None:
            late = int((first_in - start).total_seconds() // 60)
            if late > shift.grace_in_minutes:
                day.late_minutes = late
                day.status = "late"
                day.is_exception = True
            early = int((end - last_out).total_seconds() // 60)
            if early > shift.grace_out_minutes:
                day.early_leave_minutes = early
                day.is_exception = True
            if day.worked_minutes < (policy.half_day_minutes if policy else 240):
                day.status = "half_day"
        # overtime
        threshold = policy.overtime_after_minutes if policy else 30
        block = policy.rounding_minutes if policy else 15
        if shift is None or is_holiday:
            ot = day.worked_minutes
            day.overtime_category = "holiday" if is_holiday else "weekend"
        else:
            ot = max(day.worked_minutes - shift.scheduled_minutes, 0)
            day.overtime_category = "night" if shift.is_night else "normal"
        if ot >= threshold:
            day.overtime_minutes = _round_down(ot, block)
        if day.overtime_minutes:
            needs_approval = policy.overtime_requires_approval if policy else True
            if day.overtime_status not in ("approved", "rejected"):
                day.overtime_status = "pending" if needs_approval else "approved"
            if day.overtime_status == "approved" and not day.approved_overtime_minutes:
                day.approved_overtime_minutes = day.overtime_minutes
        else:
            day.overtime_status = "none"
            day.overtime_category = ""
    day.notes = "On call" if on_call else ""
    day.save()
    return day


def process_range(start, end, employees=None):
    from apps.employees.models import ACTIVE_STATUSES, Employee

    employees = employees if employees is not None else Employee.objects.filter(status__in=ACTIVE_STATUSES,
                                                                                hire_date__lte=end)
    n = 0
    for emp in employees:
        for d in daterange(max(start, emp.hire_date), min(end, emp.exit_date or end)):
            process_day(emp, d)
            n += 1
    return n


@transaction.atomic
def approve_overtime(day: AttendanceDay, minutes=None, approve=True):
    if day.locked:
        raise BusinessRuleError("Attendance for this period is locked.")
    if approve:
        day.approved_overtime_minutes = min(minutes if minutes is not None else day.overtime_minutes,
                                            day.overtime_minutes)
        day.overtime_status = "approved"
    else:
        day.approved_overtime_minutes = 0
        day.overtime_status = "rejected"
    day.save(update_fields=["approved_overtime_minutes", "overtime_status", "updated_at"])
    return day


@transaction.atomic
def apply_correction(correction):
    for ts, direction in ((correction.clock_in, "in"), (correction.clock_out, "out")):
        if ts:
            ClockEvent.objects.get_or_create(employee=correction.employee, timestamp=ts, source="correction",
                                             defaults={"direction": direction})
    correction.status = "approved"
    correction.save(update_fields=["status", "updated_at"])
    process_day(correction.employee, correction.date)


def generate_roster(employees, pattern: ShiftPattern, start, end, offset=0, stagger=0, overwrite=False,
                    department=None):
    """Apply a rotating pattern. `stagger` shifts each successive employee along the cycle."""
    seq = pattern.sequence or []
    if not seq:
        raise BusinessRuleError("Pattern has no sequence.")
    shifts = {s.id: s for s in Shift.objects.filter(id__in=[x for x in seq if x])}
    created = 0
    for idx, emp in enumerate(employees):
        for i, d in enumerate(daterange(start, end)):
            sid = seq[(i + offset + idx * stagger) % len(seq)]
            shift = shifts.get(sid) if sid else None
            if shift is not None:
                _check_credentials(emp, shift, d)
            defaults = {"shift": shift, "source": "pattern", "department": department}
            if overwrite:
                RosterEntry.objects.update_or_create(employee=emp, date=d, defaults=defaults)
                created += 1
            else:
                _, was_created = RosterEntry.objects.get_or_create(employee=emp, date=d, defaults=defaults)
                created += int(was_created)
    return created


def _check_credentials(employee, shift, date):
    """Hospital add-on: block rostering clinical staff whose licence has lapsed."""
    org = employee.organization
    if org.has_feature("hospital"):
        from apps.hospital.services import assert_credentials_valid

        assert_credentials_valid(employee, date)


def assign_shift(employee, date, shift, user=None, source="manual", is_on_call=False, department=None, notes=""):
    if shift is not None:
        _check_credentials(employee, shift, date)
    entry, _ = RosterEntry.objects.update_or_create(
        employee=employee, date=date,
        defaults={"shift": shift, "source": source, "is_on_call": is_on_call, "department": department,
                  "notes": notes})
    return entry


@transaction.atomic
def build_period_summary(start, end, lock=False):
    """Aggregate attendance into per-employee period totals for payroll. Only approved OT counts."""
    from apps.employees.models import ACTIVE_STATUSES, Employee

    process_range(start, end)
    summaries = []
    for emp in Employee.objects.filter(status__in=ACTIVE_STATUSES, hire_date__lte=end):
        days = AttendanceDay.objects.filter(employee=emp, date__range=(start, end))
        s, _ = AttendancePeriodSummary.objects.get_or_create(employee=emp, period_start=start, period_end=end)
        if s.locked:
            summaries.append(s)
            continue
        policy = policy_for(emp)
        s.scheduled_days = days.exclude(status__in=["off", "holiday"]).count()
        s.days_present = Decimal(days.filter(status__in=["present", "late"]).count()) + \
            Decimal(days.filter(status="half_day").count()) / 2
        s.days_absent = Decimal(days.filter(status="absent").count())
        s.days_on_leave = Decimal(days.filter(status="on_leave").count())
        s.late_count = days.filter(late_minutes__gt=0).count()
        s.late_minutes = sum(days.values_list("late_minutes", flat=True))
        s.incomplete_days = days.filter(status="incomplete").count()

        def ot_hours(cat):
            mins = sum(days.filter(overtime_category=cat, overtime_status="approved")
                       .values_list("approved_overtime_minutes", flat=True))
            return (Decimal(mins) / 60).quantize(Decimal("0.01"))

        s.ot_normal_hours = ot_hours("normal") + ot_hours("night")
        s.ot_weekend_hours = ot_hours("weekend")
        s.ot_holiday_hours = ot_hours("holiday")
        if policy and policy.max_overtime_hours_month:
            cap = Decimal(policy.max_overtime_hours_month)
            total = s.ot_normal_hours + s.ot_weekend_hours + s.ot_holiday_hours
            if total > cap:
                factor = cap / total
                s.ot_normal_hours = (s.ot_normal_hours * factor).quantize(Decimal("0.01"))
                s.ot_weekend_hours = (s.ot_weekend_hours * factor).quantize(Decimal("0.01"))
                s.ot_holiday_hours = (s.ot_holiday_hours * factor).quantize(Decimal("0.01"))
        s.night_shifts = days.filter(shift__is_night=True, status__in=["present", "late", "half_day"]).count()
        s.on_call_days = days.filter(notes="On call").count()
        s.unexcused_absence_days = s.days_absent if (policy and policy.absent_deduction) else Decimal("0")
        s.locked = lock
        s.save()
        if lock:
            days.update(locked=True)
        summaries.append(s)
    return summaries
