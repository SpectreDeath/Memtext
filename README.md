# Memtext - Context Offloading for AI Agents

Persistent memory across sessions for coding agents.

## Installation

```bash
pip install memtext
```

## Quick Start

```bash
# Initialize context storage in current project
memtext init

# Save a decision
memtext save "We chose PostgreSQL for ACID compliance"

# Query prior context
memtext query "database decisions"
```

## Commands

- `memtext init` - Initialize `.context/` directory with templates
- `memtext save <text>` - Save context with optional tags
- `memtext query <text>` - Search context files
- `memtext log <text>` - Add session log entry

## File Structure

```
.context/
├── .gitignore
├── identity.md     # Project purpose, stack, conventions
├── decisions.md    # Architecture decisions
└── session-logs/   # Episodic notes
    └── 2026-04-10.md
```