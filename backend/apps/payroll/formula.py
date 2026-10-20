"""Safe arithmetic formula evaluation for pay elements (no eval)."""

import ast
import operator
from decimal import Decimal

_BINOPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
           ast.Mod: operator.mod, ast.Pow: operator.pow}
_CMP = {ast.Gt: operator.gt, ast.GtE: operator.ge, ast.Lt: operator.lt, ast.LtE: operator.le, ast.Eq: operator.eq,
        ast.NotEq: operator.ne}
_FUNCS = {"min": min, "max": max, "abs": abs, "round": lambda x, n=2: round(Decimal(x), int(n))}


class FormulaError(ValueError):
    pass


def evaluate(expr: str, variables: dict) -> Decimal:
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise FormulaError(f"Invalid formula: {expr}") from exc

    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return Decimal(str(node.value))
        if isinstance(node, ast.Name):
            if node.id not in variables:
                raise FormulaError(f"Unknown variable '{node.id}'")
            return Decimal(str(variables[node.id]))
        if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
            return _BINOPS[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -ev(node.operand)
        if isinstance(node, ast.Compare) and len(node.ops) == 1 and type(node.ops[0]) in _CMP:
            return Decimal(1) if _CMP[type(node.ops[0])](ev(node.left), ev(node.comparators[0])) else Decimal(0)
        if isinstance(node, ast.IfExp):
            return ev(node.body) if ev(node.test) else ev(node.orelse)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS:
            return Decimal(str(_FUNCS[node.func.id](*[ev(a) for a in node.args])))
        raise FormulaError(f"Unsupported expression in formula: {ast.dump(node)[:60]}")

    return ev(tree)
