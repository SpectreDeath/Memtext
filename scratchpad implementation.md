Adding a scratchpad mechanism to your agent workflows is a great way to let them draft, iterate, and reduce execution overhead before committing final text to persistent storage.

Based on the [Memtext repository](https://github.com/SpectreDeath/Memtext) structure, you can integrate this as a local runtime layer that interfaces cleanly with the existing file-based setup. Here is a modular blueprint for implementing the scratchpad, the post-LLM call hook, and the skill.

---

## 1. The Skill: Working with the Scratchpad

Since you are working with an agentic workflow, the skill needs to expose an interface for initializing, updating, and finalized-saving of the scratchpad. This keeps the scratchpad in memory (or a temporary dot-file) until the agent is ready to commit it.

```python
import os
from pathlib import Path

class ScratchpadSkill:
    """A skill that provides a temporary scratchpad for agent reasoning and drafting."""
    
    def __init__(self, project_root: str = "."):
        self.scratchpad_path = Path(project_root) / ".context" / "scratchpad.tmp"

    def write_scratchpad(self, content: str, append: bool = False) -> str:
        """Allows the agent to draft or update its thoughts."""
        self.scratchpad_path.parent.mkdir(exist_ok=True)
        mode = "a" if append else "w"
        with open(self.scratchpad_path, mode, encoding="utf-8") as f:
            f.write(content + "\n")
        return "Scratchpad updated successfully."

    def read_scratchpad(self) -> str:
        """Allows the agent to review its current draft."""
        if not self.scratchpad_path.exists():
            return "Scratchpad is empty."
        return self.scratchpad_path.read_text(encoding="utf-8")

    def flush_to_context(self, target_file: str = "decisions.md") -> str:
        """Flushes the scratchpad content into the permanent Memtext context and clears it."""
        if not self.scratchpad_path.exists():
            return "Nothing to save; scratchpad is empty."
        
        content = self.scratchpad_path.read_text(encoding="utf-8").strip()
        if not content:
            return "Scratchpad content is empty."

        # Append to the permanent memtext file format
        target_path = self.scratchpad_path.parent / target_file
        with open(target_path, "a", encoding="utf-8") as f:
            f.write(f"\n\n\n{content}\n")
            
        # Clean up the scratchpad
        self.scratchpad_path.unlink()
        return f"Scratchpad contents permanently saved to {target_file}."

```

---

## 2. The Hook: Triggering Scratchpad Usage

To trigger this automatically during agent operations, you can introduce a custom hook pattern that intercepts the agent's cycle. This aligns with the hook patterns referenced in `AGENTS.md`.

You can parse the agent's intent or look for a specific formatting marker (like a structural XML tag or a low confidence threshold) to decide whether to divert the execution to the scratchpad first.

```python
def post_llm_scratchpad_hook(agent_response: str, skill_set: ScratchpadSkill) -> str:
    """
    Hook executed immediately after an LLM call. 
    Determines if the agent is actively 'thinking out loud' or drafting, 
    and routes the text to the scratchpad if necessary.
    """
    # Pattern 1: Explicit routing via agent tagging
    if "<scratchpad>" in agent_response and "</scratchpad>" in agent_response:
        # Extract the scratchpad content
        start = agent_response.find("<scratchpad>") + len("<scratchpad>")
        end = agent_response.find("</scratchpad>")
        draft_content = agent_response[start:end].strip()
        
        # Save to scratchpad using the skill
        skill_set.write_scratchpad(draft_content, append=True)
        
        # Strip scratchpad logs out of the main execution stream so it doesn't pollute standard logs
        clean_response = agent_response[:agent_response.find("<scratchpad>")].strip()
        return f"[Hook Action: Draft saved to scratchpad]\n{clean_response}"
        
    # Pattern 2: Explicit command to commit the draft
    if "[COMMIT_SCRATCHPAD]" in agent_response:
        status = skill_set.flush_to_context(target_file="decisions.md")
        return f"[Hook Action: {status}]"

    return agent_response

```

---

## 3. Registering the Setup

To tie this into a tool like Cline or your own custom agent router, you will want to register the skill tools so the model knows *how* and *when* to execute them:

1. **Tooling Definition:** Present `write_scratchpad`, `read_scratchpad`, and `flush_to_context` as available function calls to the agent.
2. **System Prompting:** Update the agent system profile in `.context/identity.md` with explicit instructions:
> "When executing complex reasoning tasks, designing architecture changes, or drafting large blocks of documentation, use the `write_scratchpad` tool to iterate. When the task is complete and fully verified, execute `flush_to_context` to append the final results to your persistent project memory."



Got it. Instead of flushing or destructive-appending, we want to capture the scratchpad as a structured, discrete **memory artifact** within the `memtext` system. This preserves the iterative history of *how* the agent arrived at a conclusion alongside the standard context.

Here is how we can implement this using a dedicated workspace directory for staging artifacts, along with the necessary hook and skill definitions.

---

## 1. The Skill: Managing Memory Artifacts

This skill changes the behavior from destructive flushing to persisting the scratchpad as a snapshot (an artifact) within a managed `.context/artifacts/` or `.context/session-logs/` track, assigning metadata like timestamps or target files.

```python
import os
import json
from pathlib import Path
from datetime import datetime

class ArtifactMemorySkill:
    """Provides utility for managing temporary scratchpads and packaging them into memory artifacts."""
    
    def __init__(self, project_root: str = "."):
        self.project_root = Path(project_root)
        self.scratchpad_path = self.project_root / ".context" / "scratchpad.tmp"
        self.artifacts_dir = self.project_root / ".context" / "artifacts"

    def write_scratchpad(self, content: str, append: bool = False) -> str:
        """Standard scratchpad writing utility for the agent's iterative drift."""
        self.scratchpad_path.parent.mkdir(exist_ok=True)
        mode = "a" if append else "w"
        with open(self.scratchpad_path, mode, encoding="utf-8") as f:
            f.write(content + "\n")
        return "Scratchpad updated."

    def read_scratchpad(self) -> str:
        """Allows the agent to view current scratchpad buffer."""
        if not self.scratchpad_path.exists():
            return "Scratchpad is empty."
        return self.scratchpad_path.read_text(encoding="utf-8")

    def save_as_artifact(self, artifact_name: str, scope: str = "general") -> str:
        """
        Transforms the current scratchpad contents into a persistent memory artifact.
        Leaves the scratchpad intact or clears it depending on agent choice, but preserves
        the historical record structurally.
        """
        if not self.scratchpad_path.exists():
            return "Error: No scratchpad content found to convert into an artifact."
            
        scratch_content = self.scratchpad_path.read_text(encoding="utf-8").strip()
        if not scratch_content:
            return "Error: Scratchpad is blank."

        self.artifacts_dir.mkdir(exist_ok=True)
        
        # Build clean filename and structured frontmatter/metadata
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = artifact_name.lower().replace(" ", "_").replace("/", "-")
        artifact_file = self.artifacts_dir / f"artifact_{timestamp}_{safe_name}.md"
        
        artifact_structure = f"""---
type: memory_artifact
created: {datetime.now().isoformat()}
scope: {scope}
name: {artifact_name}
---

# Memory Artifact: {artifact_name}

## Intent / Process History
Captured scratchpad execution trace for analytical transparency.

## Contents
```text
{scratch_content}

```

"""
with open(artifact_file, "w", encoding="utf-8") as f:
f.write(artifact_structure)

```
    return f"Successfully saved scratchpad state as memory artifact: {artifact_file.name}"

```

```

---

## 2. The Hook: Signaling Artifact Compilation
To let your core loop catch this and convert it without manual workflow injection, the Post-LLM hook can scan for explicit formatting blocks like `<scratchpad_artifact>` parsing.

```python
import re

def post_llm_artifact_hook(agent_response: str, skill: ArtifactMemorySkill) -> str:
    """
    Scans the LLM output stream for memory tracking parameters.
    If the agent wraps its output with an artifact directive, it automatically compiles it.
    """
    # Look for syntax pattern: <artifact name="Architecture Draft" scope="database">...</artifact>
    pattern = r'<artifact\s+name="([^"]+)"(?:\s+scope="([^"]+)")?>(.*?)</artifact>'
    match = re.search(pattern, agent_response, re.DOTALL)
    
    if match:
        name = match.group(1)
        scope = match.group(2) if match.group(2) else "general"
        content = match.group(3).strip()
        
        # Direct write step straight to scratchpad staging
        skill.write_scratchpad(content, append=False)
        
        # Commit directly as a decoupled artifact track
        status_msg = skill.save_as_artifact(artifact_name=name, scope=scope)
        
        # Strip out block from standard stdout/execution response so it doesn't double-log
        clean_response = re.sub(pattern, f"\n[System Hook: {status_msg}]\n", agent_response, flags=re.DOTALL)
        return clean_response
        
    return agent_response

```

---

## 3. How the Agent Invokes It

By providing this framework, an agent running locally can construct a plan inside its response window without risking context drift or running up file sizes in `identity.md` or `decisions.md`:

```xml
I am outlining the network visualization module dependencies. 
I'll store this as an artifact so I can look up the constraints later without polluting active files.

<artifact name="Gephi Network Data Graph Rules" scope="visualization">
- Extract edge tables strictly from memory-engine data outputs.
- Filter out isolated components with node degree < 1.
- Target layout preset: ForceAtlas2 for modular cluster mapping.
</artifact>

```

The hook intercepts this, compiles `artifact_20260613_082953_gephi_network_data_graph_rules.md`, and keeps your primary configuration documents uncluttered.

Yes, exactly. The artifact setup is built to save directly inside the `.context/` directory structure, keeping it safely encapsulated where `memtext` manages local project memory.

Because `memtext init` pre-configures a `.gitignore` inside the `.context/` folder itself, everything nested under it—including a new `artifacts/` subdirectory—is automatically caught by git and shielded from being pushed to GitHub. This prevents project context, thought processes, and internal system architecture notes from leaking into public or shared repositories.

To align perfectly with the standard directory layout, the artifacts are stored like this:

```text
.context/
   .gitignore          # <-- Blocks this entire folder from Git leakage
   identity.md         
   decisions.md        
   artifacts/          # <-- New directory for memory snapshots
     artifact_20260613_082953_graph_rules.md
   session-logs/       
     2026-06-13.md

```

Using this approach, your agents can generate high-fidelity technical snapshots or track complex line-of-thought steps dynamically, keeping your workspace uncluttered and your data completely local.