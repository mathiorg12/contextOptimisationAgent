import json
from typing import Dict, Any, List
from models.provider import ModelProvider

class ContextProcessor:
    def __init__(self, provider: ModelProvider):
        self.provider = provider
        self.system_instruction = (
            "You are a specialized Context Processor Tool. Your goal is to minimize tokens "
            "sent to a larger reasoning model. You must extract only the most relevant "
            "information from the provided content based on the user's query.\n"
            "Constraints:\n"
            "- Never return the full raw content.\n"
            "- Always return a structured JSON response.\n"
            "- Focus on relevant functions, error messages, or logic snippets."
        )

    def process(self, operation: str, query: str, content: str, constraints: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        operation: summarize | extract | rank | compress
        """
        prompt = f"""
Operation: {operation}
Query/Intent: {query}
Constraints: {json.dumps(constraints or {{}})}

Content to process:
---
{content}
---

Return your response in the following JSON format:
{{
  "summary": "short explanation",
  "key_points": ["point 1", "point 2"],
  "relevant_snippets": [
    {{
      "file": "filename if known",
      "code": "minimal relevant code block"
    }}
  ],
  "confidence": 0.9
}}
"""
        response_text = self.provider.call("small", prompt, system_instruction=self.system_instruction)
        
        # Simple JSON extraction from response
        try:
            # Look for JSON block if model wrapped it in markdown
            if "```json" in response_text:
                json_str = response_text.split("```json")[1].split("```")[0].strip()
            elif "{" in response_text:
                json_str = response_text[response_text.find("{"):response_text.rfind("}")+1]
            else:
                json_str = response_text
                
            return json.loads(json_str)
        except Exception as e:
            return {
                "summary": "Error parsing small model output",
                "error": str(e),
                "raw_output": response_text[:500],
                "confidence": 0.0
            }
