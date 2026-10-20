"""Models registered here get automatic create/update/delete audit entries.

register(Model, exclude=[...], sensitive=[...])
  - exclude: fields not recorded at all (e.g. updated_at)
  - sensitive: changes recorded as "<changed>" without values (salary, bank, IDs)
"""

_registry: dict = {}

DEFAULT_EXCLUDE = {"updated_at", "created_at", "password", "last_login"}


def register(model, exclude=None, sensitive=None):
    _registry[model] = {
        "exclude": DEFAULT_EXCLUDE | set(exclude or []),
        "sensitive": set(sensitive or []),
    }
    return model


def config_for(model):
    return _registry.get(model)


def registered_models():
    return list(_registry)
