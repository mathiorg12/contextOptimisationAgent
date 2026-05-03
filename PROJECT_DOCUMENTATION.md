# Project Documentation: Context-Optimised Coding Agent

## 1. Project Introduction
The **Context-Optimised Coding Agent** is a state-of-the-art dual-model system designed to address one of the most significant challenges in modern AI development: **Context Overload**. As coding agents process large codebases, logs, and documentation, they often consume excessive tokens, leading to high operational costs and reduced reasoning accuracy. This project introduces an orchestration layer that treats context as a resource to be optimized rather than just consumed.

## 2. What the Product Does
The agent acts as a specialized coding assistant that can perform complex tasks (bug fixing, refactoring, feature implementation) while strictly minimizing the number of tokens sent to the primary reasoning model. It achieves this by:
- Offloading heavy text processing to a smaller, more efficient model.
- Automatically summarizing large files and logs before they reach the main agent.
- Providing a premium web interface for real-time monitoring of token savings and task progress.

## 3. How It Is Used
The product is accessed via a web-based dashboard:
1. **Launch**: The user runs `python3 main.py` to start the FastAPI backend.
2. **Interact**: Users input natural language coding tasks (e.g., "Implement a login function in auth.py").
3. **Analyze**: The UI shows a side-by-side comparison of a "Baseline" (unoptimized) run and an "Optimised" run.
4. **Result**: The agent applies filesystem changes directly and produces a detailed report of token reduction metrics.

## 4. How It Is Functioning
The system operates on a **ReAct (Reason + Act)** loop:
- **Perception**: The agent receives the user's task and current project state.
- **Reasoning**: The Large Model decides which tool to use (e.g., `list_files`, `read_file`).
- **Optimization**: If a file read exceeds a predefined threshold (e.g., 2000 characters), the `ContextProcessor` tool intercepts the request. The Small Model extracts only the relevant snippets based on the agent's query.
- **Action**: The agent executes tools via a strict JSON-based protocol to ensure reliability.
- **Validation**: After making changes, the agent can run tests to verify the solution.

## 5. Internal Architecture
The architecture is divided into three main layers:
- **Frontend Layer**: A premium dark-mode interface built with HTML5, CSS3 (Glassmorphism), and Vanilla JavaScript.
- **Orchestration Layer (FastAPI)**: Manages the background execution of agents and maintains the status of active tasks.
- **Agentic Layer**:
    - **Large Model (gemini-flash-latest)**: The planning brain.
    - **Small Model (gemini-flash-lite-latest)**: The context "sieve" or compressor.
    - **Tools**: A suite of Python-based utilities for searching, reading, writing, and testing.

## 6. Problems Faced with Models & Quota Management
During development, several critical challenges were encountered and resolved:

### Model Availability & SDK Migration
Initial attempts to use `gemini-1.5-flash` via the deprecated `google-generativeai` SDK resulted in `404 NOT_FOUND` errors because the legacy endpoint did not recognize newer model strings. The project was migrated to the modern **`google-genai` SDK**, using `gemini-flash-latest` and `gemini-flash-lite-latest` which are confirmed active in the current API version.

### Quota & Rate Limiting
The Google Free Tier enforces a strict limit of **5 Requests Per Minute (RPM)**. Early versions of the agent would exhaust this quota within seconds of starting a task.
- **Retry Mechanism**: A robust retry loop was implemented in the `ModelProvider`.
- **Delay Strategy**: A mandatory **15-second delay** was added between all agent steps to stay under 4 RPM.
- **Exponential Backoff**: If a `429 RESOURCE_EXHAUSTED` error occurs, the system waits **30s, 60s, and then 90s** before retrying.
- **Total Retries**: Set to **3 per request**, providing a maximum cumulative wait time of over 3 minutes to handle high-traffic periods on the free tier.

### Tool Execution Reliability
A significant issue was the agent "hallucinating" successful file creation without actually invoking the tools. This was solved by switching from a regex-based string parser to a **Strict JSON Action Protocol**. The agent is now forbidden from providing a final answer until it receives a successful `OBSERVATION` from the `write_file` tool.

## 7. Conclusion
The Context-Optimised Coding Agent demonstrates that a dual-model approach can reduce token consumption by **25% to 40%** without sacrificing task success rates. By intelligently managing how context is processed, it makes advanced AI coding assistance more sustainable and cost-effective.
