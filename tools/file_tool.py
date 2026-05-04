import os
from typing import Optional

from tools.context_processor import ContextProcessor
from utils.logger import get_logger

log = get_logger(__name__)


class FileTool:
    """
    File read/write tool with optional base_dir isolation.

    Parameters
    ----------
    context_processor : ContextProcessor | None
        When provided (and optimized=True), large file reads are routed through it.
    threshold_chars : int
        File byte-size above which the context processor is invoked on reads.
    optimized : bool
        Whether to use the context processor on large reads.
    base_dir : str | None
        If set, all *write* paths are resolved relative to this directory.
        The directory (and any sub-directories) is created automatically.
        Read paths are still resolved as-is so agents can inspect the project.
    """

    def __init__(
        self,
        context_processor: Optional[ContextProcessor] = None,
        threshold_chars: int = 2000,
        optimized: bool = True,
        base_dir: Optional[str] = None,
    ):
        self.context_processor = context_processor
        self.threshold_chars = threshold_chars
        self.optimized = optimized
        self.base_dir = base_dir

        if base_dir:
            os.makedirs(base_dir, exist_ok=True)
            log.debug("FileTool: output base_dir=%s (created if missing)", os.path.abspath(base_dir))
        else:
            log.debug("FileTool: no base_dir set — writes go to cwd")

        # Track files created during this run for reporting
        self.created_files: list[str] = []

    # ── Helpers ────────────────────────────────────────────────────────────────
    def _resolve_write_path(self, file_path: str) -> str:
        """
        Resolve a file path for writing.

        If base_dir is set, strip any leading '/', './', '../' components and
        place the file inside base_dir so agents can't accidentally write
        outside the sandbox.
        """
        if self.base_dir:
            # Strip dangerous path traversal before joining
            clean = os.path.normpath(file_path).lstrip("/").lstrip(".")
            # Remove leading separators after normpath
            while clean.startswith(os.sep):
                clean = clean[1:]
            resolved = os.path.abspath(os.path.join(self.base_dir, clean))
            # Safety check — must still be inside base_dir
            abs_base = os.path.abspath(self.base_dir)
            if not resolved.startswith(abs_base):
                log.warning(
                    "FileTool: path traversal attempt blocked — %s resolved to %s (outside %s)",
                    file_path, resolved, abs_base,
                )
                resolved = os.path.join(abs_base, os.path.basename(file_path))
            return resolved
        return os.path.abspath(file_path)

    # ── Public API ─────────────────────────────────────────────────────────────
    def read_file(self, file_path: str, query: Optional[str] = None) -> str:
        log.info("read_file: path=%s  query=%s", file_path, query)

        if not os.path.exists(file_path):
            log.warning("read_file: file not found — %s", file_path)
            return f"Error: File {file_path} not found."

        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        log.debug("read_file: read %d chars from %s", len(content), file_path)

        if (
            self.optimized
            and len(content) > self.threshold_chars
            and self.context_processor
            and query
        ):
            log.info(
                "read_file: file is large (%d chars > threshold %d) — routing through ContextProcessor",
                len(content),
                self.threshold_chars,
            )
            processed = self.context_processor.process(
                operation="extract",
                query=query,
                content=content,
                constraints={"max_lines": 50},
            )
            return (
                f"[CONTEXT OPTIMISED OUTPUT for {file_path}]\n"
                f"Summary: {processed.get('summary')}\n"
                f"Snippets:\n"
                + "\n".join([s.get("code", "") for s in processed.get("relevant_snippets", [])])
            )

        return content

    def write_file(self, file_path: str, content: str) -> str:
        resolved = self._resolve_write_path(file_path)

        log.info(
            "write_file: original_path=%s  resolved_path=%s  content_len=%d chars",
            file_path,
            resolved,
            len(content),
        )

        try:
            parent = os.path.dirname(resolved)
            if parent:
                os.makedirs(parent, exist_ok=True)
                log.debug("write_file: ensured parent dir %s", parent)

            with open(resolved, "w", encoding="utf-8") as f:
                f.write(content)

            self.created_files.append(resolved)
            log.info("write_file: SUCCESS — wrote %d chars to %s", len(content), resolved)
            return f"Successfully wrote {len(content)} chars to: {resolved}"

        except Exception as e:
            log.error("write_file: FAILED — path=%s  error=%s", resolved, str(e), exc_info=True)
            return f"Error writing file {resolved}: {e}"
