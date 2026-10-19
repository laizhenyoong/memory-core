import pytest

from memory_agent.policy import is_allowed, validate

AC = "bedrock-agentcore:"
MEM = "memory/mem-123"
OTHER = "memory/mem-999"

PER_USER = {
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [f"{AC}CreateEvent", f"{AC}ListEvents", f"{AC}GetEvent"],
            "Resource": MEM,
            "Condition": {"StringEquals": {f"{AC}actorId": "${principal.tag/actorId}"}},
        },
        {
            "Effect": "Allow",
            "Action": f"{AC}RetrieveMemoryRecords",
            "Resource": MEM,
            "Condition": {
                "StringLike": {f"{AC}namespace": "/strategy/*/actors/${principal.tag/actorId}/*"}
            },
        },
    ]
}
BACKEND = {
    "Statement": [
        {"Effect": "Allow", "Action": f"{AC}*", "Resource": MEM},
        {"Effect": "Deny", "Action": [f"{AC}Delete*", f"{AC}BatchDelete*"], "Resource": "*"},
    ]
}
ANALYST = {
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [f"{AC}RetrieveMemoryRecords", f"{AC}ListMemoryRecords"],
            "Resource": "memory/*",
            "Condition": {"StringEquals": {f"{AC}strategyId": "episodes-ab12cd"}},
        }
    ]
}
SELF_MANAGED = {
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [f"{AC}Batch*MemoryRecords", f"{AC}ListEvents"],
            "Resource": MEM,
        }
    ]
}
ADMIN = {"Statement": [{"Effect": "Allow", "Action": "*", "Resource": "*"}]}

USER_A = {"principal.id": "prn-a", "principal.tag/actorId": "user-a"}
WILDCARD_TAG = {"principal.id": "prn-x", "principal.tag/actorId": "*"}
NO_TAG = {"principal.id": "prn-n"}


def actor(actor_id, session="s1"):
    return {f"{AC}actorId": actor_id, f"{AC}sessionId": session}


def ns(namespace, strategy=None):
    context = {f"{AC}namespace": namespace}
    if strategy:
        context[f"{AC}strategyId"] = strategy
    return context


CASES = [
    # per-user agent
    ("own events", PER_USER, "CreateEvent", MEM, actor("user-a"), USER_A, True),
    ("list own events", PER_USER, "ListEvents", MEM, actor("user-a"), USER_A, True),
    ("other user's events", PER_USER, "ListEvents", MEM, actor("user-b"), USER_A, False),
    ("action not granted", PER_USER, "DeleteEvent", MEM, actor("user-a"), USER_A, False),
    ("other memory", PER_USER, "CreateEvent", OTHER, actor("user-a"), USER_A, False),
    ("missing condition key", PER_USER, "ListEvents", MEM, {}, USER_A, False),
    ("missing tag", PER_USER, "ListEvents", MEM, actor("user-a"), NO_TAG, False),
    (
        "own namespace",
        PER_USER,
        "RetrieveMemoryRecords",
        MEM,
        ns("/strategy/s1/actors/user-a/"),
        USER_A,
        True,
    ),
    (
        "other namespace",
        PER_USER,
        "RetrieveMemoryRecords",
        MEM,
        ns("/strategy/s1/actors/user-b/"),
        USER_A,
        False,
    ),
    (
        "tag value is literal, not a wildcard",
        PER_USER,
        "RetrieveMemoryRecords",
        MEM,
        ns("/strategy/s1/actors/user-b/"),
        WILDCARD_TAG,
        False,
    ),
    (
        "tag value literal in StringEquals",
        PER_USER,
        "ListEvents",
        MEM,
        actor("user-b"),
        WILDCARD_TAG,
        False,
    ),
    # backend agent
    ("backend writes any actor", BACKEND, "CreateEvent", MEM, actor("anyone"), None, True),
    ("backend retrieves", BACKEND, "RetrieveMemoryRecords", MEM, ns("/x/"), None, True),
    ("backend cannot delete", BACKEND, "DeleteEvent", MEM, actor("anyone"), None, False),
    (
        "backend cannot batch delete",
        BACKEND,
        "BatchDeleteMemoryRecords",
        MEM,
        ns("/x/"),
        None,
        False,
    ),
    ("backend other memory", BACKEND, "CreateEvent", OTHER, actor("anyone"), None, False),
    # analyst
    (
        "analyst reflections",
        ANALYST,
        "RetrieveMemoryRecords",
        OTHER,
        ns("/strategy/episodes-ab12cd/", "episodes-ab12cd"),
        None,
        True,
    ),
    (
        "analyst other strategy",
        ANALYST,
        "ListMemoryRecords",
        MEM,
        ns("/x/", "facts-1"),
        None,
        False,
    ),
    ("analyst no strategy key", ANALYST, "ListMemoryRecords", MEM, ns("/x/"), None, False),
    ("analyst cannot write", ANALYST, "CreateEvent", MEM, actor("a"), None, False),
    # self-managed pipeline
    (
        "self-managed batch create",
        SELF_MANAGED,
        "BatchCreateMemoryRecords",
        MEM,
        ns("/m/"),
        None,
        True,
    ),
    ("self-managed list events", SELF_MANAGED, "ListEvents", MEM, actor("a"), None, True),
    (
        "self-managed no retrieve",
        SELF_MANAGED,
        "RetrieveMemoryRecords",
        MEM,
        ns("/m/"),
        None,
        False,
    ),
    # basics
    ("admin", ADMIN, "admin:CreatePrincipal", "principal/*", None, None, True),
    ("action is case-insensitive", SELF_MANAGED, "listevents", MEM, None, None, True),
    ("resource is case-sensitive", SELF_MANAGED, "ListEvents", "memory/MEM-123", None, None, False),
]


@pytest.mark.parametrize(
    "policy,action,resource,context,variables,expected",
    [c[1:] for c in CASES],
    ids=[c[0] for c in CASES],
)
def test_recipes(policy, action, resource, context, variables, expected):
    action = action if ":" in action else AC + action
    assert is_allowed([policy], action, resource, context, variables) is expected


def test_default_deny():
    assert is_allowed([], f"{AC}GetMemory", MEM) is False


def test_explicit_deny_wins_across_policies():
    deny = {"Statement": [{"Effect": "Deny", "Action": "*", "Resource": MEM}]}
    assert is_allowed([ADMIN, deny], f"{AC}GetMemory", MEM) is False
    assert is_allowed([ADMIN, deny], f"{AC}GetMemory", OTHER) is True


def test_statement_may_be_a_single_object():
    policy = {"Statement": {"Effect": "Allow", "Action": f"{AC}GetMemory", "Resource": MEM}}
    assert is_allowed([policy], f"{AC}GetMemory", MEM) is True


def test_principal_id_variable_and_value_lists():
    policy = {
        "Statement": [
            {
                "Effect": "Allow",
                "Action": f"{AC}CreateEvent",
                "Resource": MEM,
                "Condition": {
                    "StringEquals": {f"{AC}actorId": ["${principal.id}", "shared"]},
                    "StringLike": {f"{AC}sessionId": "web-*"},
                },
            }
        ]
    }
    variables = {"principal.id": "prn-a"}
    assert is_allowed([policy], f"{AC}CreateEvent", MEM, actor("prn-a", "web-1"), variables)
    assert is_allowed([policy], f"{AC}CreateEvent", MEM, actor("shared", "web-2"), variables)
    assert not is_allowed([policy], f"{AC}CreateEvent", MEM, actor("prn-a", "cli-1"), variables)
    assert not is_allowed([policy], f"{AC}CreateEvent", MEM, actor("prn-b", "web-1"), variables)


@pytest.mark.parametrize(
    "operator,value,expected",
    [
        ("StringNotEquals", "user-b", True),
        ("StringNotEquals", "user-a", False),
        ("StringNotLike", "user-*", False),
        ("StringNotLike", "admin-*", True),
    ],
)
def test_negated_operators(operator, value, expected):
    policy = {
        "Statement": [
            {
                "Effect": "Allow",
                "Action": "*",
                "Resource": "*",
                "Condition": {operator: {f"{AC}actorId": value}},
            }
        ]
    }
    assert is_allowed([policy], f"{AC}ListEvents", MEM, actor("user-a")) is expected


def test_condition_key_lookup_is_case_insensitive():
    policy = {
        "Statement": [
            {
                "Effect": "Allow",
                "Action": "*",
                "Resource": "*",
                "Condition": {"StringEquals": {"Bedrock-AgentCore:ActorId": "user-a"}},
            }
        ]
    }
    assert is_allowed([policy], f"{AC}ListEvents", MEM, actor("user-a"))


@pytest.mark.parametrize(
    "policy",
    [PER_USER, BACKEND, ANALYST, SELF_MANAGED, ADMIN, {"Version": "2012-10-17", **ADMIN}],
)
def test_validate_accepts_recipes(policy):
    validate(policy)


@pytest.mark.parametrize(
    "policy,message",
    [
        ("nope", "must be an object"),
        ({}, "at least one Statement"),
        ({"Statement": []}, "at least one Statement"),
        ({"Statement": [{"Effect": "Maybe", "Action": "*", "Resource": "*"}]}, "Effect"),
        ({"Statement": [{"Effect": "Allow", "Resource": "*"}]}, "Action"),
        ({"Statement": [{"Effect": "Allow", "Action": [], "Resource": "*"}]}, "Action"),
        ({"Statement": [{"Effect": "Allow", "Action": "*"}]}, "Resource"),
        (
            {"Statement": [{"Effect": "Allow", "Action": "*", "Resource": "*", "NotAction": "x"}]},
            "unsupported statement keys",
        ),
        (
            {
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": "*",
                        "Resource": "*",
                        "Condition": {"IpAddress": {"aws:SourceIp": "1.2.3.4"}},
                    }
                ]
            },
            "unsupported condition operator",
        ),
        (
            {
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": "*",
                        "Resource": "*",
                        "Condition": {"StringEquals": {"k": 1}},
                    }
                ]
            },
            "StringEquals",
        ),
        ({"Statement": [], "Principal": "*"}, "unsupported policy keys"),
    ],
)
def test_validate_rejects(policy, message):
    with pytest.raises(ValueError, match=message):
        validate(policy)
