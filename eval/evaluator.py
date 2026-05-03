import os
import sys
import json
from models.provider import ModelProvider
from agent import LargeModelAgent

def run_evaluation():
    provider = ModelProvider()
    results = []

    tasks = [
        {"name": "Bug Fix", "task": "Fix the bug in bug_fix/utils.py. The calculate_sum function should add numbers, not subtract them. Run tests in bug_fix/ to verify."},
        {"name": "Feature", "task": "Add a 'multiply' method to the MathOps class in feature/math_ops.py."},
        {"name": "Refactor", "task": "Rename API_KEY to ACCESS_TOKEN in refactor/config.py and update refactor/client.py accordingly."}
    ]

    for mode in ["Baseline", "Optimised"]:
        print(f"\n--- Running Evaluation: {mode} Mode ---")
        for t in tasks:
            print(f"Task: {t['name']}")
            provider.reset_metrics()
            
            agent = LargeModelAgent(provider)
            # Configure agent based on mode
            if mode == "Baseline":
                agent.file_tool.optimized = False
            else:
                agent.file_tool.optimized = True
                agent.file_tool.threshold_chars = 500 # Strict optimization for eval
            
            try:
                # Change to task directory or handle paths correctly
                # For simplicity, we'll assume relative paths from root work
                output = agent.run_task(t['task'])
                metrics = provider.get_metrics()
                
                results.append({
                    "mode": mode,
                    "task": t['name'],
                    "success": "FINAL_ANSWER" in output,
                    "metrics": metrics
                })
            except Exception as e:
                print(f"Error in task {t['name']}: {str(e)}")

    # Generate Report
    generate_report(results)

def generate_report(results):
    print("\n\n" + "="*50)
    print("CONTEXT OPTIMISATION REPORT")
    print("="*50)
    
    # Aggregate by mode
    modes = {}
    for r in results:
        m = r['mode']
        if m not in modes:
            modes[m] = {"large_tokens": 0, "small_tokens": 0, "successes": 0, "tasks": 0}
        
        modes[m]["large_tokens"] += r['metrics']['large']['total']
        modes[m]["small_tokens"] += r['metrics']['small']['total']
        modes[m]["tasks"] += 1
        if r['success']:
            modes[m]["successes"] += 1

    print(f"{'Metric':<25} | {'Baseline':<15} | {'Optimised':<15}")
    print("-" * 60)
    
    base = modes.get("Baseline", {})
    opt = modes.get("Optimised", {})
    
    print(f"{'Tokens (Large Model)':<25} | {base.get('large_tokens', 0):<15} | {opt.get('large_tokens', 0):<15}")
    print(f"{'Tokens (Small Model)':<25} | {base.get('small_tokens', 0):<15} | {opt.get('small_tokens', 0):<15}")
    
    total_base = base.get('large_tokens', 0)
    total_opt = opt.get('large_tokens', 0) + opt.get('small_tokens', 0)
    
    print(f"{'Total Tokens':<25} | {total_base:<15} | {total_opt:<15}")
    
    reduction = 0
    if total_base > 0:
        reduction = (total_base - opt.get('large_tokens', 0)) / total_base * 100
    
    print(f"{'Large Model Reduction %':<25} | {'N/A':<15} | {reduction:.1f}%")
    print(f"{'Success Rate':<25} | {base.get('successes', 0)}/{base.get('tasks', 0):<13} | {opt.get('successes', 0)}/{opt.get('tasks', 0):<13}")
    print("="*50)

if __name__ == "__main__":
    # Ensure tasks are setup
    os.system("python3 eval/tasks/setup_tasks.py")
    run_evaluation()
