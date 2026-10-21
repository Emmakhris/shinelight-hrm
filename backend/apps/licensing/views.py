from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.rbac.permissions import require

from . import services


class LicenceStatusView(APIView):
    """Banner information for any signed-in user: no licence details beyond what they need to see."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        s = services.state()
        return Response({k: s.get(k) for k in ("state", "read_only", "message", "days_left")})


class LicenceView(APIView):
    """Administrators: view the installed licence and install a renewal (paste or upload the file's text)."""

    permission_classes = [IsAuthenticated, require("admin.settings")]

    def get(self, request):
        from apps.employees.models import ACTIVE_STATUSES, Employee

        s = services.state(refresh=True)
        return Response({**s, "active_employees": Employee.objects.filter(status__in=ACTIVE_STATUSES).count(),
                         "evaluation_limit": services.EVALUATION_EMPLOYEES})

    def post(self, request):
        upload = request.FILES.get("file")
        text = upload.read().decode("utf-8", errors="replace") if upload else str(request.data.get("licence", ""))
        services.install(text, request.user)
        return self.get(request)
