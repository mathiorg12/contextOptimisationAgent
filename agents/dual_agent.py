"""
Dual Agent — Approach 2: Planner (Large) + Executor (Small).

Workflow:
  1. PLANNING PHASE — large model receives the task and returns a JSON array
     of concrete steps (each step is a plain English instruction).
  2. EXECUTION PHASE — for each step the small model runs a mini ReAct loop,
     calling tools to carry out that specific step.

All file writes are sandboxed to output/optimised/.
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

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPTIMISED_OUTPUT_DIR = os.path.join(_PROJECT_ROOT, "output", "optimised")

# ── System prompts ─────────────────────────────────────────────────────────────

PLANNER_SYSTEM = """\
You are a Planning Agent. Your ONLY job is to break a coding task into a numbered list of small, concrete steps.

Rules:
- Return ONLY a valid JSON array of strings.
- Each string must be a single, self-contained instruction (e.g. "Create file hello.py containing print('Hello World')").
- Do NOT include explanations, markdown fences, or commentary — just the JSON array.
- Keep each step simple enough for a junior model to execute with one tool call.
- Maximum 8 steps.

Example output:
["Create file utils.py with a function called add(a, b) that returns a + b",
 "Create file test_utils.py that imports add and asserts add(1, 2) == 3"]
"""

EXECUTOR_SYSTEM = """\
You are an Execution Agent. You carry out exactly ONE instruction given to you using the available tools.

CRITICAL RULES:
1. To create or write a file you MUST call the 'write_file' tool.
2. Do NOT show code and claim the task is done — you MUST actually CALL the tool.
3. After the OBSERVATION confirms success, emit STEP_DONE: <brief summary>.
4. If the tool fails, emit STEP_FAILED: <reason>.

Available tools:
  search(pattern, path)          — grep for a pattern
  read_file(file_path, query)    — read a file
  write_file(file_path, content) — CREATE or OVERWRITE a file on disk
  run_tests(path)                — run pytest
  list_files(path)               — list directory contents

Tool call format (strict JSON):
THOUGHT: <reasoning>
ACTION: {"tool": "tool_name", "args": ["arg1", "arg2"]}
"""


class DualAgent:
    """Planner (large) + Executor (small) dual-model agent."""

    def __init__(self, provider: ModelProvider, max_exec_steps: int = 5):
        self.provider = provider
        self.max_exec_steps = max_exec_steps

        self.context_processor = ContextProcessor(provider)
        self.file_tool = FileTool(
            context_processor=self.context_processor,
            optimized=True,                 # Optimised: uses context processor
            threshold_chars=500,
            base_dir=OPTIMISED_OUTPUT_DIR,
        )
        self.search_tool = SearchTool()
        self.test_tool = TestTool()

        log.info(
            "[DualAgent] Initialised — output_dir=%s  max_exec_steps=%d",
            OPTIMISED_OUTPUT_DIR,
            max_exec_steps,
        )

    # ── Public entry point ─────────────────────────────────────────────────────
    def run_task(self, task_description: str) -> dict:
        """
        Execute a task using the Planner + Executor pattern.
        Returns a result dict compatible with BaselineAgent.run_task().
        """
        log.info("[DualAgent] ══ Task START ══ %s", task_description)
        t_start = time.perf_counter()

        # ── Phase 1: Plan ──────────────────────────────────────────────────────
        steps = self._plan(task_description)
        if not steps:
            wall = time.perf_counter() - t_start
            log.error("[DualAgent] Planning produced no steps — aborting.")
            return {
                "output": "PLANNING FAILED: No steps generated.",
                "created_files": [],
                "missing_files": [],
                "step_count": 0,
                "success": False,
                "wall_time_s": round(wall, 2),
            }

        log.info("[DualAgent] Plan produced %d step(s):", len(steps))
        for i, s in enumerate(steps, 1):
            log.info("  Step %d: %s", i, s)

        # ── Phase 2: Execute each step ─────────────────────────────────────────
        step_results = []
        for idx, step_desc in enumerate(steps, 1):
            log.info("[DualAgent] ── Executing step %d/%d: %s ──", idx, len(steps), step_desc)
            result = self._execute_step(step_desc, idx)
            step_results.append(result)
            log.info(
                "[DualAgent] Step %d done — success=%s  obs=%s",
                idx,
                result["success"],
                result["observation"][:120],
            )

        # ── Final summary ──────────────────────────────────────────────────────
        wall = time.perf_counter() - t_start
        created = self.file_tool.created_files[:]

        verified, missing = [], []
        for fp in created:
            if os.path.exists(fp):
                verified.append(fp)
                log.info("[DualAgent] FILE_VERIFIED: %s", fp)
            else:
                missing.append(fp)
                log.error("[DualAgent] FILE_MISSING: %s", fp)

        all_success = all(r["success"] for r in step_results)
        success = all_success and len(verified) > 0

        # Build a human-readable output summary
        lines = [f"PLANNER + EXECUTOR — {len(steps)} step(s) planned\n"]
        for i, (s, r) in enumerate(zip(steps, step_results), 1):
            status = "✅" if r["success"] else "❌"
            lines.append(f"{status} Step {i}: {s}")
            lines.append(f"   └─ {r['observation'][:200]}")
        lines.append(f"\nFiles created: {[os.path.basename(f) for f in verified]}")
        if missing:
            lines.append(f"Files MISSING: {missing}")
        final_output = "\n".join(lines)
        if success:
            final_output = "FINAL_ANSWER: " + final_output

        log.info(
            "[DualAgent] ══ Task END ══  success=%s  steps_planned=%d  "
            "wall_time=%.1fs  files_verified=%d  files_missing=%d",
            success,
            len(steps),
            wall,
            len(verified),
            len(missing),
        )

        return {
            "output": final_output,
            "created_files": verified,
            "missing_files": missing,
            "step_count": len(steps),
            "success": success,
            "wall_time_s": round(wall, 2),
        }

    # ── Planning phase ─────────────────────────────────────────────────────────
    def _plan(self, task_description: str) -> List[str]:
        log.info("[DualAgent][PLANNER] Requesting plan from large model...")

        prompt = f"Task: {task_description}\n\nBreak this into steps (JSON array only):"
        raw = self.provider.call("large", prompt, system_instruction=PLANNER_SYSTEM)

        # Guard: provider can return None or empty string (thinking model edge-case)
        if not raw or not raw.strip():
            log.error(
                "[DualAgent][PLANNER] Large model returned empty response — cannot plan."
            )
            return []

        log.debug("[DualAgent][PLANNER] Raw response:\n%s", raw[:600])

        # Extract JSON array from response (model may wrap in fences)
        try:
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0].strip()
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0].strip()

            # Find the first '[' ... last ']'
            start = raw.find("[")
            end = raw.rfind("]")
            if start != -1 and end != -1:
                raw = raw[start : end + 1]

            steps = json.loads(raw)
            if isinstance(steps, list) and all(isinstance(s, str) for s in steps):
                log.info("[DualAgent][PLANNER] Parsed %d steps successfully.", len(steps))
                return steps
            else:
                log.warning("[DualAgent][PLANNER] Unexpected JSON structure: %s", steps)
                return []
        except Exception as e:
            log.error("[DualAgent][PLANNER] Failed to parse plan JSON: %s\nRaw:\n%s", e, raw[:400])
            return []

    # ── Execution phase (one step) ─────────────────────────────────────────────
    def _execute_step(self, step_desc: str, step_num: int) -> dict:
        """Run a mini ReAct loop with the SMALL model to execute one step."""
        history = [
            f"INSTRUCTION: {step_desc}\n"
            "Use the tools to carry this out now. "
            "After a successful OBSERVATION emit STEP_DONE: <summary>."
        ]
        observation = "No observation yet."
        success = False

        for attempt in range(1, self.max_exec_steps + 1):
            log.debug(
                "[DualAgent][EXECUTOR] Step %d — attempt %d/%d",
                step_num,
                attempt,
                self.max_exec_steps,
            )
            prompt = "\n".join(history)
            response = self.provider.call(
                "small", prompt, system_instruction=EXECUTOR_SYSTEM
            )

            # Guard: provider guarantees a str, but defensive check anyway
            if response is None:
                response = ""
            if not response.strip():
                log.warning(
                    "[DualAgent][EXECUTOR] Step %d attempt %d — small model returned "
                    "EMPTY response (thinking-model edge-case). Nudging.",
                    step_num, attempt,
                )
                history.append(
                    "ASSISTANT: (empty response)"
                    "\nOBSERVATION: Your response was empty. "
                    "You MUST output THOUGHT + ACTION: {...} or STEP_DONE: ..."
                )
                continue

            history.append(f"ASSISTANT: {response}")
            log.debug("[DualAgent][EXECUTOR] Response:\n%s", response[:400])

            if "STEP_DONE:" in response:
                observation = response.split("STEP_DONE:", 1)[1].strip()
                success = True
                log.info("[DualAgent][EXECUTOR] STEP_DONE at attempt %d", attempt)
                break

            if "STEP_FAILED:" in response:
                observation = response.split("STEP_FAILED:", 1)[1].strip()
                log.warning("[DualAgent][EXECUTOR] STEP_FAILED: %s", observation)
                break

            action_match = re.search(r"ACTION:\s*(\{.*?\})", response, re.DOTALL)
            if action_match:
                try:
                    action_json = json.loads(action_match.group(1))
                    tool_name = action_json.get("tool", "")
                    args = action_json.get("args", [])

                    log.info(
                        "[DualAgent][EXECUTOR] Tool call — tool=%s  args=%s",
                        tool_name,
                        [str(a)[:80] for a in args],
                    )
                    obs = self._execute_tool(tool_name, args)
                    observation = obs
                    log.info(
                        "[DualAgent][EXECUTOR] Observation — tool=%s  result=%s",
                        tool_name,
                        str(obs)[:200],
                    )
                    history.append(f"OBSERVATION: {obs}")

                except json.JSONDecodeError as e:
                    log.error("[DualAgent][EXECUTOR] JSON parse error: %s", e)
                    history.append(f"OBSERVATION ERROR: Could not parse ACTION JSON: {e}")
                except Exception as e:
                    log.error("[DualAgent][EXECUTOR] Tool error: %s", e, exc_info=True)
                    history.append(f"OBSERVATION ERROR: {e}")
            else:
                log.warning(
                    "[DualAgent][EXECUTOR] No ACTION found in step %d attempt %d — nudging.",
                    step_num,
                    attempt,
                )
                history.append(
                    "OBSERVATION: No ACTION found. "
                    "You MUST output ACTION: {...} or STEP_DONE: ..."
                )

        return {"success": success, "observation": observation}

    # ── Tool dispatch ──────────────────────────────────────────────────────────
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
            log.warning("[DualAgent][EXECUTOR] Unknown tool: %s", name)
            return f"Unknown tool: {name}. Available: search, read_file, write_file, run_tests, list_files"
