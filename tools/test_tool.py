import subprocess
import os

class TestTool:
    def run_tests(self, path: str = ".") -> str:
        # Check if pytest is available
        try:
            cmd = ["pytest", "-v", path]
            result = subprocess.run(cmd, capture_output=True, text=True)
            return f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        except Exception as e:
            return f"Error running tests: {str(e)}"
