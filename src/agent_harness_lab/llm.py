"""调一个 OpenAI 兼容的 chat 模型。评分器、模拟器共用这一处。

调用会偶发失败(超时、限流、5xx)——这类是噪声,自动退避重试几次。
4xx(除 429 限流)是真错,不重试,直接抛。
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request


def chat(base_url: str, model: str, api_key: str, prompt: str,
         timeout: float = 180.0, retries: int = 2) -> str:
    """给 OpenAI 兼容的 chat completions 发一条 prompt,返回回答文本。

    撞上超时 / 限流(429)/ 5xx 会退避重试 retries 次;仍失败才抛。
    """
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
    last_err: object = "未知错误"
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return str(data["choices"][0]["message"]["content"])
        except urllib.error.HTTPError as exc:
            # 4xx(除 429 限流)是真错 —— 不重试,直接抛
            if 400 <= exc.code < 500 and exc.code != 429:
                raise RuntimeError(
                    f"模型调用失败 HTTP {exc.code}:{exc.reason}") from exc
            last_err = f"HTTP {exc.code}"
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            # 超时、连接问题 —— 偶发噪声,重试
            last_err = exc
        if attempt < retries:
            time.sleep(2 ** attempt)  # 指数退避:1s、2s……
    raise RuntimeError(f"模型调用失败(重试 {retries} 次仍失败):{last_err}")
