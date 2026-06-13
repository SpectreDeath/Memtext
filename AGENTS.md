---
name: memtext
description: "Use when: context offloading, persistent memory across sessions, storing decisions, querying history, project memory management. Triggers: 'memtext', 'context storage', 'save context', 'remember', 'memory', 'persistent context'. NOT for: single-session tasks, when no persistence needed."
---

# Memtext

Context offloading for AI agents - persistent memory across sessions. This skill provides both filesystem-based context storage and SQLite-backed memory with full-text search.

## When to Use This Skill

Use this skill when:
- Saving agent context for future sessions
- Storing decisions and architecture choices
- Querying historical context
- Managing project memory across sessions
- Onboarding new agents with project context

Do NOT use this skill when:
- Single-session tasks only
- No persistence needed
- Project already has memory system

## Input Format

```yaml
context_request:
  action: string        # "init", "save", "query", "log", "add", "list", "migrate", "synthesize", "review"
  text: string          # Context text to save/query
  tags: array           # Optional tags for organization
  type: string          # Entry type: decision, pattern, note, error, convention, memory
  importance: int       # 1-5 importance level
  limit: int            # Max results for queries
  session: string       # Session identifier for logs
  scan: bool            # Scan for projects
  all: bool             # Process all logs (not just recent)
  trust_score: float    # Trust score for entry (0.0-1.0, default: 1.0)
  source: string        # Entry source: manual, agent, etc. (default: manual)
```

## Output Format

```yaml
context_result:
  status: "success" | "error" | "not_found"
  message: string
  entry_id: int         # For add operations
  results: array        # For query operations
  new_memories: int     # For synthesize operations
  trust_score: float    # Trust score for entry (0.0-1.0)
  source: string        # Entry source: manual, agent, etc.
```

## Capabilities

### 1. Initialize Context Storage

```bash
memtext init
```

Creates:
- `.context/` directory
- `identity.md` - Project purpose, stack, conventions
- `decisions.md` - Architecture decisions
- `artifacts/` - Scratchpad snapshots and immutable memory artifacts
- `session-logs/` - Daily session notes
- `memtext.db` - SQLite with FTS5 for full-text search
- Auto-updates `.gitignore`

### 2. Save Context

```bash
memtext save "We chose PostgreSQL for ACID compliance" --tags database architecture
```

Saves to `decisions.md` with timestamp and tags.

### 3. Query Context

```bash
memtext query database --limit 10
```

Searches all markdown files using regex. Returns matching lines with file source.

### 4. Session Logging

```bash
memtext log "Fixed auth bug with JWT refresh" --session bugfix
```

Creates daily session logs in `.context/session-logs/YYYY-MM-DD.md`.

### 5. SQLite Storage

```bash
# Add structured entry
memtext add "API Decision" --content "Use REST not GraphQL for now" --type decision --tags api,rest --importance 3

# List entries
memtext list --type decision --limit 20
```

Uses SQLite with full-text search (FTS5) for fast retrieval.

### 6. Memory Synthesis

```bash
# Scan logs for @memory markers
memtext synthesize

# Process all logs
memtext synthesize --all

# Manual synthesis
memtext synthesize --text "Title: Content (@tags: t1, t2)"
```

Extracts `@memory` markers from logs into structured memories.

### 7. Project Registry

```bash
# List registered projects
memtext projects

# Scan for projects with .context
memtext projects --scan
```

Cross-project tracking at `~/.config/memtext/projects.db`.

### 8. Agent Staging and Review

When AI agents generate context that needs human verification, they can mark it for review using the trust score and source fields:

```bash
# Agent adds content that needs review (low trust score)
memtext add "Agent-generated hypothesis" --content "This needs verification" --importance 3 --trust-score 0.5

# Or mark by source
memtext add "Agent-generated hypothesis" --content "This needs verification" --importance 3 --source "agent"
```

To review and verify agent-generated content:

```bash
# List content pending review
memtext review --limit 20

# Approve an entry (marks as trusted and human-reviewed)
memtext review --approve 123

# Reject and remove an entry
memtext review --reject 123
```

Entries with trust scores below 1.0 or sources other than 'manual' will appear in the review queue.

### Staging Memory and Artifacts

Use the scratchpad tier for non-destructive drafting when an agent needs to work through architecture changes, long-form reasoning, or multi-step plans before committing anything to core context files. The scratchpad is a temporary buffer for `scratchpad.tmp`; it lets agents iterate without introducing context drift into `identity.md`, `decisions.md`, or active session logs.

Manual scratchpad commands:

```bash
memtext scratchpad write "Draft the migration plan first"
memtext scratchpad read
memtext scratchpad artifact "Migration Plan Draft"
```

`memtext scratchpad artifact <name>` saves the current scratchpad content directly as an immutable memory artifact under `.context/artifacts/` and clears the temporary scratchpad by default. Filename collisions are resolved with a monotonic suffix counter such as `_1`, `_2` when multiple artifacts are created in the same second.

Automated artifact compilation is available through `post_llm_artifact_hook()`. When an agent wraps text in an `<artifact>` XML directive in its response stream, the hook captures the directive content, removes that block from the user-facing response to avoid double-logging, and saves it as a timestamped snapshot under `.context/artifacts/`.

```xml
<artifact name="Gephi Network Data Graph Rules" scope="visualization">
- Extract edge tables strictly from memory-engine data outputs.
- Filter out isolated components with node degree less than 1.
- Target layout preset: ForceAtlas2 for modular cluster mapping.
</artifact>
```

### 9. Migration

```bash
memtext migrate
```

Migrates v0.1.x filesystem context to SQLite database.

## Entry Types

| Type | Description |
|------|-------------|
| decision | Architecture decisions |
| pattern | Reusable patterns discovered |
| note | General notes |
| error | Errors and workarounds |
| convention | Project conventions |
| memory | Synthesized high-value memories |
| memory_artifact | Structured scratchpad or agent-process artifacts |

## Configuration

- `.context/` - Context storage directory (customizable)
- `.context/memtext.db` - SQLite database
- `~/.config/memtext/projects.db` - Global project registry

## Integration

- **Before answering**: Query context for relevant prior decisions
- **After making decision**: `memtext save` to record
- **After drafting or reasoning**: use `memtext scratchpad write/read/artifact` to stage and compile artifacts
- **Session end**: `memtext log` to summarize
- **After LLM calls**: Use `memtext log` or `memtext add` to capture insights (see post_llm_call hook below)
- **Periodic**: `memtext synthesize` to extract memories

### Automatic post_llm_call Hook

To ensure valuable context from agent interactions is automatically preserved, integrate the following pattern into your agent frameworks:

#### For LangChain Agents
```python
from memtext.cli import main
import subprocess

def memtext_post_llm_hook(llm_output: str, context: str = ""):
    """Hook to call after LLM execution to save insights"""
    try:
        # Save the LLM output as a log entry
        subprocess.run(["memtext", "log", f"LLM Insight: {llm_output[:200]}..."], 
                      check=False)
        
        # If there's significant context, save it as a decision or pattern
        if len(context) > 50:  # Arbitrary threshold
            subprocess.run(["memtext", "add", "LLM-Generated Pattern", 
                          "--content", context[:500], 
                          "--type", "pattern", 
                          "--importance", "3"],
                          check=False)
    except Exception as e:
        # Don't let logging failures break the agent
        pass
```

#### For Custom MCP Servers
Add this to your session teardown loop:
```bash
# Save session summary
memtext log "Session completed: $(date) - Processed $TOKEN_COUNT tokens"

# Extract and save key insights
memtext synthesize --text "$SESSION_INSIGHTS (@tags: llm-generated, insight)"
```

#### Environment Configuration
Set up automatic hooking by adding to your agent's initialization:
```bash
# Enable PostgreSQL for better search (optional)
export MEMTEXT_DATABASE_URL="postgresql://user:pass@host:port/dbname"

# Install with PostgreSQL support
pip install memtext[postgres]
```

## Dependencies

- Python 3.10+
- Standard library: pathlib, re, datetime
- SQLite (built-in)
- Optional: ruff (linting)

## Agent API Functions

Memtext exposes a FastAPI REST server for external agent integration (`pip install memtext[api]`).

### Starting the API Server

```bash
memtext serve              # Default: 0.0.0.0:8000
memtext serve --port 9000
memtext serve --reload     # Hot-reload for development
```

Set the `MEMTEXT_API_KEY` environment variable for authentication (defaults to
`dev-key-change-in-production`).

### Authentication

All endpoints except `/health` require an `X-Api-Key` header:

```http
X-Api-Key: your-api-key
```

### Endpoints

| Method   | Path              | Description                                          |
|----------|-------------------|------------------------------------------------------|
| `GET`    | `/health`         | Health check — returns status, version, timestamp    |
| `GET`    | `/entries`        | List entries (filter by `entry_type`, `limit`)       |
| `GET`    | `/entries/{id}`   | Get single entry by ID (increments access count)     |
| `POST`   | `/entries`        | Create a new entry                                   |
| `PUT`    | `/entries/{id}`   | Update an existing entry (all fields optional)       |
| `DELETE` | `/entries/{id}`   | Delete an entry                                      |
| `WS`     | `/ws`             | WebSocket for real-time context update events        |

### Request / Response Schemas

**Create Entry (`POST /entries`)**

```json
{
  "title": "API Decision",
  "content": "Use REST not GraphQL for now",
  "entry_type": "decision",
  "tags": ["api", "rest"],
  "importance": 3
}
```

**Entry Response**

        ```json
        {
          "id": 42,
          "title": "API Decision",
          "content": "Use REST not GraphQL for now",
          "entry_type": "decision",
          "tags": "api,rest",
          "importance": 3,
          "source": "manual",
          "trust_score": 1.0,
          "created_at": "2026-04-15T13:00:00",
          "last_accessed": null,
          "access_count": 0
        }
        ```

**Update Entry (`PUT /entries/{id}`)** — all fields optional:

```json
{
  "title": "Updated Title",
  "importance": 5
}
```

### WebSocket Events

Connect to `ws://<host>/ws` to receive real-time broadcasts:

```json
{ "type": "CREATE", "entry_id": 42, "title": "New Entry" }
{ "type": "UPDATE", "entry_id": 42, "fields": ["title", "importance"] }
{ "type": "DELETE", "entry_id": 42 }
```

Clients can also send JSON messages which are echoed back as `{ "type": "ECHO", ... }`.

### Programmatic Usage

```python
from memtext.api import app  # FastAPI ASGI app instance
import uvicorn

uvicorn.run(app, host="0.0.0.0", port=8000)
```
