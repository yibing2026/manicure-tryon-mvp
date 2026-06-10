from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List


def load_env_file(path: Path = Path(".env.local")) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def get_llm_config(prefix: str = "LLM") -> Dict[str, str]:
    load_env_file()
    api_key = (
        os.getenv(f"{prefix}_API_KEY")
        or os.getenv("LLM_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or os.getenv("ARK_API_KEY")
        or os.getenv("DOUBAO_API_KEY")
        or ""
    )
    api_base = (
        os.getenv(f"{prefix}_API_BASE")
        or os.getenv("LLM_API_BASE")
        or "https://api.openai.com/v1"
    ).rstrip("/")
    model = (
        os.getenv(f"{prefix}_MODEL")
        or os.getenv("LLM_MODEL")
        or os.getenv("OPENAI_TEXT_MODEL")
        or "gpt-4o-mini"
    )
    return {
        "api_key": api_key,
        "api_base": api_base,
        "model": model,
    }


def image_file_to_data_url(path: Path) -> str:
    mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
    payload = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{payload}"


def parse_json_object(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def call_chat_json(
    *,
    messages: List[Dict[str, Any]],
    config: Dict[str, str],
    temperature: float = 0.2,
    timeout: int = 90,
) -> Dict[str, Any]:
    if not config.get("api_key"):
        raise RuntimeError("LLM API key is not configured.")

    request_body = {
        "model": config["model"],
        "messages": messages,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        f"{config['api_base']}/chat/completions",
        data=json.dumps(request_body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LLM API request failed ({error.code}): {detail}") from error

    content = payload["choices"][0]["message"]["content"]
    return {
        "model": payload.get("model") or config["model"],
        "raw_content": content,
        "json": parse_json_object(content),
        "usage": payload.get("usage"),
    }
