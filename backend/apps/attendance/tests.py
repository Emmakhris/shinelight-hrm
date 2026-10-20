import datetime as dt

import pytest
from django.utils import timezone

from apps.core.exceptions import BusinessRuleError


def _ts(d, h, m=0):
    return timezone.make_aware(dt.datetime.combine(d, dt.time(h, m)), timezone.get_current_timezone())


@pytest.fixture
def emp(org, make_employee):
    return make_employee()


def test_on_time_late_and_overtime(emp):
    from apps.attendance.models import ClockEvent
    from apps.attendance.services import process_day

    d = dt.date(2026, 10, 5)  # Monday
    ClockEvent.objects.create(employee=emp, timestamp=_ts(d, 8, 30), direction="in", source="biometric")
    ClockEvent.objects.create(employee=emp, timestamp=_ts(d, 19, 0), direction="out", source="biometric")
    day = process_day(emp, d)
    assert day.status == "late" and day.late_minutes == 30
    # 10.5h gross - 1h break = 570 worked; shift 480 => 90 OT
    assert day.worked_minutes == 570
    assert day.overtime_minutes == 90 and day.overtime_category == "normal"
    assert day.overtime_status == "pending"


def test_missing_punch_and_absence(emp):
    from apps.attendance.models import ClockEvent
    from apps.attendance.services import process_day

    d = dt.date(2026, 10, 6)
    ClockEvent.objects.create(employee=emp, timestamp=_ts(d, 8, 0), direction="in", source="web")
    assert process_day(emp, d).status == "incomplete"
    assert process_day(emp, dt.date(2026, 10, 7)).status == "absent"
    assert process_day(emp, dt.date(2026, 10, 10)).status == "off"  # Saturday


def test_weekend_work_is_rest_day_overtime(emp):
    from apps.attendance.models import ClockEvent
    from apps.attendance.services import process_day

    d = dt.date(2026, 10, 10)  # Saturday
    ClockEvent.objects.create(employee=emp, timestamp=_ts(d, 9), direction="in", source="web")
    ClockEvent.objects.create(employee=emp, timestamp=_ts(d, 13), direction="out", source="web")
    day = process_day(emp, d)
    assert day.overtime_category == "weekend" and day.overtime_minutes == 240


def test_night_shift_crossing_midnight(emp):
    from apps.attendance.models import ClockEvent, Shift
    from apps.attendance.services import assign_shift, process_day

    night = Shift.objects.get(code="night")
    d = dt.date(2026, 10, 7)
    assign_shift(emp, d, night)
    ClockEvent.objects.create(employee=emp, timestamp=_ts(d, 20, 55), direction="in", source="biometric")
    ClockEvent.objects.create(employee=emp, timestamp=_ts(d + dt.timedelta(days=1), 7, 5), direction="out",
                              source="biometric")
    day = process_day(emp, d)
    assert day.status == "present"
    assert day.worked_minutes == 610 - 30


def test_period_summary_only_counts_approved_overtime(emp):
    from apps.attendance.models import AttendanceDay, ClockEvent
    from apps.attendance.services import approve_overtime, build_period_summary

    d = dt.date(2026, 10, 5)
    ClockEvent.objects.create(employee=emp, timestamp=_ts(d, 8), direction="in", source="web")
    ClockEvent.objects.create(employee=emp, timestamp=_ts(d, 19), direction="out", source="web")
    s = build_period_summary(d, d)[0]
    assert s.ot_normal_hours == 0
    approve_overtime(AttendanceDay.objects.get(employee=emp, date=d))
    s = build_period_summary(d, d)[0]
    assert float(s.ot_normal_hours) == 2.0


def test_hospital_credential_blocks_roster(emp):
    from apps.attendance.models import Shift
    from apps.attendance.services import assign_shift
    from apps.hospital.models import ProfessionalLicense

    jt = emp.job_title
    jt.is_clinical = True
    jt.required_license_type = "Registered General Nurse"
    jt.save()
    emp.refresh_from_db()
    shift = Shift.objects.get(code="day")
    with pytest.raises(BusinessRuleError) as exc:
        assign_shift(emp, dt.date(2026, 10, 5), shift)
    assert exc.value.code == "credential_invalid"
    ProfessionalLicense.objects.create(employee=emp, license_type="Registered General Nurse", regulator="nmc",
                                       registration_number="RGN/1", expiry_date=dt.date(2027, 1, 1), status="active")
    assign_shift(emp, dt.date(2026, 10, 5), shift)


def test_geofence(emp):
    from apps.attendance.models import AttendancePolicy
    from apps.attendance.services import clock
    from apps.organization.models import Location
    from apps.tenancy.models import OrganizationFeature

    loc = Location.objects.create(name="HQ", latitude=5.56, longitude=-0.2, geofence_radius_m=200)
    emp.location = loc
    emp.save()
    OrganizationFeature.objects.update_or_create(organization=emp.organization, code="geofence",
                                                 defaults={"enabled": True})
    AttendancePolicy.objects.update(require_geofence=True)
    with pytest.raises(BusinessRuleError):
        clock(emp, latitude=6.69, longitude=-1.62)  # Kumasi
    e = clock(emp, latitude=5.5601, longitude=-0.2001)
    assert e.within_geofence is True
