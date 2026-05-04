"""
Baseline Agent — Approach 1: Large Model Only.

The large model (gemini-flash-latest) is responsible for ALL steps:
planning, deciding tool calls, executing tools, and writing files.

All file writes are sandboxed to output/baseline/.
"""

import json
import os
import re
import time
from typing import Any, List

from models.provider import ModelProvider
from tools.context_processor import ContextProcessor
from tools.file_tool import FileTool
from tools.search_tool import SearchTool
from tools.test_tool import TestTool
from utils.logger import get_logger

log = get_logger(__name__)

# Absolute path for sandboxed output
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASELINE_OUTPUT_DIR = os.path.join(_PROJECT_ROOT, "output", "baseline")

SYSTEM_INSTRUCTION = """\
You are an advanced coding agent with FULL SYSTEM ACCESS.

CRITICAL RULES:
1. To create or modify files you MUST use the 'write_file' tool.
2. DO NOT show code in your response and claim the file is created — you MUST actually CALL the tool.
3. After every tool call you will receive an OBSERVATION. Read it carefully.
4. Only emit FINAL_ANSWER after you have received a successful write_file OBSERVATION.

Available tools:
  search(pattern, path)          — grep for a pattern in a directory
  read_file(file_path, query)    — read a file (large files auto-summarised)
  write_file(file_path, content) — CREATE or OVERWRITE a file on disk
  run_tests(path)                — run pytest on a path
  list_files(path)               — list directory contents

Tool call format (strict JSON — no markdown fences):
THOUGHT: <your reasoning>
ACTION: {"tool": "tool_name", "args": ["arg1", "arg2"]}

Example — creating a file:
THOUGHT: I need to create hello.py with a print statement.
ACTION: {"tool": "write_file", "args": ["hello.py", "print('Hello, World!')"]}

After you get back OBSERVATION: Successfully wrote ... you may emit:
FINAL_ANSWER: <summary of what you did>
"""


class BaselineAgent:
    """Single large-model ReAct agent."""

    def __init__(self, provider: ModelProvider, max_steps: int = 12):
        self.provider = provider
        self.max_steps = max_steps

        self.context_processor = ContextProcessor(provider)
        self.file_tool = FileTool(
            context_processor=self.context_processor,
            optimized=False,          # Baseline: no context optimisation
            base_dir=BASELINE_OUTPUT_DIR,
        )
        self.search_tool = SearchTool()
        self.test_tool = TestTool()

        log.info(
            "[BaselineAgent] Initialised — output_dir=%s  max_steps=%d",
            BASELINE_OUTPUT_DIR,
            max_steps,
        )

    def run_task(self, task_description: str) -> dict:
        """
        Execute a task and return a result dict with:
          output, created_files, step_count, success, wall_time_s
        """
        log.info("[BaselineAgent] ══ Task START ══ %s", task_description)
        t_start = time.perf_counter()

        history: List[str] = [f"USER_TASK: {task_description}"]
        step = 0
        final_output = "Task failed: Max steps reached without FINAL_ANSWER."

        for step in range(1, self.max_steps + 1):
            log.info("[BaselineAgent] ── Step %d/%d ──", step, self.max_steps)

            prompt = "\n".join(history)
            response = self.provider.call(
                "large", prompt, system_instruction=SYSTEM_INSTRUCTION
            )

            # Guard: provider guarantees str, but thinking model can still be empty
            if response is None:
                response = ""
            if not response.strip():
                log.warning(
                    "[BaselineAgent] Step %d — large model returned EMPTY response "
                    "(thinking-model edge-case). Nudging.",
                    step,
                )
                history.append(
                    "ASSISTANT: (empty response)"
                    "\nOBSERVATION: Your response was empty. "
                    "You MUST output THOUGHT + ACTION: {...} or FINAL_ANSWER: ..."
                )
                continue

            history.append(f"ASSISTANT: {response}")
            log.debug("[BaselineAgent] Step %d response:\n%s", step, response[:500])

            if "FINAL_ANSWER:" in response:
                log.info("[BaselineAgent] FINAL_ANSWER received at step %d", step)
                final_output = response
                break

            action_match = re.search(r"ACTION:\s*(\{.*?\})", response, re.DOTALL)
            if action_match:
                try:
                    action_json = json.loads(action_match.group(1))
                    tool_name = action_json.get("tool", "")
                    args = action_json.get("args", [])

                    log.info(
                        "[BaselineAgent] Tool call — tool=%s  args=%s",
                        tool_name,
                        [str(a)[:80] for a in args],
                    )
                    observation = self._execute_tool(tool_name, args)
                    log.info(
                        "[BaselineAgent] Observation — tool=%s  result=%s",
                        tool_name,
                        str(observation)[:200],
                    )
                    history.append(f"OBSERVATION: {observation}")

                except json.JSONDecodeError as e:
                    log.error("[BaselineAgent] JSON parse error on ACTION: %s", e)
                    history.append(f"OBSERVATION ERROR: Could not parse ACTION JSON: {e}")
                except Exception as e:
                    log.error("[BaselineAgent] Tool execution error: %s", e, exc_info=True)
                    history.append(f"OBSERVATION ERROR: {e}")
            else:
                log.warning(
                    "[BaselineAgent] Step %d — no ACTION found in response. Nudging agent.",
                    step,
                )
                history.append(
                    "OBSERVATION: No valid ACTION found. "
                    "You MUST output either ACTION: {...} or FINAL_ANSWER: ..."
                )

        wall_time = time.perf_counter() - t_start
        created = self.file_tool.created_files[:]

        # Verify files actually exist on disk
        verified = []
        missing = []
        for fp in created:
            if os.path.exists(fp):
                verified.append(fp)
                log.info("[BaselineAgent] FILE_VERIFIED: %s", fp)
            else:
                missing.append(fp)
                log.error("[BaselineAgent] FILE_MISSING: %s", fp)

        success = "FINAL_ANSWER:" in final_output and len(verified) > 0

        log.info(
            "[BaselineAgent] ══ Task END ══  success=%s  steps=%d  wall_time=%.1fs  "
            "files_created=%d  files_verified=%d  files_missing=%d",
            success,
            step,
            wall_time,
            len(created),
            len(verified),
            len(missing),
        )

        return {
            "output": final_output,
            "created_files": verified,
            "missing_files": missing,
            "step_count": step,
            "success": success,
            "wall_time_s": round(wall_time, 2),
        }

    def _execute_tool(self, name: str, args: List[Any]) -> str:
        if name == "search":
            return self.search_tool.search(*args)
        elif name == "read_file":
            return self.file_tool.read_file(*args)
        elif name == "write_file":
            return self.file_tool.write_file(*args)
        elif name == "run_tests":
            return self.test_tool.run_tests(*args)
        elif name == "list_files":
            path = args[0] if args else "."
            try:
                entries = os.listdir(path)
                log.debug("list_files: path=%s  entries=%s", path, entries)
                return str(entries)
            except Exception as e:
                return str(e)
        else:
            log.warning("[BaselineAgent] Unknown tool requested: %s", name)
            return f"Unknown tool: {name}. Available: search, read_file, write_file, run_tests, list_files"
