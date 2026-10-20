"""Request-scoped context (current organization, user, IP) using contextvars so it is
safe for threads, async and Celery tasks."""

from contextlib import contextmanager
from contextvars import ContextVar

_current_org = ContextVar("current_org", default=None)
_current_user = ContextVar("current_user", default=None)
_current_ip = ContextVar("current_ip", default=None)


def get_current_org():
    return _current_org.get()


def set_current_org(org):
    return _current_org.set(org)


def get_current_user():
    return _current_user.get()


def set_current_user(user):
    return _current_user.set(user)


def get_current_ip():
    return _current_ip.get()


def set_current_ip(ip):
    return _current_ip.set(ip)


@contextmanager
def org_context(org, user=None):
    t1 = _current_org.set(org)
    t2 = _current_user.set(user)
    try:
        yield
    finally:
        _current_org.reset(t1)
        _current_user.reset(t2)
