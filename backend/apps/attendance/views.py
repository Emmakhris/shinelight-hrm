import datetime as dt

from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import BusinessRuleError
from apps.core.exports import tabular_response
from apps.core.middleware import client_ip
from apps.core.serializers import TenantSerializer
from apps.core.views import TenantModelViewSet
from apps.employees.models import ACTIVE_STATUSES, Employee
from apps.rbac.services import can_access_employee, has_perm, scope_queryset

from . import services
from .models import (
    AttendanceCorrection,
    AttendanceDay,
    AttendancePeriodSummary,
    AttendancePolicy,
    BiometricDevice,
    BiometricEnrollment,
    ClockEvent,
    RosterEntry,
    Shift,
    ShiftPattern,
)


def ser(model_cls, extra=None, read_only=()):
    meta = type("Meta", (TenantSerializer.Meta,), {"model": model_cls,
                                                   "read_only_fields": TenantSerializer.Meta.read_only_fields
                                                   + list(read_only)})
    return type(f"{model_cls.__name__}Serializer", (TenantSerializer,), {"Meta": meta, **(extra or {})})


class ConfigViewSet(TenantModelViewSet):
    perm_module = "attendance"
    perm_write = "attendance.manage"
    pagination_class = None


class ShiftViewSet(ConfigViewSet):
    queryset = Shift.objects.all()
    serializer_class = ser(Shift, {"scheduled_minutes": serializers.IntegerField(read_only=True),
                                   "crosses_midnight": serializers.BooleanField(read_only=True)})
    perm_map = {"list": None, "retrieve": None}


class PolicyViewSet(ConfigViewSet):
    queryset = AttendancePolicy.objects.select_related("default_shift")
    serializer_class = ser(AttendancePolicy)
    perm_read = "attendance.manage"


class PatternViewSet(ConfigViewSet):
    queryset = ShiftPattern.objects.all()
    serializer_class = ser(ShiftPattern)


class DeviceViewSet(ConfigViewSet):
    queryset = BiometricDevice.objects.select_related("location")
    serializer_class = ser(BiometricDevice, read_only=["last_sync_at", "last_sync_status", "last_record_at"])
    perm_read = "attendance.manage"

    @action(detail=True, methods=["post"])
    def sync(self, request, pk=None):
        from .zk import sync_device

        return Response(sync_device(self.get_object()))


class EnrollmentViewSet(ConfigViewSet):
    queryset = BiometricEnrollment.objects.select_related("employee")
    serializer_class = ser(BiometricEnrollment, {"employee_name": serializers.CharField(source="employee.full_name",
                                                                                         read_only=True)})
    perm_read = "attendance.manage"
    filterset_fields = ["employee"]


class RosterSerializer(TenantSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    shift_name = serializers.CharField(source="shift.name", read_only=True, default=None)
    shift_color = serializers.CharField(source="shift.color", read_only=True, default=None)

    class Meta(TenantSerializer.Meta):
        model = RosterEntry


class RosterViewSet(TenantModelViewSet):
    queryset = RosterEntry.objects.select_related("employee", "shift")
    serializer_class = RosterSerializer
    perm_module = "attendance"
    perm_write = "attendance.manage"
    scope_prefix = "employee__"
    filterset_fields = ["employee", "shift", "department", "is_published"]
    pagination_class = None

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        if p.get("start"):
            qs = qs.filter(date__gte=p["start"])
        if p.get("end"):
            qs = qs.filter(date__lte=p["end"])
        if p.get("employee__department"):
            qs = qs.filter(employee__department=p["employee__department"])
        if not has_perm(self.request.user, "attendance.manage"):
            qs = qs.filter(is_published=True)  # staff and managers only see published rosters
        return qs

    def perform_create(self, serializer):
        d = serializer.validated_data
        if d.get("shift"):
            services._check_credentials(d["employee"], d["shift"], d["date"])
        serializer.save()

    def perform_update(self, serializer):
        d = serializer.validated_data
        shift = d.get("shift", serializer.instance.shift)
        if shift:
            services._check_credentials(d.get("employee", serializer.instance.employee), shift,
                                        d.get("date", serializer.instance.date))
        serializer.save()

    @action(detail=False, methods=["post"])
    def generate(self, request):
        pattern = ShiftPattern.objects.get(pk=request.data["pattern"])
        emps = Employee.objects.filter(pk__in=request.data.get("employees", []))
        n = services.generate_roster(emps, pattern, dt.date.fromisoformat(request.data["start"]),
                                     dt.date.fromisoformat(request.data["end"]), int(request.data.get("offset", 0)),
                                     int(request.data.get("stagger", 0)), bool(request.data.get("overwrite")))
        return Response({"created": n})

    @action(detail=False, methods=["post"])
    def publish(self, request):
        qs = RosterEntry.objects.filter(date__range=(request.data["start"], request.data["end"]))
        if request.data.get("department"):
            qs = qs.filter(employee__department=request.data["department"])
        n = qs.update(is_published=True)
        return Response({"published": n})

    @action(detail=False)
    def staffing(self, request):
        """Ward/department staffing by date and shift (incl. emergency availability)."""
        start = dt.date.fromisoformat(request.query_params.get("start", dt.date.today().isoformat()))
        end = dt.date.fromisoformat(request.query_params.get("end", start.isoformat()))
        qs = self.get_queryset().filter(date__range=(start, end), shift__isnull=False)
        out = {}
        for r in qs.select_related("shift", "employee__department"):
            dept = (r.department or r.employee.department)
            key = (r.date.isoformat(), dept.name if dept else "-", r.shift.name)
            out.setdefault(key, []).append(r.employee.full_name)
        return Response([{"date": k[0], "department": k[1], "shift": k[2], "count": len(v), "staff": v}
                         for k, v in sorted(out.items())])


class ClockView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        emp = getattr(request.user, "employee", None)
        if emp is None:
            return Response({"events": [], "can_clock": False})
        today = timezone.localdate()
        start = timezone.make_aware(dt.datetime.combine(today, dt.time.min))
        events = ClockEvent.objects.filter(employee=emp, timestamp__gte=start - dt.timedelta(hours=12), is_void=False)
        last = events.order_by("-timestamp").first()
        shift, _, _ = services.scheduled_shift(emp, today)
        return Response({"can_clock": True, "next_direction": "out" if last and last.direction == "in" else "in",
                         "shift": str(shift) if shift else None,
                         "events": [{"timestamp": e.timestamp, "direction": e.direction, "source": e.source,
                                     "within_geofence": e.within_geofence} for e in events.order_by("timestamp")]})

    def post(self, request):
        emp = getattr(request.user, "employee", None)
        if emp is None:
            raise BusinessRuleError("Your account is not linked to an employee record.")
        e = services.clock(emp, source=request.data.get("source", "web"), direction=request.data.get("direction", "auto"),
                           latitude=request.data.get("latitude"), longitude=request.data.get("longitude"),
                           ip=client_ip(request))
        return Response({"timestamp": e.timestamp, "direction": e.direction, "within_geofence": e.within_geofence},
                        status=201)


class DaySerializer(TenantSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    staff_number = serializers.CharField(source="employee.staff_number", read_only=True)
    shift_name = serializers.CharField(source="shift.name", read_only=True, default=None)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta(TenantSerializer.Meta):
        model = AttendanceDay


class DayViewSet(TenantModelViewSet):
    queryset = AttendanceDay.objects.select_related("employee", "shift")
    serializer_class = DaySerializer
    perm_module = "attendance"
    scope_prefix = "employee__"
    http_method_names = ["get", "post"]
    filterset_fields = ["employee", "status", "is_exception", "overtime_status", "employee__department", "date"]
    perm_map = {"process": "attendance.manage", "approve_overtime": "attendance.approve", "export": "attendance.view",
                "create": "attendance.manage"}

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        if p.get("start"):
            qs = qs.filter(date__gte=p["start"])
        if p.get("end"):
            qs = qs.filter(date__lte=p["end"])
        return qs

    @action(detail=False, methods=["post"])
    def process(self, request):
        start = dt.date.fromisoformat(request.data["start"])
        end = dt.date.fromisoformat(request.data.get("end", request.data["start"]))
        emps = None
        if request.data.get("employee"):
            emps = Employee.objects.filter(pk=request.data["employee"])
        return Response({"processed": services.process_range(start, end, emps)})

    @action(detail=False, methods=["post"], url_path="approve-overtime")
    def approve_overtime(self, request):
        approve = request.data.get("approve", True)
        done = 0
        for day in AttendanceDay.objects.filter(pk__in=request.data.get("ids", [])).select_related("employee"):
            if day.employee == getattr(request.user, "employee", None):
                continue  # cannot approve own overtime
            if can_access_employee(request.user, "attendance.approve", day.employee):
                services.approve_overtime(day, approve=bool(approve))
                done += 1
        return Response({"updated": done})

    @action(detail=False)
    def export(self, request):
        qs = self.filter_queryset(self.get_queryset()).order_by("employee__staff_number", "date")
        headers = ["Staff No", "Name", "Date", "Shift", "In", "Out", "Worked (h)", "Late (min)", "Early leave (min)",
                   "OT (h)", "OT category", "OT status", "Status"]
        tz = timezone.get_current_timezone()
        rows = [[d.employee.staff_number, d.employee.full_name, d.date.strftime("%d/%m/%Y"),
                 d.shift.name if d.shift else "", d.first_in.astimezone(tz).strftime("%H:%M") if d.first_in else "",
                 d.last_out.astimezone(tz).strftime("%H:%M") if d.last_out else "", round(d.worked_minutes / 60, 2),
                 d.late_minutes, d.early_leave_minutes, round(d.overtime_minutes / 60, 2), d.overtime_category,
                 d.overtime_status, d.get_status_display()] for d in qs[:20000]]
        return tabular_response(headers, rows, "timesheet", request.query_params.get("format", "xlsx"), "Timesheet")


class CorrectionSerializer(TenantSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)

    class Meta(TenantSerializer.Meta):
        model = AttendanceCorrection
        read_only_fields = TenantSerializer.Meta.read_only_fields + ["status", "employee"]

    def validate(self, attrs):
        if not attrs.get("clock_in") and not attrs.get("clock_out"):
            raise serializers.ValidationError("Provide a corrected clock-in and/or clock-out time.")
        if attrs.get("date") and attrs["date"] > dt.date.today():
            raise serializers.ValidationError("You cannot correct a future date.")
        return attrs


class CorrectionViewSet(TenantModelViewSet):
    queryset = AttendanceCorrection.objects.select_related("employee")
    serializer_class = CorrectionSerializer
    perm_module = "attendance"
    scope_prefix = "employee__"
    http_method_names = ["get", "post"]
    perm_map = {"create": None}
    filterset_fields = ["status", "employee"]

    def perform_create(self, serializer):
        from apps.workflow import engine

        emp = getattr(self.request.user, "employee", None)
        if emp is None:
            raise BusinessRuleError("Your account is not linked to an employee record.")
        day = AttendanceDay.objects.filter(employee=emp, date=serializer.validated_data["date"]).first()
        if day and day.locked:
            raise BusinessRuleError("Attendance for that date is locked (payroll closed).")
        corr = serializer.save(employee=emp)
        engine.start(corr, "attendance_correction", self.request.user, subject_employee=emp)


class SummarySerializer(TenantSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    staff_number = serializers.CharField(source="employee.staff_number", read_only=True)

    class Meta(TenantSerializer.Meta):
        model = AttendancePeriodSummary


class SummaryViewSet(TenantModelViewSet):
    queryset = AttendancePeriodSummary.objects.select_related("employee")
    serializer_class = SummarySerializer
    perm_module = "attendance"
    scope_prefix = "employee__"
    http_method_names = ["get", "post"]
    perm_map = {"build": "attendance.manage"}
    filterset_fields = ["period_start", "period_end", "locked", "employee"]

    @action(detail=False, methods=["post"])
    def build(self, request):
        start = dt.date.fromisoformat(request.data["start"])
        end = dt.date.fromisoformat(request.data["end"])
        summaries = services.build_period_summary(start, end, lock=bool(request.data.get("lock")))
        return Response({"employees": len(summaries)})


class TeamTodayView(APIView):
    """Manager view: who is in, late, absent or on leave today."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.leave.services import on_leave_on

        today = timezone.localdate()
        team = scope_queryset(request.user, Employee.objects.filter(status__in=ACTIVE_STATUSES), "attendance.view")
        if not request.user.is_superuser and not has_perm(request.user, "attendance.approve"):
            return Response([])
        on_leave = set(on_leave_on(today).filter(employee__in=team).values_list("employee_id", flat=True))
        rows = []
        for emp in team.select_related("department")[:500]:
            first = ClockEvent.objects.filter(employee=emp, timestamp__date=today, is_void=False).order_by("timestamp").first()
            shift, _, _ = services.scheduled_shift(emp, today)
            if emp.id in on_leave:
                state = "on_leave"
            elif first is None:
                state = "not_in" if shift else "off"
            else:
                state = "in"
                if shift:
                    start, _ = services.shift_window(shift, today)
                    if (first.timestamp - start).total_seconds() / 60 > shift.grace_in_minutes:
                        state = "late"
            rows.append({"employee": emp.id, "name": emp.full_name, "department": emp.department.name if emp.department_id
                         else "", "state": state, "first_in": first.timestamp if first else None,
                         "shift": shift.name if shift else None})
        return Response(rows)
