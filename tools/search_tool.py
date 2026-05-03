import subprocess
import os

class SearchTool:
    def search(self, pattern: str, path: str = ".") -> str:
        try:
            # Using ripgrep (rg) if available, otherwise fallback to grep
            cmd = ["rg", "--line-number", pattern, path]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                return result.stdout
            elif result.returncode == 1:
                return "No matches found."
            else:
                return f"Error: {result.stderr}"
        except FileNotFoundError:
            # Fallback to standard grep
            cmd = ["grep", "-rn", pattern, path]
            result = subprocess.run(cmd, capture_output=True, text=True)
            return result.stdout if result.returncode == 0 else "No matches found or error."
