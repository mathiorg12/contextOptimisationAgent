# Context-Optimised Coding Agent (Dual-Model System)

This project implements a dual-model coding agent designed to minimize token consumption and cost by offloading context-heavy operations to a small model.

[Read the Detailed Project Documentation](PROJECT_DOCUMENTATION.md)

## Features
- **Dual-Model Architecture**: Uses a large model for reasoning and a small model for context extraction.
- **Automatic Context Optimization**: Large file reads are automatically redirected through the `context_processor` tool.
- **Token Efficiency**: Minimizes tokens sent to the expensive reasoning model.
- **Evaluation Framework**: Built-in benchmarking to compare token usage and success rates between single-model and dual-model approaches.

## Setup
1. Install dependencies:
   ```bash
   python3 -m pip install -r requirements.txt
   ```
2. Configure your API Key:
   Open the `.env` file and replace `'your_key'` with your actual Google AI API Key:
   ```bash
   GOOGLE_API_KEY='your_actual_key_here'
   ```

## Running the Evaluation
To see the system in action and view the token reduction report, run the evaluator as a module from the project root:
```bash
python3 -m eval.evaluator
```

## Project Structure
- `agent.py`: Main orchestration logic.
- `tools/`: Tool definitions including the `context_processor`.
- `models/`: Model provider and token tracking.
- `eval/`: Benchmark tasks and evaluator script.
