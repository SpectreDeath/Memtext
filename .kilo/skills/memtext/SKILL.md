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
  action: string        # "init", "save", "query", "log", "add", "list", "migrate", "synthesize"
  text: string          # Context text to save/query
  tags: array           # Optional tags for organization
  type: string          # Entry type: decision, pattern, note, error, convention, memory
  importance: int       # 1-5 importance level
  limit: int            # Max results for queries
  session: string       # Session identifier for logs
  scan: bool            # Scan for projects
  all: bool             # Process all logs (not just recent)
```

## Output Format

```yaml
context_result:
  status: "success" | "error" | "not_found"
  message: string
  entry_id: int         # For add operations
  results: array        # For query operations
  new_memories: int     # For synthesize operations
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

### 8. Migration

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

## Configuration

- `.context/` - Context storage directory (customizable)
- `.context/memtext.db` - SQLite database
- `~/.config/memtext/projects.db` - Global project registry

## Integration

- **Before answering**: Query context for relevant prior decisions
- **After making decision**: `memtext save` to record
- **Session end**: `memtext log` to summarize
- **Periodic**: `memtext synthesize` to extract memories

## Dependencies

- Python 3.10+
- Standard library: pathlib, re, datetime
- SQLite (built-in)
- Optional: ruff (linting)