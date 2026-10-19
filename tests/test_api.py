import pytest
from conftest import ADMIN, allow

AC = "bedrock-agentcore:"
NS = "/strategy/{memoryStrategyId}/actors/{actorId}/"

FOUR_STRATEGIES = {
    "name": "support_memory",
    "description": "Customer support agent",
    "eventExpiryDuration": 30,
    "memoryStrategies": [
        {"semanticMemoryStrategy": {"name": "facts"}},
        {"userPreferenceMemoryStrategy": {"name": "prefs", "namespaces": [NS]}},
        {"summaryMemoryStrategy": {"name": "summary"}},
        {
            "episodicMemoryStrategy": {
                "name": "episodes",
                "namespaces": ["/strategy/{memoryStrategyId}/actor/{actorId}/"],
                "reflectionConfiguration": {"namespaces": ["/strategy/{memoryStrategyId}/"]},
            }
        },
    ],
}


def create_memory(client, name="support_memory", headers=ADMIN, **extra):
    body = {**FOUR_STRATEGIES, "name": name, **extra}
    return client.post("/memories", json=body, headers=headers)


# --- authentication -----------------------------------------------------------


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer mak_wrong"}, {"Authorization": "Basic abc"}],
    ids=["missing", "wrong key", "wrong scheme"],
)
def test_unauthenticated_requests_get_401(client, headers):
    response = client.get("/memories", headers=headers)
    assert response.status_code == 401
    assert response.json()["type"] == "UnrecognizedClientException"


def test_admin_key_from_settings_works(client):
    assert client.get("/principals", headers=ADMIN).status_code == 200


def test_generated_admin_key_is_printed_once(tmp_path, capsys):
    from fastapi.testclient import TestClient

    from memory_agent.config import Settings
    from memory_agent.main import create_app

    settings = Settings(db_path=str(tmp_path / "m.db"), admin_key=None)
    with TestClient(create_app(settings)) as first:
        key = capsys.readouterr().out.strip().rsplit(" ", 1)[-1]
        assert key.startswith("mak_")
        assert (
            first.get("/principals", headers={"Authorization": f"Bearer {key}"}).status_code == 200
        )
    with TestClient(create_app(settings)):
        assert "Admin API key" not in capsys.readouterr().out


# --- memories ------------------------------------------------------------------


def test_admin_creates_memory_with_four_strategies(client):
    response = create_memory(client)
    assert response.status_code == 201, response.text
    memory = response.json()["memory"]
    assert memory["id"].startswith("mem-")
    assert memory["status"] == "ACTIVE"
    assert memory["eventExpiryDuration"] == 30
    by_type = {s["type"]: s for s in memory["strategies"]}
    assert set(by_type) == {"SEMANTIC", "USER_PREFERENCE", "SUMMARY", "EPISODIC"}
    assert by_type["SEMANTIC"]["strategyId"].startswith("facts-")
    assert by_type["SEMANTIC"]["namespaces"] == [NS]
    assert by_type["SUMMARY"]["namespaces"] == [
        "/strategy/{memoryStrategyId}/actors/{actorId}/sessions/{sessionId}/"
    ]
    assert by_type["EPISODIC"]["reflectionConfiguration"] == {
        "namespaces": ["/strategy/{memoryStrategyId}/"]
    }


def test_custom_override_and_self_managed_strategies(client):
    strategies = [
        {
            "customMemoryStrategy": {
                "name": "domain_facts",
                "namespaces": ["/domain/{actorId}"],
                "configuration": {
                    "semanticOverride": {
                        "extraction": {"appendToPrompt": "Billing only.", "modelId": "m-1"}
                    }
                },
            }
        },
        {
            "customMemoryStrategy": {
                "name": "mine",
                "configuration": {"selfManagedConfiguration": {}},
            }
        },
    ]
    response = create_memory(client, memoryStrategies=strategies)
    assert response.status_code == 201, response.text
    override, self_managed = response.json()["memory"]["strategies"]
    assert override["type"] == "CUSTOM"
    assert override["namespaces"] == ["/domain/{actorId}/"]
    assert override["configuration"] == {
        "semanticOverride": {"extraction": {"appendToPrompt": "Billing only.", "modelId": "m-1"}}
    }
    assert self_managed["configuration"] == {"selfManagedConfiguration": {}}
    assert self_managed["namespaces"] == [NS]


@pytest.mark.parametrize(
    "patch",
    [
        {"eventExpiryDuration": 3},
        {"eventExpiryDuration": 366},
        {"name": "1bad"},
        {
            "memoryStrategies": [
                {"semanticMemoryStrategy": {"name": "a"}, "summaryMemoryStrategy": {"name": "b"}}
            ]
        },
        {"memoryStrategies": [{}]},
        {
            "memoryStrategies": [
                {"semanticMemoryStrategy": {"name": "a", "namespaces": ["no-slash"]}}
            ]
        },
        {
            "memoryStrategies": [
                {"semanticMemoryStrategy": {"name": "a", "namespaces": ["/{bogus}/"]}}
            ]
        },
        {"memoryStrategies": [{"customMemoryStrategy": {"name": "c", "configuration": {}}}]},
        {"unknownField": 1},
    ],
)
def test_create_memory_validation(client, patch):
    response = create_memory(client, **patch)
    assert response.status_code == 400, response.text
    assert response.json()["type"] == "ValidationException"


def test_duplicate_names_conflict(client):
    assert create_memory(client).status_code == 201
    response = create_memory(client)
    assert response.status_code == 409
    assert response.json()["type"] == "ConflictException"

    dup = [{"semanticMemoryStrategy": {"name": "x"}}, {"summaryMemoryStrategy": {"name": "x"}}]
    assert create_memory(client, name="other", memoryStrategies=dup).status_code == 409


def test_get_list_and_paginate(client):
    ids = [create_memory(client, name=f"m{i}").json()["memory"]["id"] for i in range(3)]

    assert client.get(f"/memories/{ids[0]}", headers=ADMIN).json()["memory"]["name"] == "m0"

    first = client.get("/memories", params={"maxResults": 2}, headers=ADMIN).json()
    assert [m["id"] for m in first["memories"]] == ids[:2]
    second = client.get(
        "/memories", params={"maxResults": 2, "nextToken": first["nextToken"]}, headers=ADMIN
    ).json()
    assert [m["id"] for m in second["memories"]] == ids[2:]
    assert "nextToken" not in second

    bad = client.get("/memories", params={"nextToken": "!!"}, headers=ADMIN)
    assert bad.status_code == 400


def test_update_memory_and_strategies(client):
    memory = create_memory(client).json()["memory"]
    by_name = {s["name"]: s["strategyId"] for s in memory["strategies"]}
    body = {
        "description": "updated",
        "eventExpiryDuration": 90,
        "memoryStrategies": {
            "addMemoryStrategies": [{"semanticMemoryStrategy": {"name": "more_facts"}}],
            "modifyMemoryStrategies": [
                {"memoryStrategyId": by_name["facts"], "namespaces": ["/facts/{actorId}/"]}
            ],
            "deleteMemoryStrategies": [{"memoryStrategyId": by_name["summary"]}],
        },
    }
    response = client.patch(f"/memories/{memory['id']}", json=body, headers=ADMIN)
    assert response.status_code == 200, response.text
    updated = response.json()["memory"]
    assert updated["description"] == "updated"
    assert updated["eventExpiryDuration"] == 90
    strategies = {s["name"]: s for s in updated["strategies"]}
    assert set(strategies) == {"facts", "prefs", "episodes", "more_facts"}
    assert strategies["facts"]["namespaces"] == ["/facts/{actorId}/"]


def test_update_rejects_bad_strategy_changes(client):
    memory = create_memory(client).json()["memory"]
    facts = memory["strategies"][0]["strategyId"]
    url = f"/memories/{memory['id']}"

    config = {"selfManagedConfiguration": {}}
    modify = {"modifyMemoryStrategies": [{"memoryStrategyId": facts, "configuration": config}]}
    assert client.patch(url, json={"memoryStrategies": modify}, headers=ADMIN).status_code == 400

    missing = {"deleteMemoryStrategies": [{"memoryStrategyId": "nope-0000000000"}]}
    assert client.patch(url, json={"memoryStrategies": missing}, headers=ADMIN).status_code == 404

    # A failed update leaves the memory untouched.
    after = client.get(url, headers=ADMIN).json()["memory"]
    assert after["strategies"] == memory["strategies"]


def test_delete_memory(client):
    memory_id = create_memory(client).json()["memory"]["id"]
    response = client.delete(f"/memories/{memory_id}", headers=ADMIN)
    assert response.json() == {"memoryId": memory_id, "status": "DELETING"}
    assert client.get(f"/memories/{memory_id}", headers=ADMIN).status_code == 404


def test_missing_memory_is_404_for_authorized_caller(client):
    response = client.get("/memories/mem-0000000000", headers=ADMIN)
    assert response.status_code == 404
    assert response.json()["type"] == "ResourceNotFoundException"


# --- access control ------------------------------------------------------------


def test_key_without_create_memory_gets_403(client, make_principal):
    reader = make_principal([allow([f"{AC}GetMemory", f"{AC}ListMemories"])])
    response = create_memory(client, headers=reader)
    assert response.status_code == 403
    assert response.json()["type"] == "AccessDeniedException"


def test_memory_scoped_key(client, make_principal):
    mine = create_memory(client, name="mine").json()["memory"]["id"]
    other = create_memory(client, name="other").json()["memory"]["id"]
    headers = make_principal([allow(f"{AC}GetMemory", f"memory/{mine}")])

    assert client.get(f"/memories/{mine}", headers=headers).status_code == 200
    assert client.get(f"/memories/{other}", headers=headers).status_code == 403
    # Denied before lookup: a scoped key cannot probe for IDs.
    assert client.get("/memories/mem-0000000000", headers=headers).status_code == 403
    assert client.get("/memories", headers=headers).status_code == 403
    assert client.patch(f"/memories/{mine}", json={}, headers=headers).status_code == 403
    assert client.delete(f"/memories/{mine}", headers=headers).status_code == 403


def test_backend_recipe_cannot_delete_memory(client, make_principal):
    memory_id = create_memory(client).json()["memory"]["id"]
    headers = make_principal(
        [
            {
                "Statement": [
                    {"Effect": "Allow", "Action": f"{AC}*", "Resource": f"memory/{memory_id}"},
                    {"Effect": "Deny", "Action": f"{AC}Delete*", "Resource": "*"},
                ]
            }
        ]
    )
    assert client.patch(f"/memories/{memory_id}", json={}, headers=headers).status_code == 200
    assert client.delete(f"/memories/{memory_id}", headers=headers).status_code == 403


# --- principals ----------------------------------------------------------------


def test_principal_crud(client):
    body = {"name": "agent", "policies": [allow(f"{AC}ListMemories")], "tags": {"actorId": "u1"}}
    created = client.post("/principals", json=body, headers=ADMIN)
    assert created.status_code == 201, created.text
    principal, key = created.json()["principal"], created.json()["apiKey"]
    assert key.startswith("mak_") and len(key) == 36
    assert "apiKey" not in principal and "keyHash" not in principal
    url = f"/principals/{principal['principalId']}"
    headers = {"Authorization": f"Bearer {key}"}

    assert client.get("/memories", headers=headers).status_code == 200
    assert client.get(url, headers=ADMIN).json()["principal"]["tags"] == {"actorId": "u1"}
    listed = client.get("/principals", headers=ADMIN).json()["principals"]
    assert {p["name"] for p in listed} == {"admin", "agent"}

    updated = client.patch(url, json={"disabled": True}, headers=ADMIN).json()["principal"]
    assert updated["disabled"] is True
    assert client.get("/memories", headers=headers).status_code == 401

    assert client.delete(url, headers=ADMIN).status_code == 204
    assert client.get(url, headers=ADMIN).status_code == 404


def test_principal_policies_are_validated(client):
    bad = {"name": "x", "policies": [{"Statement": [{"Effect": "Allow", "Action": "*"}]}]}
    response = client.post("/principals", json=bad, headers=ADMIN)
    assert response.status_code == 400
    assert "Resource" in response.json()["message"]


def test_non_admin_cannot_manage_principals(client, make_principal):
    headers = make_principal([allow(f"{AC}*")])
    assert client.post("/principals", json={"name": "x"}, headers=headers).status_code == 403
    assert client.get("/principals", headers=headers).status_code == 403
