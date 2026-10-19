"""Control-plane routes: parse, authorize, call the logic module. Authorization runs before
lookups so a denied caller cannot probe which IDs exist."""

from typing import Annotated

from fastapi import APIRouter, Query, Response

from memory_agent import memories, principals
from memory_agent.auth import authorize
from memory_agent.deps import Conn, CurrentPrincipal
from memory_agent.models import (
    CreateMemoryInput,
    CreatePrincipalInput,
    UpdateMemoryInput,
    UpdatePrincipalInput,
)
from memory_agent.pagination import DEFAULT_MAX_RESULTS, MAX_RESULTS

router = APIRouter()

MaxResults = Annotated[int, Query(alias="maxResults", ge=1, le=MAX_RESULTS)]
NextToken = Annotated[str | None, Query(alias="nextToken")]


def _memory_action(name: str) -> str:
    return f"bedrock-agentcore:{name}"


def _admin_action(name: str) -> str:
    return f"admin:{name}"


# --- memories ---------------------------------------------------------------


@router.post("/memories", status_code=201)
def create_memory(body: CreateMemoryInput, principal: CurrentPrincipal, conn: Conn) -> dict:
    authorize(principal, _memory_action("CreateMemory"), "memory/*")
    return {"memory": memories.create_memory(conn, body)}


@router.get("/memories")
def list_memories(
    principal: CurrentPrincipal,
    conn: Conn,
    max_results: MaxResults = DEFAULT_MAX_RESULTS,
    next_token: NextToken = None,
) -> dict:
    authorize(principal, _memory_action("ListMemories"), "memory/*")
    items, token = memories.list_memories(conn, next_token, max_results)
    return {"memories": items, **({"nextToken": token} if token else {})}


@router.get("/memories/{memory_id}")
def get_memory(memory_id: str, principal: CurrentPrincipal, conn: Conn) -> dict:
    authorize(principal, _memory_action("GetMemory"), f"memory/{memory_id}")
    return {"memory": memories.get_memory(conn, memory_id)}


@router.patch("/memories/{memory_id}")
def update_memory(
    memory_id: str, body: UpdateMemoryInput, principal: CurrentPrincipal, conn: Conn
) -> dict:
    authorize(principal, _memory_action("UpdateMemory"), f"memory/{memory_id}")
    return {"memory": memories.update_memory(conn, memory_id, body)}


@router.delete("/memories/{memory_id}")
def delete_memory(memory_id: str, principal: CurrentPrincipal, conn: Conn) -> dict:
    authorize(principal, _memory_action("DeleteMemory"), f"memory/{memory_id}")
    return memories.delete_memory(conn, memory_id)


# --- principals -------------------------------------------------------------


@router.post("/principals", status_code=201)
def create_principal(body: CreatePrincipalInput, principal: CurrentPrincipal, conn: Conn) -> dict:
    authorize(principal, _admin_action("CreatePrincipal"), "principal/*")
    created, key = principals.create_principal(conn, body)
    return {"principal": created, "apiKey": key}


@router.get("/principals")
def list_principals(
    principal: CurrentPrincipal,
    conn: Conn,
    max_results: MaxResults = DEFAULT_MAX_RESULTS,
    next_token: NextToken = None,
) -> dict:
    authorize(principal, _admin_action("ListPrincipals"), "principal/*")
    items, token = principals.list_principals(conn, next_token, max_results)
    return {"principals": items, **({"nextToken": token} if token else {})}


@router.get("/principals/{principal_id}")
def get_principal(principal_id: str, principal: CurrentPrincipal, conn: Conn) -> dict:
    authorize(principal, _admin_action("GetPrincipal"), f"principal/{principal_id}")
    return {"principal": principals.get_principal(conn, principal_id)}


@router.patch("/principals/{principal_id}")
def update_principal(
    principal_id: str, body: UpdatePrincipalInput, principal: CurrentPrincipal, conn: Conn
) -> dict:
    authorize(principal, _admin_action("UpdatePrincipal"), f"principal/{principal_id}")
    return {"principal": principals.update_principal(conn, principal_id, body)}


@router.delete("/principals/{principal_id}", status_code=204)
def delete_principal(principal_id: str, principal: CurrentPrincipal, conn: Conn) -> Response:
    authorize(principal, _admin_action("DeletePrincipal"), f"principal/{principal_id}")
    principals.delete_principal(conn, principal_id)
    return Response(status_code=204)
