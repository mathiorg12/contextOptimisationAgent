import os
import time
from dataclasses import dataclass, field
from typing import Dict, Any, Optional

from google import genai
from google.genai import types
from dotenv import load_dotenv
from utils.logger import get_logger

log = get_logger(__name__)

# Load environment variables from .env in the project root
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(project_root, ".env"))


@dataclass
class TokenMetrics:
    input_tokens: int = 0
    output_tokens: int = 0
    call_count: int = 0
    total_latency_ms: float = 0.0

    def add(self, other: "TokenMetrics"):
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.call_count += other.call_count
        self.total_latency_ms += other.total_latency_ms

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def avg_latency_ms(self) -> float:
        if self.call_count == 0:
            return 0.0
        return self.total_latency_ms / self.call_count


class ModelProvider:
    def __init__(self):
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY not found in environment")

        self.client = genai.Client(api_key=api_key)

        # Using confirmed -latest variants from client.models.list()
        # DO NOT CHANGE THESE MODEL NAMES
        self.large_model_name = "gemini-flash-latest"
        self.small_model_name = "gemini-flash-lite-latest"

        self.metrics: Dict[str, TokenMetrics] = {
            "large": TokenMetrics(),
            "small": TokenMetrics(),
        }

        log.info(
            "ModelProvider initialised — large=%s  small=%s",
            self.large_model_name,
            self.small_model_name,
        )

    # ── Core call ──────────────────────────────────────────────────────────────
    def call(
        self,
        model_type: str,
        prompt: str,
        system_instruction: Optional[str] = None,
    ) -> str:
        model_name = (
            self.large_model_name if model_type == "large" else self.small_model_name
        )

        config = None
        if system_instruction:
            config = types.GenerateContentConfig(
                system_instruction=system_instruction
            )

        log.info(
            "[CALL START] model_type=%s  model=%s  prompt_len=%d chars",
            model_type,
            model_name,
            len(prompt),
        )

        max_retries = 3
        last_error = ""
        for attempt in range(max_retries):
            try:
                # 15 s delay → max ~4 RPM (Free tier is 5 RPM)
                log.debug("Rate-limit delay: sleeping 15 s before API call (attempt %d/%d)", attempt + 1, max_retries)
                time.sleep(15)

                t0 = time.perf_counter()
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=config,
                )
                elapsed_ms = (time.perf_counter() - t0) * 1000

                # Track metrics
                in_tok = 0
                out_tok = 0
                if response.usage_metadata:
                    in_tok = response.usage_metadata.prompt_token_count or 0
                    out_tok = response.usage_metadata.candidates_token_count or 0

                self.metrics[model_type].input_tokens += in_tok
                self.metrics[model_type].output_tokens += out_tok
                self.metrics[model_type].call_count += 1
                self.metrics[model_type].total_latency_ms += elapsed_ms

                log.info(
                    "[CALL OK] model=%s  in_tokens=%d  out_tokens=%d  latency=%.0f ms",
                    model_name,
                    in_tok,
                    out_tok,
                    elapsed_ms,
                )
                # response.text can be None when the model returns only a
                # thought_signature part (thinking models). Extract text safely.
                text = response.text
                if text is None:
                    # Fallback: concatenate text from individual parts
                    try:
                        parts = response.candidates[0].content.parts
                        text = "".join(
                            p.text for p in parts if hasattr(p, "text") and p.text
                        )
                        if text:
                            log.debug("[RESPONSE] Recovered text from parts (%d chars)", len(text))
                        else:
                            log.warning(
                                "[RESPONSE] model=%s returned no usable text — "
                                "out_tokens=%d. Returning empty string.",
                                model_name, out_tok,
                            )
                            text = ""
                    except Exception as part_err:
                        log.warning("[RESPONSE] part extraction failed: %s", part_err)
                        text = ""

                log.debug("[RESPONSE] %s", text[:300] if text else "(empty)")
                return text

            except Exception as e:
                last_error = str(e)
                if "429" in last_error or "RESOURCE_EXHAUSTED" in last_error:
                    wait_time = 30 * (attempt + 1)
                    log.warning(
                        "[QUOTA ERROR] attempt=%d/%d  wait=%ds  error=%s",
                        attempt + 1,
                        max_retries,
                        wait_time,
                        last_error,
                    )
                    time.sleep(wait_time)
                    continue
                log.error("[UNEXPECTED ERROR] model=%s  error=%s", model_name, last_error, exc_info=True)
                raise

        log.error("[MAX RETRIES REACHED] model=%s  last_error=%s", model_name, last_error)
        return f"Error: Maximum retries reached. Last error: {last_error}"

    # ── Metrics ────────────────────────────────────────────────────────────────
    def get_metrics(self) -> Dict[str, Any]:
        def _serialise(m: TokenMetrics) -> Dict[str, Any]:
            return {
                "input": m.input_tokens,
                "output": m.output_tokens,
                "total": m.total_tokens,
                "call_count": m.call_count,
                "total_latency_ms": round(m.total_latency_ms, 1),
                "avg_latency_ms": round(m.avg_latency_ms, 1),
            }

        return {
            "large": _serialise(self.metrics["large"]),
            "small": _serialise(self.metrics["small"]),
        }

    def reset_metrics(self):
        self.metrics = {
            "large": TokenMetrics(),
            "small": TokenMetrics(),
        }
        log.debug("Metrics reset.")
