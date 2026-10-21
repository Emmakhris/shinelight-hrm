"""PostgreSQL row-level security: a database-level backstop behind the ORM's tenant filter.

When DB_ROW_LEVEL_SECURITY is on, every request and every org_context() sets the session variable
`app.current_org`, and each tenant table carries a policy that hides other organizations' rows while it
is set - even from code that forgot the filter or used `all_objects`. Code that legitimately works across
organizations (platform console, Celery loops, public endpoints) runs with the variable unset.

Requirements: the application must connect as a role that is NOT a superuser and does NOT have BYPASSRLS
(superusers always bypass row-level security). Apply the policies with `manage.py enable_rls` after
migrations; it is idempotent.
"""

from contextlib import contextmanager

from django.conf import settings
from django.db import connection

GUC = "app.current_org"
POLICY = "shinelight_tenant_isolation"


def enabled():
    return bool(getattr(settings, "DB_ROW_LEVEL_SECURITY", False)) and connection.vendor == "postgresql"


def set_db_org(org_id):
    if not enabled():
        return
    with connection.cursor() as cur:
        cur.execute("SELECT set_config(%s, %s, false)", [GUC, str(org_id or "")])


@contextmanager
def unrestricted():
    """Temporarily lift the database policy for a deliberate cross-organization lookup."""
    from apps.core.context import get_current_org

    if not enabled():
        yield
        return
    set_db_org(None)
    try:
        yield
    finally:
        org = get_current_org()
        set_db_org(org.pk if org else None)


def tenant_tables():
    from django.apps import apps

    from apps.core.models import TenantModel

    return sorted({m._meta.db_table for m in apps.get_models()
                   if issubclass(m, TenantModel) and not m._meta.proxy and m._meta.managed})


def apply(using_connection=None):
    """Enable and force RLS with the isolation policy on every tenant table. Returns the table count."""
    conn = using_connection or connection
    if conn.vendor != "postgresql":
        return 0
    tables = tenant_tables()
    with conn.cursor() as cur:
        for t in tables:
            q = conn.ops.quote_name(t)
            cur.execute(f"ALTER TABLE {q} ENABLE ROW LEVEL SECURITY")
            cur.execute(f"ALTER TABLE {q} FORCE ROW LEVEL SECURITY")
            cur.execute(f"DROP POLICY IF EXISTS {POLICY} ON {q}")
            org = f"NULLIF(current_setting('{GUC}', true), '')"    # NULL when unset (OR doesn't short-circuit)
            cur.execute(f"CREATE POLICY {POLICY} ON {q} USING ({org} IS NULL OR organization_id = {org}::bigint)")
    return len(tables)


def remove(using_connection=None):
    conn = using_connection or connection
    if conn.vendor != "postgresql":
        return 0
    tables = tenant_tables()
    with conn.cursor() as cur:
        for t in tables:
            q = conn.ops.quote_name(t)
            cur.execute(f"DROP POLICY IF EXISTS {POLICY} ON {q}")
            cur.execute(f"ALTER TABLE {q} NO FORCE ROW LEVEL SECURITY")
            cur.execute(f"ALTER TABLE {q} DISABLE ROW LEVEL SECURITY")
    return len(tables)
