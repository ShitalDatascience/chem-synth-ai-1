from typing import Dict, Any

# If you're using OpenAI / local LLM later, plug here
# For now this is interface-ready design

class ScientificLLM:

    @staticmethod
    def generate(prompt: str) -> Dict[str, Any]:
        """
        Replace with:
        - OpenAI GPT-4o
        - Llama 3
        - local vLLM
        """

        # TEMP MOCK (replace later with real model call)
        return {
            "summary": "Scientific reasoning output placeholder",
            "raw_prompt": prompt
        }
