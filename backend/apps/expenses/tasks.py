from celery import shared_task


@shared_task
def travel_housekeeping():
    """Daily: mark finished trips completed and remind employees with overdue advance retirements."""
    from apps.core.context import org_context
    from apps.notifications.services import notify
    from apps.tenancy.models import Organization

    from . import services

    reminded = 0
    for org in Organization.objects.filter(is_active=True):
        with org_context(org):
            services.mark_completed_trips()
            for tr in services.overdue_retirements().select_related("employee__user"):
                if tr.employee.user_id:
                    notify("generic", [tr.employee.user], {
                        "title": f"Retire your travel advance {tr.reference}",
                        "body": f"Your advance of {tr.currency} {tr.advance_paid:,.2f} was due for retirement on "
                                f"{tr.retirement_due:%d/%m/%Y}. Submit an expense claim linked to the trip.",
                        "link": "/expenses/my"})
                    reminded += 1
    return reminded
