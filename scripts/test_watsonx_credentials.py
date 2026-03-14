#!/usr/bin/env python3
"""Test watsonx credentials and connectivity.

Usage (from repo root):
    python scripts/test_watsonx_credentials.py

Loads settings from backend/.env and attempts authentication, model
listing, and a short text generation call.
"""

from __future__ import annotations

import os
import sys

# Ensure the backend package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
os.chdir(os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.core.config import settings

BOLD = "\033[1m"
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
RESET = "\033[0m"

def ok(msg: str) -> None:
    print(f"  {GREEN}✓{RESET} {msg}")

def fail(msg: str) -> None:
    print(f"  {RED}✗{RESET} {msg}")

def warn(msg: str) -> None:
    print(f"  {YELLOW}!{RESET} {msg}")


def main() -> None:
    print(f"\n{BOLD}watsonx credential check{RESET}\n")

    # 1. Check env vars
    print(f"{BOLD}1. Environment variables{RESET}")
    api_key = settings.watsonx_api_key
    project_id = settings.watsonx_project_id
    url = settings.watsonx_url

    if not api_key:
        fail("WATSONX_API_KEY is empty — set it in backend/.env")
        return
    ok(f"WATSONX_API_KEY      = {api_key[:8]}...{api_key[-4:]}")
    ok(f"WATSONX_PROJECT_ID   = {project_id or '(empty)'}")
    ok(f"WATSONX_URL          = {url}")

    if not project_id:
        warn("WATSONX_PROJECT_ID is empty — most API calls require it")

    # 2. Import SDK
    print(f"\n{BOLD}2. IBM watsonx SDK{RESET}")
    try:
        import ibm_watsonx_ai
        ok(f"ibm_watsonx_ai {ibm_watsonx_ai.__version__}")
    except ImportError:
        fail("ibm-watsonx-ai is not installed — run: pip install ibm-watsonx-ai")
        return

    # 3. Authenticate
    print(f"\n{BOLD}3. Authentication{RESET}")
    try:
        from ibm_watsonx_ai import Credentials
        creds = Credentials(url=url, api_key=api_key)
        ok("Credentials object created")
    except Exception as exc:
        fail(f"Credentials creation failed: {exc}")
        return

    # 4. Connect to project
    print(f"\n{BOLD}4. Project connection{RESET}")
    try:
        from ibm_watsonx_ai import APIClient
        client = APIClient(credentials=creds, project_id=project_id)
        ok(f"Connected to project {project_id}")
    except Exception as exc:
        fail(f"Project connection failed: {exc}")
        print(f"\n    This usually means the API key is invalid or the project ID")
        print(f"    doesn't exist. Double-check WATSONX_API_KEY in backend/.env.")
        return

    # 5. List available foundation models
    print(f"\n{BOLD}5. Foundation models{RESET}")
    try:
        from ibm_watsonx_ai.foundation_models.utils.enums import ModelTypes
        models = [m.value for m in ModelTypes]
        ok(f"{len(models)} model types available in SDK")
    except Exception as exc:
        warn(f"Could not enumerate models: {exc}")

    # 6. Test generation
    model_id = "meta-llama/llama-3-3-70b-instruct"
    print(f"\n{BOLD}6. Test generation ({model_id}){RESET}")
    try:
        from ibm_watsonx_ai.foundation_models import ModelInference
        model = ModelInference(
            model_id=model_id,
            credentials=creds,
            project_id=project_id,
            params={
                "decoding_method": "greedy",
                "max_new_tokens": 30,
                "temperature": 0.1,
            },
        )
        response = model.generate_text(prompt="Say hello in one sentence.")
        ok(f"Response: {response.strip()[:120]}")
    except Exception as exc:
        fail(f"Generation failed: {exc}")
        return

    print(f"\n{GREEN}{BOLD}All checks passed — watsonx is ready to use.{RESET}\n")


if __name__ == "__main__":
    main()
