from celery import shared_task


@shared_task
def recruitment_housekeeping():
    """Daily: close vacancies past their closing date, expire unanswered offers and anonymise candidates
    whose retention period has ended (Data Protection Act, 2012 (Act 843))."""
    from apps.core.context import org_context
    from apps.tenancy.models import Organization

    from . import services

    out = {"closed": 0, "expired": 0, "anonymised": 0}
    for org in Organization.objects.filter(is_active=True):
        with org_context(org):
            out["closed"] += services.close_expired_vacancies()
            out["expired"] += services.expire_offers()
            out["anonymised"] += services.purge_expired_candidates()
    return out
