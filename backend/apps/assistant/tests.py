import copy
from types import SimpleNamespace

import pytest
from rest_framework.test import APIClient


class FakeClient:
    """Stands in for anthropic.Anthropic: replays scripted responses and records each request."""

    def __init__(self, script):
        self.script, self.calls = list(script), []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        stop, content = self.script.pop(0)
        return SimpleNamespace(stop_reason=stop, content=content,
                               usage=SimpleNamespace(input_tokens=100, output_tokens=20))


def tool_call(name, args, id_="t1"):
    return ("tool_use", [{"type": "text", "text": "Let me check."},
                         {"type": "tool_use", "id": id_, "name": name, "input": args}])


def answer(text):
    return ("end_turn", [{"type": "text", "text": text}])


@pytest.fixture
def ai(org, settings, monkeypatch, make_employee, make_user):
    from apps.assistant import services
    from apps.servicedesk.models import KnowledgeArticle
    from apps.tenancy.models import OrganizationFeature

    settings.ANTHROPIC_API_KEY = "test-key"
    OrganizationFeature.objects.update_or_create(organization=org, code="ai_assistant", defaults={"enabled": True})
    KnowledgeArticle.objects.create(title="Maternity leave policy", tags="leave maternity",
                                    body="Female employees are entitled to 12 weeks of paid maternity leave.")
    KnowledgeArticle.objects.create(title="Draft travel rules", body="maternity", is_published=False)
    emp = make_employee(first="Ama")
    holder = {}

    def use(script):
        holder["client"] = FakeClient(script)
        monkeypatch.setattr(services, "get_client", lambda: holder["client"])
        return holder["client"]

    return {"use": use, "emp": emp, "user": make_user("ama", ("employee",), employee=emp),
            "admin": make_user("sysadmin", ("sys_admin",)), "org": org}


def test_policy_answers_are_grounded_and_minimal(ai):
    from apps.assistant.models import Message

    fake = ai["use"]([tool_call("search_policies", {"query": "maternity leave"}),
                      answer("You get 12 weeks of paid maternity leave (Maternity leave policy).")])
    c = APIClient()
    c.force_authenticate(ai["user"])
    r = c.post("/api/assistant/ask/", {"message": "How long is maternity leave? My Ghana Card is GHA-123456789-0 "
                                                  "and phone 0244123456"}, format="json")
    assert r.status_code == 200, r.content
    msg = r.json()["message"]
    assert "12 weeks" in msg["text"] and msg["sources"][0]["title"] == "Maternity leave policy"
    first = fake.calls[0]
    # policies mode: only the policy tool is offered and identifiers never leave the server
    assert [t["name"] for t in first["tools"]] == ["search_policies"] and first["tools"][0]["strict"] is True
    sent = first["messages"][0]["content"][0]["text"]
    assert "GHA-123456789-0" not in sent and "0244123456" not in sent and "[Ghana Card number]" in sent
    assert first["model"] == "claude-opus-5-5" and first["fallbacks"] == "default"
    # unpublished articles are never retrieved; the tool result is replayed to the model
    tool_result = fake.calls[1]["messages"][-1]["content"][0]
    assert tool_result["type"] == "tool_result" and "Draft travel rules" not in tool_result["content"]
    # the conversation is private: another user cannot read it, even an administrator
    conv = r.json()["conversation"]
    assert c.get(f"/api/assistant/conversations/{conv}/").json()["messages"][-1]["text"] == msg["text"]
    c.force_authenticate(ai["admin"])
    assert c.get(f"/api/assistant/conversations/{conv}/").status_code == 404
    usage = c.get("/api/assistant/settings/").json()["usage"]
    assert usage["questions"] == 1 and "text" not in str(usage)
    assert Message.objects.filter(role="assistant").exclude(text="").count() == 1


def test_personal_tools_follow_permissions(ai):
    from apps.assistant import tools

    ai["org"].settings = {"ai_assistant": {"mode": "hr_data"}}
    ai["org"].save()
    names = {t["name"] for t in tools.available(ai["user"], "hr_data")}
    assert {"my_leave_balances", "my_profile", "my_latest_payslip"} <= names
    assert "headcount" not in names and "team_on_leave" not in names     # plain employees get no reports
    with pytest.raises(PermissionError):
        tools.run("headcount", {"group_by": "department"}, ai["user"], "hr_data")
    # a model asking for a tool the user cannot use gets an error result, not data
    fake = ai["use"]([tool_call("headcount", {"group_by": "gender"}), answer("I can't see that.")])
    c = APIClient()
    c.force_authenticate(ai["user"])
    r = c.post("/api/assistant/ask/", {"message": "How many staff by gender?"}, format="json")
    assert r.status_code == 200
    result = fake.calls[1]["messages"][-1]["content"][0]
    assert result["is_error"] is True and r.json()["message"]["tools_used"] == []
    profile, _ = tools.run("my_profile", {}, ai["user"], "hr_data")
    assert profile["name"] == ai["emp"].full_name and "ghana_card_no" not in profile


def test_guardrails_feature_flag_limits_and_refusals(ai):
    from apps.assistant.models import Conversation
    from apps.tenancy.models import OrganizationFeature

    c = APIClient()
    c.force_authenticate(ai["user"])
    ai["use"]([("refusal", [])])
    r = c.post("/api/assistant/ask/", {"message": "something unsafe"}, format="json")
    assert "can't help" in r.json()["message"]["text"]
    # API failures roll the turn back instead of leaving half a conversation
    import anthropic

    def boom(**kw):
        raise anthropic.APIConnectionError(request=None)
    fake = ai["use"]([])
    fake.beta.messages.create = boom
    before = Conversation.objects.count()
    r = c.post("/api/assistant/ask/", {"message": "hello"}, format="json")
    assert r.status_code == 400 and r.json()["code"] == "ai_unavailable" and Conversation.objects.count() == before
    # daily limit (counted per user)
    ai["org"].settings = {"ai_assistant": {"daily_limit": 1}}
    ai["org"].save()
    ai["use"]([answer("hi")])
    assert c.post("/api/assistant/ask/", {"message": "again"}, format="json").json()["code"] == "ai_limit"
    # feature switched off
    OrganizationFeature.objects.filter(code="ai_assistant").update(enabled=False)
    r = c.post("/api/assistant/ask/", {"message": "hi"}, format="json")
    assert r.json()["code"] == "ai_disabled"
    assert c.get("/api/assistant/status/").json()["available"] is False
    # only administrators change the settings
    assert c.patch("/api/assistant/settings/", {"mode": "hr_data"}, format="json").status_code == 403
    c.force_authenticate(ai["admin"])
    assert c.patch("/api/assistant/settings/", {"mode": "nonsense"}, format="json").status_code == 400
    assert c.patch("/api/assistant/settings/", {"mode": "hr_data", "daily_limit": 20},
                   format="json").json()["settings"]["mode"] == "hr_data"


def test_redaction_and_purge(ai):
    import datetime as dt

    from django.utils import timezone

    from apps.assistant import services
    from apps.assistant.models import Conversation

    assert services.redact("SSNIT C123456789012, acct 1234567890123, mail a@b.com") == \
        "SSNIT [SSNIT number], acct [account number], mail [email]"
    old = Conversation.objects.create(user=ai["user"], title="old")
    Conversation.objects.filter(pk=old.pk).update(updated_at=timezone.now() - dt.timedelta(days=200))
    Conversation.objects.create(user=ai["user"], title="new")
    assert services.purge() == 1 and Conversation.objects.filter(title="new").exists()
