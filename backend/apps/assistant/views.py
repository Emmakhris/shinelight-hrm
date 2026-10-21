from rest_framework import mixins, serializers, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit import services as audit
from apps.core.exceptions import BusinessRuleError
from apps.rbac.permissions import require

from . import services
from .models import Conversation, Message


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = ["id", "role", "text", "sources", "tools_used", "helpful", "created_at"]


class ConversationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Conversation
        fields = ["id", "title", "created_at", "updated_at"]


class ConversationViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.DestroyModelMixin,
                          viewsets.GenericViewSet):
    """The signed-in user's own conversations only. Nobody else, including HR or admins, can read them."""

    serializer_class = ConversationSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        return Conversation.objects.filter(user=self.request.user)

    def retrieve(self, request, *args, **kwargs):
        c = self.get_object()
        msgs = c.messages.exclude(role="tool").exclude(text="")
        return Response({**ConversationSerializer(c).data, "messages": MessageSerializer(msgs, many=True).data})


class StatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(services.status(request.user))


class AskView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        conv = None
        if request.data.get("conversation"):
            conv = Conversation.objects.filter(pk=request.data["conversation"], user=request.user).first()
            if conv is None:
                raise BusinessRuleError("Conversation not found.", code="ai_not_found")
        msg = services.ask(request.user, str(request.data.get("message", "")), conv)
        return Response({"conversation": msg.conversation_id, "title": msg.conversation.title,
                         "message": MessageSerializer(msg).data})


class FeedbackView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        msg = Message.objects.filter(pk=pk, conversation__user=request.user, role="assistant").first()
        if msg is None:
            raise BusinessRuleError("Message not found.", code="ai_not_found")
        msg.helpful = bool(request.data.get("helpful"))
        msg.feedback = str(request.data.get("note", ""))[:2000]
        msg.save(update_fields=["helpful", "feedback"])
        return Response({"ok": True})


class SettingsView(APIView):
    """Administrator settings and usage statistics (counts only, never conversation content)."""

    permission_classes = [IsAuthenticated, require("admin.settings")]

    def get(self, request):
        org = request.user.organization
        return Response({"settings": services.config(org), "modes": services.MODES,
                         "enabled": org.has_feature("ai_assistant"), "configured": services.configured(),
                         "usage": services.usage()})

    def patch(self, request):
        org = request.user.organization
        cfg = services.config(org)
        data = request.data
        if "mode" in data:
            if data["mode"] not in services.MODES:
                raise BusinessRuleError("Unknown mode.")
            cfg["mode"] = data["mode"]
        for key, lo, hi in (("daily_limit", 1, 500), ("retention_days", 1, 730)):
            if key in data:
                v = int(data[key])
                if not lo <= v <= hi:
                    raise BusinessRuleError(f"{key.replace('_', ' ').capitalize()} must be between {lo} and {hi}.")
                cfg[key] = v
        if data.get("model"):
            cfg["model"] = str(data["model"])[:60]
        org.settings = {**(org.settings or {}), "ai_assistant": cfg}
        org.save(update_fields=["settings"])
        audit.log("config", org, {"ai_assistant": cfg}, object_repr="AI assistant settings")
        return self.get(request)
