"""Tiny, safe condition evaluator for workflow routing (no eval).

Format:
  {}                                              -> always true
  {"field": "days", "op": ">", "value": 10}
  {"all": [cond, cond]} / {"any": [cond, cond]} / {"not": cond}
"""

from decimal import Decimal, InvalidOperation

OPS = {
    "=": lambda a, b: a == b,
    "eq": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    "ne": lambda a, b: a != b,
    ">": lambda a, b: a is not None and a > b,
    ">=": lambda a, b: a is not None and a >= b,
    "<": lambda a, b: a is not None and a < b,
    "<=": lambda a, b: a is not None and a <= b,
    "in": lambda a, b: a in (b or []),
    "not_in": lambda a, b: a not in (b or []),
}


def _coerce(a, b):
    if isinstance(b, (int, float)) and not isinstance(b, bool):
        try:
            return Decimal(str(a)) if a is not None else None, Decimal(str(b))
        except InvalidOperation:
            return a, b
    return a, b


def evaluate(cond, ctx: dict) -> bool:
    if not cond:
        return True
    if "all" in cond:
        return all(evaluate(c, ctx) for c in cond["all"])
    if "any" in cond:
        return any(evaluate(c, ctx) for c in cond["any"])
    if "not" in cond:
        return not evaluate(cond["not"], ctx)
    op = OPS.get(cond.get("op", "="))
    if op is None:
        raise ValueError(f"Unknown operator {cond.get('op')}")
    a, b = _coerce(ctx.get(cond.get("field")), cond.get("value"))
    try:
        return bool(op(a, b))
    except TypeError:
        return False
