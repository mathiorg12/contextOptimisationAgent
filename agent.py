import json
import re
import os
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
            "You are an advanced coding agent with FULL SYSTEM ACCESS.\n"
            "CRITICAL: To create or modify files, you MUST use the 'write_file' tool.\n"
            "DO NOT simply show the code in your response. You must EXECUTE the tool.\n\n"
            "Tools available:\n"
            "1. search(pattern, path)\n"
            "2. read_file(file_path, query)\n"
            "3. write_file(file_path, content)\n"
            "4. run_tests(path)\n"
            "5. list_files(path)\n"
            "6. context_processor(operation, query, content)\n\n"
            "To use a tool, you MUST use this exact JSON format:\n"
            "THOUGHT: <your reasoning>\n"
            "ACTION: {\"tool\": \"tool_name\", \"args\": [\"arg1\", \"arg2\"]}\n\n"
            "Example:\n"
            "THOUGHT: I need to create a hello world file.\n"
            "ACTION: {\"tool\": \"write_file\", \"args\": [\"hello.py\", \"print('hello')\"]}\n\n"
            "After every tool call, wait for the OBSERVATION. Once finished, use:\n"
            "FINAL_ANSWER: <summary of actions taken>"
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
                
            # Parse action (JSON format)
            action_match = re.search(r"ACTION: (\{.*\})", response)
            if action_match:
                try:
                    action_json = json.loads(action_match.group(1))
                    tool_name = action_json.get("tool")
                    args = action_json.get("args", [])
                    
                    print(f"DEBUG: Agent calling tool {tool_name} with {len(args)} args...")
                    
                    observation = self.execute_tool(tool_name, args)
                    print(f"DEBUG: Tool {tool_name} returned successfully.")
                    history.append(f"OBSERVATION: {observation}")
                except Exception as e:
                    print(f"DEBUG: Action parsing error: {str(e)}")
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
        elif name == "list_files":
            try:
                path = args[0] if args else "."
                return str(os.listdir(path))
            except Exception as e:
                return str(e)
        elif name == "context_processor":
            return str(self.context_processor.process(*args))
        else:
            return f"Unknown tool: {name}"
