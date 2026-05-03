import json
import re
from typing import List, Dict, Any
from models.provider import ModelProvider
from tools.context_processor import ContextProcessor
from tools.file_tool import FileTool
from tools.search_tool import SearchTool
from tools.test_tool import TestTool

class LargeModelAgent:
    def __init__(self, provider: ModelProvider):
        self.provider = provider
        self.context_processor = ContextProcessor(provider)
        self.file_tool = FileTool(self.context_processor)
        self.search_tool = SearchTool()
        self.test_tool = TestTool()
        
        self.system_instruction = (
            "You are an advanced coding agent. You have access to tools to interact with a codebase.\n"
            "CRITICAL RULE: To keep context small, use the 'context_processor' for large files or logs.\n"
            "The 'read_file' tool automatically uses the context processor if the file is large, "
            "but you must provide a 'query' to guide the extraction.\n\n"
            "Tools available:\n"
            "1. search(pattern, path): Search for text in the codebase.\n"
            "2. read_file(file_path, query): Read a file. Provide a query for context optimization.\n"
            "3. write_file(file_path, content): Write to a file.\n"
            "4. run_tests(path): Run tests in a directory.\n"
            "5. context_processor(operation, query, content): Manually process large text.\n\n"
            "Format your response as:\n"
            "THOUGHT: <your reasoning>\n"
            "ACTION: <tool_name>(<arguments>)\n"
            "or\n"
            "FINAL_ANSWER: <your solution or summary>"
        )

    def run_task(self, task_description: str) -> str:
        history = [f"USER_TASK: {task_description}"]
        max_steps = 10
        
        for _ in range(max_steps):
            prompt = "\n".join(history)
            response = self.provider.call("large", prompt, system_instruction=self.system_instruction)
            history.append(f"ASSISTANT: {response}")
            
            if "FINAL_ANSWER:" in response:
                return response
                
            # Parse action
            action_match = re.search(r"ACTION: (\w+)\((.*)\)", response)
            if action_match:
                tool_name = action_match.group(1)
                args_str = action_match.group(2)
                
                # Simple argument parsing (could be improved)
                try:
                    # Try to parse as JSON list or just split by comma
                    if args_str.startswith("["):
                        args = json.loads(args_str)
                    else:
                        # Very naive split for this demo
                        args = [a.strip().strip("'").strip('"') for a in args_str.split(",")]
                    
                    observation = self.execute_tool(tool_name, args)
                    history.append(f"OBSERVATION: {observation}")
                except Exception as e:
                    history.append(f"OBSERVATION ERROR: {str(e)}")
            else:
                history.append("OBSERVATION: No valid ACTION found. Please specify an ACTION or FINAL_ANSWER.")
                
        return "Task failed: Max steps reached."

    def execute_tool(self, name: str, args: List[Any]) -> str:
        if name == "search":
            return self.search_tool.search(*args)
        elif name == "read_file":
            return self.file_tool.read_file(*args)
        elif name == "write_file":
            return self.file_tool.write_file(*args)
        elif name == "run_tests":
            return self.test_tool.run_tests(*args)
        elif name == "context_processor":
            return str(self.context_processor.process(*args))
        else:
            return f"Unknown tool: {name}"
