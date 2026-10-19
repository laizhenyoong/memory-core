import pytest
from conftest import ADMIN, allow

AC = "bedrock-agentcore:"


# --- authentication -----------------------------------------------------------


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer mak_wrong"}, {"Authorization": "Basic abc"}],
    ids=["missing", "wrong key", "wrong scheme"],
)
def test_unauthenticated_requests_get_401(client, headers):
    response = client.get("/principals", headers=headers)
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


# --- principals ----------------------------------------------------------------


def test_principal_crud(client):
    body = {"name": "agent", "policies": [allow("admin:ListPrincipals")], "tags": {"actorId": "u1"}}
    created = client.post("/principals", json=body, headers=ADMIN)
    assert created.status_code == 201, created.text
    principal, key = created.json()["principal"], created.json()["apiKey"]
    assert key.startswith("mak_") and len(key) == 36
    assert "apiKey" not in principal and "keyHash" not in principal
    url = f"/principals/{principal['principalId']}"
    headers = {"Authorization": f"Bearer {key}"}

    assert client.get("/principals", headers=headers).status_code == 200
    assert client.get(url, headers=ADMIN).json()["principal"]["tags"] == {"actorId": "u1"}
    listed = client.get("/principals", headers=ADMIN).json()["principals"]
    assert {p["name"] for p in listed} == {"admin", "agent"}

    updated = client.patch(url, json={"disabled": True}, headers=ADMIN).json()["principal"]
    assert updated["disabled"] is True
    assert client.get("/principals", headers=headers).status_code == 401

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
