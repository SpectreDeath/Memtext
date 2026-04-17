"""FastAPI server for MemText.

Provides REST API and WebSocket endpoints for external agent integration.
Requires: pip install memtext[api]
"""

import os
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, List
from contextlib import asynccontextmanager

from fastapi import (
    FastAPI,
    HTTPException,
    Query,
    Header,
    WebSocket,
    WebSocketDisconnect,
    Request,
)
from pydantic import BaseModel, Field
import uvicorn
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded


class EntryCreate(BaseModel):
    title: str = Field(..., description="Entry title")
    content: str = Field(..., description="Entry content")
    entry_type: str = Field(default="note", description="Entry type")
    tags: Optional[List[str]] = Field(default=None, description="Tags")
    importance: int = Field(default=1, ge=1, le=5, description="Importance 1-5")


class EntryUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    entry_type: Optional[str] = None
    tags: Optional[List[str]] = None
    importance: Optional[int] = Field(default=None, ge=1, le=5)


class EntryResponse(BaseModel):
    id: int
    title: str
    content: str
    entry_type: str
    tags: Optional[str]
    importance: int
    source: str
    created_at: str
    last_accessed: Optional[str]
    access_count: int


class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: str


class ConnectionManager:
    """Manages WebSocket connections."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass


manager = ConnectionManager()

# Rate limiter setup
limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    manager.active_connections.clear()


app = FastAPI(
    title="MemText API",
    description="Context offloading for AI agents - REST API",
    version="0.3.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


async def verify_api_key(x_api_key: Optional[str] = Header(None)):
    """Verify API key from header."""
    expected = os.environ.get("MEMTEXT_API_KEY", "dev-key-change-in-production")
    if x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")


@app.get("/health", response_model=HealthResponse)
@limiter.exempt  # Health check should be exempt
async def health():
    return HealthResponse(
        status="healthy",
        version="0.3.0",
        timestamp=datetime.now().isoformat(),
    )


@app.get("/entries")
@limiter.limit("100/minute")
async def list_entries(
    request: Request,
    entry_type: Optional[str] = Query(None),
    limit: int = Query(10, le=100),
    x_api_key: Optional[str] = Header(None),
):
    """List context entries."""
    await verify_api_key(x_api_key)
    from memtext.db import query_entries, get_db_path

    if not get_db_path().exists():
        return []

    results = query_entries(entry_type=entry_type, limit=limit)
    return [
        {
            "id": r["id"],
            "title": r["title"],
            "content": r["content"],
            "entry_type": r["entry_type"],
            "tags": r.get("tags", ""),
            "importance": r.get("importance", 1),
            "source": r.get("source", "manual"),
            "created_at": r.get("created_at", ""),
            "last_accessed": r.get("last_accessed"),
            "access_count": r.get("access_count", 0),
        }
        for r in results
    ]


@app.get("/entries/{entry_id}")
@limiter.limit("200/minute")
async def get_entry(
    request: Request,
    entry_id: int,
    x_api_key: Optional[str] = Header(None),
):
    """Get a single entry by ID."""
    await verify_api_key(x_api_key)
    from memtext.db import get_entry, update_entry, get_db_path

    if not get_db_path().exists():
        raise HTTPException(status_code=404, detail="Entry not found")

    entry = get_entry(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    update_entry(
        entry_id,
        access_count=entry.get("access_count", 0) + 1,
        last_accessed=datetime.now().isoformat(),
    )

    return {
        "id": entry["id"],
        "title": entry["title"],
        "content": entry["content"],
        "entry_type": entry["entry_type"],
        "tags": entry.get("tags", ""),
        "importance": entry.get("importance", 1),
        "source": entry.get("source", "manual"),
        "created_at": entry.get("created_at", ""),
        "last_accessed": entry.get("last_accessed"),
        "access_count": entry.get("access_count", 0),
    }


@app.post("/entries", status_code=201)
@limiter.limit("60/minute")
async def create_entry(
    request: Request,
    entry: EntryCreate,
    x_api_key: Optional[str] = Header(None),
):
    """Create a new context entry."""
    await verify_api_key(x_api_key)
    from memtext.db import add_entry, get_db_path

    if not get_db_path().exists():
        raise HTTPException(
            status_code=400,
            detail="Database not initialized. Run 'memtext init' first.",
        )

    entry_id = add_entry(
        title=entry.title,
        content=entry.content,
        entry_type=entry.entry_type,
        tags=entry.tags,
        importance=entry.importance,
    )

    if entry_id < 0:
        raise HTTPException(status_code=409, detail="Entry already exists")

    # Trigger webhooks for create event
    from memtext.db import trigger_webhook

    entry_data = {"id": entry_id, "title": entry.title, "entry_type": entry.entry_type}
    trigger_webhook("create", entry_data)

    await manager.broadcast(
        {
            "type": "CREATE",
            "entry_id": entry_id,
            "title": entry.title,
        }
    )

    return {
        "id": entry_id,
        "title": entry.title,
        "content": entry.content,
        "entry_type": entry.entry_type,
    }


@app.put("/entries/{entry_id}")
@limiter.limit("60/minute")
async def update_entry_endpoint(
    request: Request,
    entry_id: int,
    entry: EntryUpdate,
    x_api_key: Optional[str] = Header(None),
):
    """Update an existing entry."""
    await verify_api_key(x_api_key)
    from memtext.db import update_entry, get_entry, get_db_path

    if not get_db_path().exists():
        raise HTTPException(status_code=404, detail="Entry not found")

    existing = get_entry(entry_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Entry not found")

    fields = {}
    if entry.title is not None:
        fields["title"] = entry.title
    if entry.content is not None:
        fields["content"] = entry.content
    if entry.entry_type is not None:
        fields["entry_type"] = entry.entry_type
    if entry.tags is not None:
        fields["tags"] = ",".join(entry.tags)
    if entry.importance is not None:
        fields["importance"] = entry.importance

    if fields:
        update_entry(entry_id, **fields)
        # Trigger webhooks for update event
        from memtext.db import trigger_webhook

        updated = get_entry(entry_id)
        trigger_webhook("update", updated)
        await manager.broadcast(
            {
                "type": "UPDATE",
                "entry_id": entry_id,
                "fields": list(fields.keys()),
            }
        )

    updated = get_entry(entry_id)
    return {
        "id": updated["id"],
        "title": updated["title"],
        "content": updated["content"],
    }


@app.delete("/entries/{entry_id}")
@limiter.limit("30/minute")
async def delete_entry_endpoint(
    request: Request,
    entry_id: int,
    x_api_key: Optional[str] = Header(None),
):
    """Delete an entry."""
    await verify_api_key(x_api_key)
    from memtext.db import delete_entry, get_entry, get_db_path

    if not get_db_path().exists():
        raise HTTPException(status_code=404, detail="Entry not found")

    existing = get_entry(entry_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Entry not found")

    delete_entry(entry_id)

    # Trigger webhooks for delete event
    from memtext.db import trigger_webhook

    trigger_webhook("delete", {"id": entry_id, "title": existing["title"]})

    await manager.broadcast(
        {
            "type": "DELETE",
            "entry_id": entry_id,
        }
    )

    return {"status": "deleted", "entry_id": entry_id}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket for real-time context updates."""
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                await manager.broadcast({"type": "ECHO", **message})
            except json.JSONDecodeError:
                await websocket.send_text('{"error": "Invalid JSON"}')
    except WebSocketDisconnect:
        manager.disconnect(websocket)


def run(host: str = "0.0.0.0", port: int = 8000, reload: bool = False):
    """Run the API server."""
    uvicorn.run(
        "memtext.api:app",
        host=host,
        port=port,
        reload=reload,
    )


if __name__ == "__main__":
    run()
