"""调一个 OpenAI 兼容的 chat 模型。评分器、模拟器共用这一处。"""
from __future__ import annotations

import json
import urllib.error
import urllib.request


def chat(base_url: str, model: str, api_key: str, prompt: str,
         timeout: float = 120.0) -> str:
    """给 OpenAI 兼容的 chat completions 发一条 prompt,返回回答文本。"""
    base = base_url.rstrip("/")
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"模型调用失败 HTTP {exc.code}:{exc.reason}") from exc
    return str(data["choices"][0]["message"]["content"])
