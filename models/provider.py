import os
import time
from google import genai
from google.genai import types
from dotenv import load_dotenv
from dataclasses import dataclass
from typing import Dict, Any, List, Optional

# Load environment variables from .env in the project root
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(project_root, ".env"))

@dataclass
class TokenMetrics:
    input_tokens: int = 0
    output_tokens: int = 0
    
    def add(self, other: 'TokenMetrics'):
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens

class ModelProvider:
    def __init__(self):
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY not found in environment")
        
        self.client = genai.Client(api_key=api_key)
        
        # Using confirmed -latest variants from client.models.list()
        self.large_model_name = "gemini-flash-latest"
        self.small_model_name = "gemini-flash-lite-latest"
        
        self.metrics = {
            "large": TokenMetrics(),
            "small": TokenMetrics()
        }

    def call(self, model_type: str, prompt: str, system_instruction: Optional[str] = None) -> str:
        model_name = self.large_model_name if model_type == "large" else self.small_model_name
        
        config = None
        if system_instruction:
            config = types.GenerateContentConfig(
                system_instruction=system_instruction
            )
            
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # 15s delay ensures max 4 RPM (Free tier is often 5 RPM)
                time.sleep(15)
                
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=config
                )
                
                # Track metrics
                if response.usage_metadata:
                    self.metrics[model_type].input_tokens += response.usage_metadata.prompt_token_count or 0
                    self.metrics[model_type].output_tokens += response.usage_metadata.candidates_token_count or 0
                    
                return response.text
            except Exception as e:
                error_msg = str(e)
                if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                    wait_time = 30 * (attempt + 1)
                    print(f"\n[QUOTA ERROR] {error_msg}")
                    print(f"Retrying in {wait_time}s... (Attempt {attempt+1}/{max_retries})\n")
                    time.sleep(wait_time)
                    continue
                print(f"\n[UNEXPECTED ERROR] {error_msg}\n")
                raise e
        
        return f"Error: Maximum retries reached. Last error: {error_msg}"

    def get_metrics(self) -> Dict[str, Dict[str, int]]:
        return {
            "large": {
                "input": self.metrics["large"].input_tokens,
                "output": self.metrics["large"].output_tokens,
                "total": self.metrics["large"].input_tokens + self.metrics["large"].output_tokens
            },
            "small": {
                "input": self.metrics["small"].input_tokens,
                "output": self.metrics["small"].output_tokens,
                "total": self.metrics["small"].input_tokens + self.metrics["small"].output_tokens
            }
        }

    def reset_metrics(self):
        self.metrics = {
            "large": TokenMetrics(),
            "small": TokenMetrics()
        }
