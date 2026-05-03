import os

def setup_bug_fix_task():
    os.makedirs("bug_fix", exist_ok=True)
    with open("bug_fix/utils.py", "w") as f:
        f.write("# " + "A " * 500 + " large file header\n") # Make it large
        f.write("def calculate_sum(a, b):\n")
        f.write("    return a - b  # intentional bug\n\n")
        f.write("# " + "B " * 500 + " large file footer\n")
        
    with open("bug_fix/test_utils.py", "w") as f:
        f.write("from utils import calculate_sum\n")
        f.write("def test_calculate_sum():\n")
        f.write("    assert calculate_sum(2, 3) == 5\n")

def setup_feature_task():
    os.makedirs("feature", exist_ok=True)
    with open("feature/math_ops.py", "w") as f:
        f.write("class MathOps:\n")
        f.write("    def add(self, a, b): return a + b\n")

def setup_refactor_task():
    os.makedirs("refactor", exist_ok=True)
    with open("refactor/config.py", "w") as f:
        f.write("API_KEY = 'secret'\n")
    with open("refactor/client.py", "w") as f:
        f.write("import config\n")
        f.write("def connect(): return config.API_KEY\n")

if __name__ == "__main__":
    setup_bug_fix_task()
    setup_feature_task()
    setup_refactor_task()
    print("Tasks setup complete.")
