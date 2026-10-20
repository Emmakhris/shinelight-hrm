from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from apps.employees.models import Employee

from .services import emit


def _payload(emp: Employee):
    return {"id": emp.id, "staff_number": emp.staff_number, "first_name": emp.first_name,
            "last_name": emp.last_name, "work_email": emp.work_email, "status": emp.status,
            "department": emp.department.code if emp.department_id else None,
            "job_title": emp.job_title.name if emp.job_title_id else None,
            "hire_date": emp.hire_date, "exit_date": emp.exit_date}


@receiver(pre_save, sender=Employee)
def _remember_status(sender, instance, **kwargs):
    if instance.pk:
        instance._previous_status = Employee.all_objects.filter(pk=instance.pk).values_list("status", flat=True).first()


@receiver(post_save, sender=Employee)
def _employee_events(sender, instance, created, raw=False, **kwargs):
    if raw:
        return
    org_id = instance.organization_id
    if created:
        emit("employee.created", _payload(instance), org_id)
        return
    emit("employee.updated", _payload(instance), org_id)
    prev = getattr(instance, "_previous_status", None)
    if prev and prev != instance.status:
        emit("employee.status_changed", {**_payload(instance), "previous_status": prev}, org_id)
        if instance.status == "exited":
            emit("employee.exited", _payload(instance), org_id)
