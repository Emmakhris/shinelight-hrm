"""Governed HR assistant backed by Claude (features.txt section 29).

Governance built in:
- Off unless the organization enables the `ai_assistant` feature and the server has an Anthropic API key.
- Permission-aware retrieval: the model only receives what `tools.py` returns for the signed-in user.
- Data minimisation: in "policies" mode no personal data leaves the server; identifiers typed by the user
  (Ghana Card, SSNIT, phone, email, account numbers) are redacted before anything is sent.
- Human in the loop: the assistant cannot change records or decide anything; it points to the right page.
- Every answer lists its sources; conversations are private to the user and purged after a retention period;
  usage (not content) is audit-logged.
"""

import datetime as dt
import logging
import re

from django.conf import settings
from django.db.models import Sum
from django.utils import timezone

from apps.audit import services as audit
from apps.core.exceptions import BusinessRuleError

from . import tools
from .models import Conversation, Message

log = logging.getLogger(__name__)

DEFAULTS = {"mode": "policies", "model": "claude-opus-5-5", "daily_limit": 40, "retention_days": 90}
MODES = {"policies": "Approved policies only", "hr_data": "Policies plus the user's own records and reports"}
MAX_TOOL_ROUNDS = 6
DISCLAIMER = ("AI answers can be wrong. Check the linked policy or ask HR before acting. The assistant cannot make "
              "or change decisions about pay, hiring, promotion, discipline or dismissal.")

REDACTIONS = [
    (re.compile(r"\bGHA-?\d{9}-?\d\b", re.I), "[Ghana Card number]"),
    (re.compile(r"\b[A-Z]\d{12}\b"), "[SSNIT number]"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[email]"),
    (re.compile(r"(?:\+233|\b0)\s?\d{2}\s?\d{3}\s?\d{4}\b"), "[phone number]"),
    (re.compile(r"\b\d{10,16}\b"), "[account number]"),
]


def redact(text):
    for pattern, label in REDACTIONS:
        text = pattern.sub(label, text)
    return text


def config(org):
    return {**DEFAULTS, **((org.settings or {}).get("ai_assistant") or {})}


def configured():
    return bool(getattr(settings, "ANTHROPIC_API_KEY", ""))


def status(user):
    org = user.organization
    enabled = bool(org and org.has_feature("ai_assistant"))
    cfg = config(org) if org else DEFAULTS
    return {"enabled": enabled, "configured": configured(), "available": enabled and configured(),
            "mode": cfg["mode"], "mode_label": MODES.get(cfg["mode"], cfg["mode"]),
            "daily_limit": cfg["daily_limit"], "used_today": used_today(user), "disclaimer": DISCLAIMER}


def used_today(user):
    start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    return Message.objects.filter(conversation__user=user, role="user", created_at__gte=start).count()


def get_client():
    import anthropic

    return anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY, timeout=90.0, max_retries=2)


def system_prompt(user, cfg):
    org = user.organization
    employee = getattr(user, "employee", None)
    who = f"{employee.full_name}, {employee.job_title.name if employee and employee.job_title_id else 'staff'}" \
        if employee else user.get_full_name() or user.username
    scope = ("You can only search the organization's approved HR policies and knowledge base."
             if cfg["mode"] == "policies" else
             "You can search approved HR policies and read the user's own HR records and, where their access "
             "allows, aggregate reports. Tools return only what this user is already allowed to see.")
    return f"""You are the HR assistant inside ShineLight HRM for {org.name}, an organization in Ghana.
Today is {dt.date.today():%d %B %Y}. You are speaking with {who}.

{scope}

Rules:
- For any question about rules, entitlements or procedures, call search_policies first and answer only from
  the articles it returns. Name the article you relied on. If nothing relevant is found, say so plainly and
  suggest raising a request with the HR service desk; never guess a policy or quote Ghanaian law from memory.
- Use the personal-data tools only for the user's own questions; never speculate about other employees.
- You cannot submit, approve or change anything. When the user wants to act, tell them which page to use
  (for example "Leave > Apply") and what to fill in.
- Never make, recommend or predict decisions about hiring, dismissal, promotion, discipline or pay. You may
  explain the process and who decides.
- If the user asks you to draft a letter or email, label it "Draft for review" and keep it neutral.
- Be concise and friendly. Use GHS for money and DD/MM/YYYY for dates."""


def _title(text):
    return (text[:60] + "...") if len(text) > 63 else text


def _blocks(content):
    return [b.model_dump(mode="json", by_alias=True, exclude_none=True) if hasattr(b, "model_dump") else b for b in content]


def ask(user, text, conversation=None):
    """Answer one user message. Returns the assistant Message."""
    org = user.organization
    if not org or not org.has_feature("ai_assistant"):
        raise BusinessRuleError("The AI assistant is not enabled for your organization.", code="ai_disabled")
    if not configured():
        raise BusinessRuleError("The AI assistant is not configured on this server.", code="ai_not_configured")
    cfg = config(org)
    text = (text or "").strip()
    if not text:
        raise BusinessRuleError("Type a question.", code="ai_empty")
    if len(text) > 4000:
        raise BusinessRuleError("Please keep questions under 4,000 characters.", code="ai_too_long")
    if used_today(user) >= int(cfg["daily_limit"]):
        raise BusinessRuleError("You have reached today's limit for the assistant. Try again tomorrow.",
                                code="ai_limit")
    if conversation is not None and conversation.user_id != user.id:
        raise BusinessRuleError("Conversation not found.", code="ai_not_found")
    new = conversation is None
    if new:
        conversation = Conversation.objects.create(user=user, title=_title(redact(text)))
    started = timezone.now()
    try:
        return _answer(user, cfg, conversation, redact(text))
    except BusinessRuleError:
        # keep the stored transcript well-formed: drop this turn (and an empty new conversation)
        if new:
            conversation.delete()
        else:
            conversation.messages.filter(created_at__gte=started).delete()
        raise


def _answer(user, cfg, conversation, safe):
    Message.objects.create(conversation=conversation, role="user", content=[{"type": "text", "text": safe}],
                           text=safe)
    history = [{"role": "assistant" if m.role == "assistant" else "user", "content": m.content}
               for m in conversation.messages.all()]
    tool_defs = tools.available(user, cfg["mode"])
    client = get_client()
    used, sources, tokens_in, tokens_out = [], [], 0, 0
    reply = None
    for _ in range(MAX_TOOL_ROUNDS):
        response = _call(client, cfg, system_prompt(user, cfg), history, tool_defs)
        tokens_in += getattr(response.usage, "input_tokens", 0) or 0
        tokens_out += getattr(response.usage, "output_tokens", 0) or 0
        content = _blocks(response.content)
        if response.stop_reason == "refusal":
            reply = "I can't help with that request. For HR matters, please contact the HR service desk."
            content = [{"type": "text", "text": reply}]
            break
        history.append({"role": "assistant", "content": content})
        calls = [b for b in content if b.get("type") == "tool_use"]
        if response.stop_reason != "tool_use" or not calls:
            reply = "\n\n".join(b["text"] for b in content if b.get("type") == "text").strip()
            if response.stop_reason == "max_tokens":
                reply += "\n\n(The answer was cut short. Please ask a narrower question.)"
            break
        Message.objects.create(conversation=conversation, role="assistant", content=content,
                               text="", tools_used=[c["name"] for c in calls])
        results = []
        for c in calls:
            try:
                result, src = tools.run(c["name"], c.get("input"), user, cfg["mode"])
                used.append(c["name"])
                sources += [s for s in src if s not in sources]
                results.append({"type": "tool_result", "tool_use_id": c["id"], "content": tools.as_json(result)})
            except PermissionError as exc:
                results.append({"type": "tool_result", "tool_use_id": c["id"], "content": str(exc),
                                "is_error": True})
            except Exception:  # a failing tool must not break the conversation
                log.exception("Assistant tool %s failed", c["name"])
                results.append({"type": "tool_result", "tool_use_id": c["id"],
                                "content": "The tool failed. Tell the user the information is unavailable.",
                                "is_error": True})
        history.append({"role": "user", "content": results})
        Message.objects.create(conversation=conversation, role="tool", content=results)
    else:
        reply = "I couldn't complete that within the allowed steps. Please try a simpler question."
        content = [{"type": "text", "text": reply}]
    msg = Message.objects.create(conversation=conversation, role="assistant", content=content, text=reply or "",
                                 tools_used=used, sources=sources, input_tokens=tokens_in, output_tokens=tokens_out)
    conversation.save(update_fields=["updated_at"])
    audit.log("ai", conversation, {"tools": used, "input_tokens": tokens_in, "output_tokens": tokens_out,
                                   "mode": cfg["mode"]}, object_repr="AI assistant query")
    return msg


def _call(client, cfg, system, history, tool_defs):
    import anthropic

    kwargs = {"model": cfg["model"], "max_tokens": 16000, "system": system, "messages": history,
              "output_config": {"effort": "medium"}}
    if tool_defs:
        kwargs["tools"] = tool_defs
    try:
        return client.beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs)
    except anthropic.RateLimitError as exc:
        raise BusinessRuleError("The assistant is busy. Please try again in a minute.", code="ai_busy") from exc
    except (anthropic.APIStatusError, anthropic.APIConnectionError) as exc:
        log.warning("Anthropic API error: %s", exc)
        raise BusinessRuleError("The assistant is temporarily unavailable.", code="ai_unavailable") from exc


def usage(days=30):
    """Usage for administrators: counts, tokens and feedback only - never conversation content."""
    since = timezone.now() - dt.timedelta(days=days)
    msgs = Message.objects.filter(created_at__gte=since)
    answers = msgs.filter(role="assistant").exclude(text="")
    tok = answers.aggregate(i=Sum("input_tokens"), o=Sum("output_tokens"))
    rated = answers.exclude(helpful__isnull=True)
    return {"days": days, "questions": msgs.filter(role="user").count(),
            "users": msgs.values("conversation__user").distinct().count(),
            "input_tokens": tok["i"] or 0, "output_tokens": tok["o"] or 0,
            "rated": rated.count(), "helpful": rated.filter(helpful=True).count(),
            "unanswered": answers.filter(sources=[]).count()}


def purge(today=None):
    """Delete conversations older than each organization's retention period."""
    from apps.tenancy.models import Organization

    n = 0
    for org in Organization.objects.filter(is_active=True):
        cutoff = timezone.now() - dt.timedelta(days=int(config(org)["retention_days"]))
        n += Conversation.all_objects.filter(organization=org, updated_at__lt=cutoff).delete()[0]
    return n
