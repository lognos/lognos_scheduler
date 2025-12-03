from pathlib import Path
from typing import Any
from jinja2 import Environment, FileSystemLoader, select_autoescape

# Define the prompts directory relative to this file (since this file is IN the prompts dir)
PROMPTS_DIR = Path(__file__).parent

# Initialize Jinja2 Environment
env = Environment(
    loader=FileSystemLoader(PROMPTS_DIR),
    autoescape=select_autoescape(["xml", "html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


class PromptLoader:
    """Utility to load and render Jinja2 prompt templates."""

    @staticmethod
    def get_prompt(template_name: str, **kwargs: Any) -> str:
        """
        Load and render a prompt template.

        Args:
            template_name: Filename in backend/prompts/ (e.g., "risk_system.xml.j2")
            **kwargs: Variables to inject into the template

        Returns:
            Rendered prompt string
        """
        template = env.get_template(template_name)
        return template.render(**kwargs)
