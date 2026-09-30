"""Environment variable loading and project configuration."""

import os
import uuid

from dotenv import load_dotenv

load_dotenv()

ROSETTA_STONE_REPO = "https://github.com/Arize-ai/project-rosetta-stone.git"
ARIZE_SKILLS_REPO = "https://github.com/Arize-ai/arize-skills.git"

SUPPORTED_APPS = {
    "langchain-py": {
        "source_path": "no-observability/langchain-py/backend",
        "ground_truth_path": "ax/langchain-py/backend",
        "framework": "langchain",
    },
}


def get_anthropic_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise ValueError("ANTHROPIC_API_KEY is required")
    return key


def get_arize_api_key() -> str:
    key = os.environ.get("ARIZE_API_KEY", "")
    if not key:
        raise ValueError("ARIZE_API_KEY is required")
    return key


def get_arize_space_id() -> str:
    space_id = os.environ.get("ARIZE_SPACE_ID", "")
    if not space_id:
        raise ValueError("ARIZE_SPACE_ID is required")
    return space_id


def generate_project_name(app_name: str) -> str:
    short_id = uuid.uuid4().hex[:8]
    return f"skill-sandbox-{app_name}-{short_id}"
