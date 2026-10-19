"""IAM-style policy evaluation. Pure functions, no I/O."""

import re
from typing import Any

OPERATORS = {"StringEquals", "StringNotEquals", "StringLike", "StringNotLike"}
_STATEMENT_KEYS = {"Sid", "Effect", "Action", "Resource", "Condition"}
_POLICY_KEYS = {"Version", "Id", "Statement"}
_VARIABLE = re.compile(r"\$\{([^}]+)\}")


def is_allowed(
    policies: list[dict],
    action: str,
    resource: str,
    context: dict[str, str] | None = None,
    variables: dict[str, str] | None = None,
) -> bool:
    """Default deny; an explicit Deny wins; otherwise any matching Allow grants access."""
    context = {k.lower(): v for k, v in (context or {}).items()}
    variables = variables or {}
    matched = [
        s
        for p in policies
        for s in _statements(p)
        if _matches(s, action, resource, context, variables)
    ]
    if any(s["Effect"] == "Deny" for s in matched):
        return False
    return any(s["Effect"] == "Allow" for s in matched)


def validate(policy: Any) -> None:
    """Raise ValueError if the document uses anything outside the supported subset."""
    if not isinstance(policy, dict):
        raise ValueError("policy must be an object")
    if unknown := set(policy) - _POLICY_KEYS:
        raise ValueError(f"unsupported policy keys: {sorted(unknown)}")
    statements = _statements(policy)
    if not statements:
        raise ValueError("policy needs at least one Statement")
    for statement in statements:
        _validate_statement(statement)


def _validate_statement(statement: Any) -> None:
    if not isinstance(statement, dict):
        raise ValueError("Statement must be an object")
    if unknown := set(statement) - _STATEMENT_KEYS:
        raise ValueError(f"unsupported statement keys: {sorted(unknown)}")
    if statement.get("Effect") not in ("Allow", "Deny"):
        raise ValueError("Effect must be Allow or Deny")
    for key in ("Action", "Resource"):
        if not _is_strings(statement.get(key)):
            raise ValueError(f"{key} must be a string or a non-empty list of strings")
    condition = statement.get("Condition", {})
    if not isinstance(condition, dict):
        raise ValueError("Condition must be an object")
    for operator, clauses in condition.items():
        if operator not in OPERATORS:
            raise ValueError(f"unsupported condition operator: {operator}")
        if not isinstance(clauses, dict) or not all(_is_strings(v) for v in clauses.values()):
            raise ValueError(f"{operator} must map keys to a string or list of strings")


def _is_strings(value: Any) -> bool:
    if isinstance(value, str):
        return True
    return isinstance(value, list) and bool(value) and all(isinstance(v, str) for v in value)


def _statements(policy: dict) -> list:
    statements = policy.get("Statement", [])
    return [statements] if isinstance(statements, dict) else statements


def _as_list(value: str | list[str]) -> list[str]:
    return [value] if isinstance(value, str) else value


def _glob(text: str) -> str:
    return "".join(".*" if c == "*" else "." if c == "?" else re.escape(c) for c in text)


def _glob_match(pattern: str, value: str, ignore_case: bool = False) -> bool:
    flags = re.DOTALL | (re.IGNORECASE if ignore_case else 0)
    return re.fullmatch(_glob(pattern), value, flags) is not None


def _matches(statement: dict, action: str, resource: str, context: dict, variables: dict) -> bool:
    return (
        any(_glob_match(a, action, ignore_case=True) for a in _as_list(statement["Action"]))
        and any(_glob_match(r, resource) for r in _as_list(statement["Resource"]))
        and _conditions_match(statement.get("Condition", {}), context, variables)
    )


def _conditions_match(condition: dict, context: dict, variables: dict) -> bool:
    # A condition on a key the request does not supply never matches (IAM behaviour).
    for operator, clauses in condition.items():
        for key, expected in clauses.items():
            actual = context.get(key.lower())
            if actual is None or not _test(operator, _as_list(expected), actual, variables):
                return False
    return True


def _test(operator: str, expected: list[str], actual: str, variables: dict) -> bool:
    if operator not in OPERATORS:
        return False
    like = operator in ("StringLike", "StringNotLike")
    patterns = [_compile(value, variables, like) for value in expected]
    if None in patterns:
        return False  # unresolved policy variable: the statement does not apply
    hit = any(re.fullmatch(p, actual, re.DOTALL) for p in patterns)
    return hit if operator in ("StringEquals", "StringLike") else not hit


def _compile(template: str, variables: dict, wildcards: bool) -> str | None:
    """Build a regex; variable values are always literal so a tag cannot inject wildcards."""
    literal = _glob if wildcards else re.escape
    parts, pos = [], 0
    for match in _VARIABLE.finditer(template):
        value = variables.get(match.group(1))
        if value is None:
            return None
        parts += [literal(template[pos : match.start()]), re.escape(value)]
        pos = match.end()
    parts.append(literal(template[pos:]))
    return "".join(parts)
