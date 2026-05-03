import os
from typing import Optional
from tools.context_processor import ContextProcessor

class FileTool:
    def __init__(self, context_processor: Optional[ContextProcessor] = None, threshold_chars: int = 2000, optimized: bool = True):
        self.context_processor = context_processor
        self.threshold_chars = threshold_chars
        self.optimized = optimized

    def read_file(self, file_path: str, query: Optional[str] = None) -> str:
        if not os.path.exists(file_path):
            return f"Error: File {file_path} not found."
            
        with open(file_path, 'r') as f:
            content = f.read()
            
        if self.optimized and len(content) > self.threshold_chars and self.context_processor and query:
            # Automatic redirection
            print(f"File {file_path} is large ({len(content)} chars). Redirecting through Context Processor...")
            processed = self.context_processor.process(
                operation="extract",
                query=query,
                content=content,
                constraints={"max_lines": 50}
            )
            return f"[CONTEXT OPTIMISED OUTPUT for {file_path}]\nSummary: {processed.get('summary')}\nSnippets:\n" + \
                   "\n".join([s.get('code', '') for s in processed.get('relevant_snippets', [])])
        
        return content

    def write_file(self, file_path: str, content: str) -> str:
        with open(file_path, 'w') as f:
            f.write(content)
        return f"Successfully wrote to {file_path}"
