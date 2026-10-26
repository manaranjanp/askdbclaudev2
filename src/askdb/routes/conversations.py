from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from askdb import conversations
from askdb.appdb import open_appdb
from askdb.auth import User, current_user

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("")
def list_conversations(request: Request, user: User = Depends(current_user)) -> list[dict[str, Any]]:
    with open_appdb(request.app.state.appdb_path) as conn:
        return conversations.list_for_user(conn, user.id)


@router.get("/{conversation_id}")
def get_conversation(conversation_id: int, request: Request, user: User = Depends(current_user)) -> dict[str, Any]:
    with open_appdb(request.app.state.appdb_path) as conn:
        found = conversations.owned_by(conn, user.id, conversation_id)
        if found is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return {
            "id": found["id"],
            "database": found["database_name"],
            "title": found["title"],
            "messages": conversations.messages(conn, conversation_id),
        }


@router.delete("/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: int, request: Request, user: User = Depends(current_user)) -> Response:
    with open_appdb(request.app.state.appdb_path) as conn:
        if not conversations.delete_for_user(conn, user.id, conversation_id):
            raise HTTPException(status_code=404, detail="Conversation not found")
    return Response(status_code=204)
