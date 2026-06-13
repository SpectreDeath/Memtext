---
name: memtext-repository-updater
description: "Use when: updating or installing Memtext in another repository, initializing Memtext context in a target repository, adding .context/artifacts, or refreshing the local memtext skill used by agents."
compatibility: "Requires Python, git, and an available memtext CLI (`python -m memtext.cli`). Intended for local repositories that already use `.context/` and `.kilo/skills/memtext/`."
allowed-tools: "filesystem_list_directory filesystem_read_text_file filesystem_edit_file filesystem_write_file bash filesystem_create_directory"
---

# Memtext Repository Updater

Use this skill to update or install Memtext in a target repository. It standardizes the repeated workflow used to refresh Memtext context storage, artifact support, and the local `.kilo/skills/memtext/SKILL.md` agent skill.

## When to Use This Skill

Use this skill when a user asks to:

- Update Memtext in a repository.
- Install or initialize Memtext in a repository.
- Add the latest Memtext scratchpad and artifact workflow to a repository.
- Refresh `.context/` Memtext support in a target project.
- Update `.kilo/skills/memtext/SKILL.md` after Memtext changes.

Do not use this skill for single-session Memtext queries, general context offloading, or repository work that does not involve updating Memtext itself.

## Safety Rules

- Work in the target repository specified by the user.
- Do not modify unrelated application code, dependencies, tests, or package manifests unless explicitly requested.
- Do not commit or push changes unless explicitly requested.
- Do not overwrite existing `identity.md`, `decisions.md`, `skills.md`, or `memtext.db`.
- Preserve existing uncommitted work in the target repository.
- Treat `.context/` as local context storage unless `.context/.gitignore` itself is tracked.
- If `python -m memtext.cli` is unavailable, report the missing CLI instead of guessing or silently changing dependencies.

## Workflow

### 1. Inspect the Target Repository

Run these checks from the target repository root:

```bash
git status --short
git branch --show-current
git remote -v
```

Inspect whether the repository has Memtext context and skill files:

```text
.context/
.context/.gitignore
.kilo/skills/memtext/SKILL.md
```

If needed, inspect dependency references with:

```bash
grep -R "memtext\|Memtext" -n .
```

### 2. Initialize Memtext Context

Run Memtext initialization from the target repository root:

```bash
python -m memtext.cli init
```

Expected result:

```text
Initialized .context/ at <target-repository>/.context
Files created: identity.md, decisions.md, skills.md, skills/, session-logs/, artifacts/, .gitignore
```

Do not rerun this as a destructive operation; `memtext init` should create missing files and leave existing context files intact.

### 3. Enforce Local Context Ignore Rules

Update `.context/.gitignore` to ignore all nested Memtext context contents while preserving the nested ignore file:

```gitignore
# Memtext context
*
!.gitignore
```

If the root `.gitignore` lacks `.context/`, add a concise ignore entry:

```gitignore
# Memtext Context
.context/
```

### 4. Verify Artifact Directory

Ensure this directory exists:

```text
.context/artifacts/
```

If missing, create it.

### 5. Refresh the Local Memtext Skill

If `.kilo/skills/memtext/SKILL.md` exists, update it with the current scratchpad/artifact workflow.

Add `artifacts/` to the initialization list:

```markdown
- `artifacts/` - Scratchpad snapshots and immutable memory artifacts
```

Add a dedicated section titled `Staging Memory and Artifacts` after Project Registry and before Migration. Use this Markdown block:

````markdown
### 8. Staging Memory and Artifacts

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
````

Renumber Migration from `### 8` to `### 9`.

Update Integration bullets:

```markdown
- **After making decision**: `memtext save` to record
- **After drafting or reasoning**: use `memtext scratchpad write/read/artifact` to stage and compile artifacts
- **Session end**: `memtext log` to summarize
- **Periodic**: `memtext synthesize` to extract memories
```

### 6. Validate the CLI

From the target repository root, verify the Memtext CLI exposes scratchpad commands:

```bash
python -m memtext.cli scratchpad --help
```

Expected commands:

```text
write
read
clear
artifact
hook
```

### 7. Report Results

Report:

- Target repository path.
- Whether `.context/artifacts/` was created or already existed.
- Whether `.context/.gitignore` was updated.
- Whether `.kilo/skills/memtext/SKILL.md` was updated.
- Any tracked changes introduced.
- Any ignored `.context/` changes that will not appear in Git.
- Any blockers, such as missing Memtext CLI.

## Example Report

```text
Updated Memtext in D:\GitHub\projects\SME.

Changed:
- Ran `memtext init`.
- Created `.context/artifacts/`.
- Updated `.context/.gitignore`.
- Updated `.kilo/skills/memtext/SKILL.md`.

Validation:
- Ran `python -m memtext.cli scratchpad --help`.
- Confirmed scratchpad subcommands are available.

Note:
- `.context/` remains ignored as intended.
```
