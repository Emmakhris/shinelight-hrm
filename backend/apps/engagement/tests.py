import pytest
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient

from apps.core.exceptions import BusinessRuleError

QUESTIONS = [
    {"key": "proud", "text": "I am proud to work here", "type": "rating", "dimension": "engagement"},
    {"key": "workload", "text": "My workload is manageable", "type": "rating", "dimension": "workload"},
    {"key": "enps", "text": "How likely are you to recommend us as an employer?", "type": "enps"},
    {"key": "improve", "text": "One thing we should improve", "type": "text", "required": False},
]


@pytest.fixture
def staff(org, make_employee, make_user, structure):
    emps = [make_employee(first=f"P{i}") for i in range(7)]
    other = make_employee(first="Fin", position=structure["pos_fin"])
    users = [make_user(f"u{i}", ("employee",), employee=e) for i, e in enumerate(emps)]
    return {"emps": emps, "users": users, "other": other, "u_other": make_user("fin", ("employee",), employee=other),
            "hro": make_user("hro", ("hr_officer",)),
            "head": make_user("head", ("dept_head",), employee=make_employee(first="Head"))}


def _survey(**kw):
    from apps.engagement.models import Survey

    return Survey.objects.create(title="Pulse", questions=QUESTIONS, **kw)


def test_anonymous_survey_and_group_threshold(staff):
    from apps.engagement import services
    from apps.engagement.models import SurveyResponse

    s = _survey()
    assert services.launch(s, staff["hro"]) == 9  # 7 in Operations + finance + the head
    with pytest.raises(BusinessRuleError):
        services.respond(s, staff["users"][0], {"proud": 9})
    for i, u in enumerate(staff["users"][:4]):
        services.respond(s, u, {"proud": 5 - (i % 2), "workload": 2, "enps": 9 if i < 2 else 5,
                                "improve": f"comment {i}"})
    with pytest.raises(BusinessRuleError):
        services.respond(s, staff["users"][0], {"proud": 5, "workload": 5, "enps": 10})  # once only
    assert not services.results(s)["sufficient"]  # 4 < 5
    services.respond(s, staff["users"][4], {"proud": 4, "workload": 1, "enps": 10})
    r = services.results(s)
    assert r["sufficient"] and r["responses"] == 5 and r["engagement_index"] == 100
    enps = next(q for q in r["questions"] if q["type"] == "enps")
    assert enps["enps"] == 20  # 3 promoters, 2 detractors of 5
    assert r["dimensions"]["workload"]["unfavourable"] == 100
    assert r["departments"][0]["risk"] is True  # workload risk flagged for the Operations group
    assert SurveyResponse.objects.filter(employee__isnull=False).count() == 0  # never linked to a person
    comments = next(q for q in r["questions"] if q["type"] == "text")["comments"]
    assert sorted(comments) == [f"comment {i}" for i in range(4)]
    # a single respondent in Finance never gets their own breakdown row
    services.respond(s, staff["u_other"], {"proud": 1, "workload": 1, "enps": 0})
    r = services.results(s)
    assert all(d["department"] != "Finance" for d in r["departments"])


def test_results_access(staff):
    from apps.engagement import services

    s = _survey()
    services.launch(s, staff["hro"])
    for u in staff["users"][:5]:
        services.respond(s, u, {"proud": 4, "workload": 4, "enps": 8})
    c = APIClient()
    c.force_authenticate(staff["users"][0])
    assert c.get(f"/api/engagement/surveys/{s.id}/results/").status_code == 403
    c.force_authenticate(staff["hro"])
    assert c.get(f"/api/engagement/surveys/{s.id}/results/").json()["responses"] == 5
    mine = APIClient()
    mine.force_authenticate(staff["users"][5])
    assert mine.get("/api/engagement/surveys/mine/").json()[0]["responded"] is False


def test_recognition_and_suggestions(staff):
    from apps.engagement import services

    a, b = staff["users"][0], staff["emps"][1]
    with pytest.raises(BusinessRuleError):
        services.recognise(a, staff["emps"][0], "teamwork", "Me!")
    services.recognise(a, b, "patient_care", "Stayed late to settle a frightened patient")
    s = services.suggest(a, {"title": "Shuttle for night staff", "text": "A bus at 10pm", "category": "welfare"},
                         anonymous=True)
    assert s.author is None
    c = APIClient()
    c.force_authenticate(staff["users"][2])
    rows = c.get("/api/engagement/suggestions/").json()["results"]
    assert rows[0]["author_name"] == "Anonymous"
    assert c.post(f"/api/engagement/suggestions/{s.id}/vote/").json()["vote_count"] == 1
    assert c.post(f"/api/engagement/suggestions/{s.id}/review/", {"status": "accepted"}).status_code == 403
    with pytest.raises(PermissionDenied):
        services.respond(_survey(), staff["users"][0], {})
