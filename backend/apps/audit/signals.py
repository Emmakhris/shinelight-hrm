from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from . import registry, services


def _field_values(instance, cfg):
    values = {}
    for f in instance._meta.concrete_fields:
        if f.name in cfg["exclude"]:
            continue
        values[f.name] = getattr(instance, f.attname)
    return values


@receiver(pre_save)
def _capture_old(sender, instance, raw=False, **kwargs):
    cfg = registry.config_for(sender)
    if cfg is None or raw or not instance.pk:
        return
    try:
        old = sender._base_manager.get(pk=instance.pk)
    except sender.DoesNotExist:
        return
    instance._audit_old = _field_values(old, cfg)


@receiver(post_save)
def _log_save(sender, instance, created, raw=False, **kwargs):
    cfg = registry.config_for(sender)
    if cfg is None or raw:
        return
    new = _field_values(instance, cfg)
    if created:
        changes = {k: ("<set>" if k in cfg["sensitive"] else v) for k, v in new.items() if v not in (None, "")}
        services.log("create", instance, changes)
        return
    old = getattr(instance, "_audit_old", {})
    changes = {}
    for k, v in new.items():
        if old.get(k) != v:
            changes[k] = "<changed>" if k in cfg["sensitive"] else {"from": old.get(k), "to": v}
    if changes:
        services.log("update", instance, changes)


@receiver(post_delete)
def _log_delete(sender, instance, **kwargs):
    cfg = registry.config_for(sender)
    if cfg is None:
        return
    services.log("delete", instance, {})


def _register():
    from .registrations import register_all

    register_all()


_register()
