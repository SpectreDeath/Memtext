"""Domain models for Memtext.

These Pydantic v2 models define the public data structures used throughout
the Memtext codebase. They replace raw dictionary returns with type-safe
objects.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class Entry(BaseModel):
    """A memory entry (context item)."""
    id: Optional[int] = None
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1)
    entry_type: str = Field(..., description="Type: decision, pattern, note, error, convention, memory")
    tags: list[str] = Field(default_factory=list)
    importance: int = Field(default=1, ge=1, le=5)
    linked_files: list[str] = Field(default_factory=list)
    parent_tag: Optional[str] = None
    source: str = Field(default="manual", description="Origin: manual, synthesized, api, etc.")
    created_at: datetime
    updated_at: Optional[datetime] = None
    last_accessed: Optional[datetime] = None
    access_count: int = 0

    model_config = {"from_attributes": True}


class SharedEntry(BaseModel):
    """A shared entry across projects."""
    id: Optional[int] = None
    title: str
    content: str
    entry_type: str
    tags: list[str] = []
    importance: int = 1
    project_id: int
    created_at: datetime
    source: str = "shared"

    model_config = {"from_attributes": True}


class Reminder(BaseModel):
    """A time-based reminder for an entry."""
    id: Optional[int] = None
    entry_id: int
    message: str
    remind_at: datetime
    completed: bool = False
    created_at: datetime = Field(default_factory=datetime.now)

    model_config = {"from_attributes": True}


class Template(BaseModel):
    """A template for structured entries."""
    name: str
    description: str
    entry_type: str
    fields_schema: dict = Field(default_factory=dict)

    model_config = {"from_attributes": True}


class Webhook(BaseModel):
    """Registered webhook endpoint."""
    id: Optional[int] = None
    url: str
    event: str
    secret: Optional[str] = None
    active: bool = True
    created_at: datetime = Field(default_factory=datetime.now)

    model_config = {"from_attributes": True}


class Project(BaseModel):
    """Registered project in the workspace."""
    id: Optional[int] = None
    path: str
    name: str
    registered_at: datetime = Field(default_factory=datetime.now)

    model_config = {"from_attributes": True}


class VersionChange(BaseModel):
    """Audit log of entry modifications."""
    id: Optional[int] = None
    entry_id: int
    field_name: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    changed_at: datetime = Field(default_factory=datetime.now)

    model_config = {"from_attributes": True}
