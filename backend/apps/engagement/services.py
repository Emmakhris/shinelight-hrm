"""Engagement: surveys with confidentiality controls, recognition, suggestions and welfare events (features.txt §16).

Survey results are only ever shown for groups of at least `min_group_size` respondents, comments are shuffled and
never attributed, and anonymous responses are stored without any link to the person (participation is tracked
separately on the invite)."""

import datetime as dt
import random
from collections import defaultdict

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.core.exceptions import BusinessRuleError
from apps.employees.models import Employee

from .models import Event, Recognition, Suggestion, Survey, SurveyInvite, SurveyResponse

QUESTION_TYPES = ("rating", "enps", "text", "choice")
RISK_DIMENSIONS = ("workload", "burnout", "wellbeing")
RISK_THRESHOLD = 30  # % unfavourable above which a group is flagged


def _notify(users, title, body, link):
    from apps.notifications.services import notify

    users = [u for u in users if u is not None]
    if users:
        notify("generic", users, {"title": title, "body": body, "link": link}, channels=("in_app", "email"))


def validate_questions(questions):
    if not questions:
        raise BusinessRuleError("Add at least one question.")
    keys = set()
    for q in questions:
        if not q.get("key") or not q.get("text") or q.get("type") not in QUESTION_TYPES:
            raise BusinessRuleError("Each question needs a key, text and a type (rating, enps, text, choice).")
        if q["key"] in keys:
            raise BusinessRuleError(f"Duplicate question key '{q['key']}'.")
        if q["type"] == "choice" and len(q.get("options") or []) < 2:
            raise BusinessRuleError(f"'{q['text']}' needs at least two options.")
        keys.add(q["key"])


def audience(survey):
    qs = Employee.objects.filter(status__in=["active", "probation"])
    if survey.departments.exists():
        from apps.rbac.services import department_descendants

        ids = set()
        for d in survey.departments.all():
            ids.update(department_descendants(d.id))
        qs = qs.filter(department_id__in=ids)
    return qs


@transaction.atomic
def launch(survey: Survey, user):
    if survey.status != "draft":
        raise BusinessRuleError("Only draft surveys can be launched.")
    validate_questions(survey.questions)
    if survey.min_group_size < 3:
        raise BusinessRuleError("The minimum reporting group must be at least 3 to protect anonymity.")
    people = list(audience(survey).select_related("user"))
    for emp in people:
        SurveyInvite.objects.get_or_create(survey=survey, employee=emp)
    survey.status = "open"
    survey.opens_on = survey.opens_on or dt.date.today()
    survey.save(update_fields=["status", "opens_on", "updated_at"])
    _notify([e.user for e in people], f"Survey: {survey.title}",
            ("Your answers are anonymous. " if survey.anonymous else "") + "It takes a few minutes. Thank you!",
            "/engagement")
    return len(people)


def respond(survey: Survey, user, answers: dict):
    emp = getattr(user, "employee", None)
    invite = SurveyInvite.objects.filter(survey=survey, employee=emp).first() if emp else None
    if invite is None:
        raise PermissionDenied("You are not invited to this survey.")
    if survey.status != "open" or (survey.closes_on and survey.closes_on < dt.date.today()):
        raise BusinessRuleError("This survey is closed.")
    if invite.responded:
        raise BusinessRuleError("You have already responded. Thank you!")
    clean = {}
    for q in survey.questions:
        v = (answers or {}).get(q["key"])
        if v in (None, ""):
            if q.get("required", q["type"] != "text"):
                raise BusinessRuleError(f"Please answer: {q['text']}")
            continue
        if q["type"] == "rating":
            v = int(v)
            if not 1 <= v <= 5:
                raise BusinessRuleError("Ratings are 1 to 5.")
        elif q["type"] == "enps":
            v = int(v)
            if not 0 <= v <= 10:
                raise BusinessRuleError("Score 0 to 10.")
        elif q["type"] == "choice" and v not in q.get("options", []):
            raise BusinessRuleError(f"Choose one of the options for: {q['text']}")
        elif q["type"] == "text":
            v = str(v)[:2000]
        clean[q["key"]] = v
    with transaction.atomic():
        SurveyResponse.objects.create(survey=survey, answers=clean, submitted_on=dt.date.today(),
                                      department=emp.department, employee=None if survey.anonymous else emp)
        invite.responded = True
        invite.save(update_fields=["responded", "updated_at"])
    return True


def close(survey: Survey):
    survey.status = "closed"
    survey.closes_on = survey.closes_on or dt.date.today()
    survey.save(update_fields=["status", "closes_on", "updated_at"])
    return survey


def _summarise(questions, answers_list):
    out, dims = [], defaultdict(lambda: [0, 0, 0])  # favourable, neutral, unfavourable
    for q in questions:
        vals = [a[q["key"]] for a in answers_list if q["key"] in a]
        item = {"key": q["key"], "text": q["text"], "type": q["type"], "dimension": q.get("dimension", ""),
                "responses": len(vals)}
        if q["type"] == "rating" and vals:
            fav = sum(1 for v in vals if v >= 4)
            unf = sum(1 for v in vals if v <= 2)
            item.update({"average": round(sum(vals) / len(vals), 2), "favourable": round(100 * fav / len(vals)),
                         "unfavourable": round(100 * unf / len(vals)),
                         "distribution": {str(i): vals.count(i) for i in range(1, 6)}})
            if q.get("dimension"):
                d = dims[q["dimension"]]
                d[0] += fav
                d[1] += len(vals) - fav - unf
                d[2] += unf
        elif q["type"] == "enps" and vals:
            promoters = sum(1 for v in vals if v >= 9)
            detractors = sum(1 for v in vals if v <= 6)
            item.update({"enps": round(100 * (promoters - detractors) / len(vals)),
                         "distribution": {str(i): vals.count(i) for i in range(0, 11)}})
        elif q["type"] == "choice":
            item["counts"] = {o: vals.count(o) for o in q.get("options", [])}
        elif q["type"] == "text":
            comments = [v for v in vals if v.strip()]
            random.shuffle(comments)  # never in submission order
            item["comments"] = comments
        out.append(item)
    dimensions = {k: {"favourable": round(100 * f / (f + n + u)), "unfavourable": round(100 * u / (f + n + u))}
                  for k, (f, n, u) in dims.items() if f + n + u}
    return out, dimensions


def results(survey: Survey, department_ids=None):
    """department_ids restricts the population (managers see their own area only)."""
    qs = survey.responses.all()
    if department_ids is not None:
        qs = qs.filter(department_id__in=department_ids)
    rows = list(qs.values_list("department_id", "department__name", "answers"))
    invited = survey.invites.count() if department_ids is None else \
        survey.invites.filter(employee__department_id__in=department_ids).count()
    n = len(rows)
    base = {"survey": survey.title, "responses": n, "invited": invited, "min_group_size": survey.min_group_size,
            "response_rate": round(100 * n / invited) if invited else None}
    if n < survey.min_group_size:
        return {**base, "sufficient": False}
    questions, dimensions = _summarise(survey.questions, [r[2] for r in rows])
    by_dept, small = defaultdict(list), []
    names = {}
    for dep_id, dep_name, ans in rows:
        by_dept[dep_id].append(ans)
        names[dep_id] = dep_name or "—"
    breakdown = []
    for dep_id, answers in by_dept.items():
        if len(answers) >= survey.min_group_size:
            _, dims = _summarise(survey.questions, answers)
            breakdown.append({"department": names[dep_id], "responses": len(answers), "dimensions": dims,
                              "risk": any(dims.get(k, {}).get("unfavourable", 0) > RISK_THRESHOLD
                                          for k in RISK_DIMENSIONS)})
        else:
            small.extend(answers)
    if len(small) >= survey.min_group_size:
        _, dims = _summarise(survey.questions, small)
        breakdown.append({"department": "Other (smaller groups combined)", "responses": len(small),
                          "dimensions": dims, "risk": False})
    engagement = dimensions.get("engagement", {}).get("favourable")
    return {**base, "sufficient": True, "engagement_index": engagement, "questions": questions,
            "dimensions": dimensions, "departments": breakdown}


def trends():
    out = []
    for s in Survey.objects.exclude(status="draft").order_by("opens_on"):
        r = results(s)
        if r.get("sufficient"):
            enps = next((q.get("enps") for q in r["questions"] if q["type"] == "enps"), None)
            out.append({"survey": s.title, "date": s.opens_on, "engagement_index": r["engagement_index"],
                        "enps": enps, "response_rate": r["response_rate"]})
    return out


# ---------------------------------------------------------------- recognition, suggestions, events
def recognise(user, recipient, value, message, is_public=True):
    giver = getattr(user, "employee", None)
    if giver is None:
        raise BusinessRuleError("Your account is not linked to an employee record.")
    if giver == recipient:
        raise BusinessRuleError("You cannot recognise yourself.")
    if value not in dict(Recognition.VALUES) or not message:
        raise BusinessRuleError("Choose the value shown and write a short message.")
    r = Recognition.objects.create(giver=giver, recipient=recipient, value=value, message=message, is_public=is_public)
    _notify([recipient.user], "You've been recognised!",
            f"{giver.full_name} recognised you for {r.get_value_display().lower()}: \"{message[:140]}\"", "/engagement")
    return r


def suggest(user, data, anonymous=False):
    if not data.get("title") or not data.get("text"):
        raise BusinessRuleError("Give your idea a title and a description.")
    return Suggestion.objects.create(author=None if anonymous else getattr(user, "employee", None),
                                     category=data.get("category") or "other", title=data["title"], text=data["text"])


def register(event: Event, user):
    emp = getattr(user, "employee", None)
    if emp is None:
        raise BusinessRuleError("Your account is not linked to an employee record.")
    if event.starts_at < timezone.now():
        raise BusinessRuleError("This event has already taken place.")
    if event.attendees.filter(pk=emp.pk).exists():
        event.attendees.remove(emp)
        return False
    if event.capacity and event.attendees.count() >= event.capacity:
        raise BusinessRuleError("This event is full.")
    event.attendees.add(emp)
    return True
