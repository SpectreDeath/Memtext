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
   .gitignore
   identity.md     # Project purpose, stack, conventions
   decisions.md    # Architecture decisions
   session-logs/   # Episodic notes
     2026-04-10.md
```

## PostgreSQL Support

Memtext supports PostgreSQL as an alternative database backend for advanced features including hybrid search, token-budget gating, and agent staging. See [PostgreSQL Documentation](docs/postgres.md) for details on setup and usage.

## Advanced Features

### Token-Budget Gating
Use `--max-tokens` with the query command to limit response size:
```bash
memtext query "machine learning" --max-tokens 500
```

### Agent Staging
Agent-generated content is automatically tagged with trust scores and sources for verification workflows.

### Post-LLM Call Hooks
Automatically capture LLM insights using the provided hook patterns in AGENTS.md.
