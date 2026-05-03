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
            "You are an advanced coding agent with FULL SYSTEM ACCESS to the current directory.\n"
            "CRITICAL: If the user asks to create, modify, or delete a file, you MUST use the corresponding tool.\n"
            "DO NOT just output the code in your response; you must actually WRITE the file using 'write_file'.\n\n"
            "Tools available:\n"
            "1. search(pattern, path): Search for text.\n"
            "2. read_file(file_path, query): Read a file with context optimization.\n"
            "3. write_file(file_path, content): Create or overwrite a file. CRITICAL: Use this to apply changes!\n"
            "4. run_tests(path): Run tests.\n"
            "5. list_files(path): List contents of a directory.\n"
            "6. context_processor(operation, query, content): Process large data.\n\n"
            "Workflow:\n"
            "- First, use 'list_files' to understand the structure.\n"
            "- Use 'read_file' or 'search' to find relevant code.\n"
            "- Use 'write_file' to apply changes. You can use this multiple times.\n"
            "- Finally, use 'run_tests' to verify.\n\n"
            "Format your response as:\n"
            "THOUGHT: <your reasoning>\n"
            "ACTION: <tool_name>(<arguments>)\n"
            "or\n"
            "FINAL_ANSWER: <your summary of actions taken>"
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
                
                # Log action to console for debugging
                print(f"DEBUG: Agent calling tool {tool_name} with args {args_str[:100]}...")
                
                try:
                    # Simple argument parsing (could be improved)
                    # Handle quoted strings and escaped characters better
                    if args_str.startswith("["):
                        args = json.loads(args_str)
                    else:
                        # Extract arguments between quotes
                        args = re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"|\'([^\'\\]*(?:\\.[^\'\\]*)*)\'|([^,\s]+)', args_str)
                        args = [a[0] or a[1] or a[2] for a in args]
                    
                    observation = self.execute_tool(tool_name, args)
                    print(f"DEBUG: Tool {tool_name} returned: {str(observation)[:100]}...")
                    history.append(f"OBSERVATION: {observation}")
                except Exception as e:
                    print(f"DEBUG: Tool {tool_name} error: {str(e)}")
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
