#!/usr/bin/env python3
"""UserPromptSubmit hook: point Stitch-shaped requests at the plugin commands.

Advisory only — always exits 0; silent unless the prompt looks Stitch-related.
"""
from __future__ import annotations

import json
import re
import sys

INTENT_RE = re.compile(
    r"stitch|设计稿|生成页面|生成界面|\bui\s*设计|设计系统|组件库|design[-\s]?system|设计转代码",
    re.IGNORECASE,
)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (OSError, ValueError):
        # Unreadable or non-JSON hook payload: this hook is advisory only.
        payload = {}

    prompt = ""
    if isinstance(payload, dict):
        prompt = str(payload.get("prompt") or "")

    if prompt.strip().startswith("/"):
        return 0

    if INTENT_RE.search(prompt):
        print(
            "提示：该请求疑似 Stitch 相关。用 /stitch 总入口按能力路由；"
            "常用细分命令：/stitch-ui-execute（生成/编辑界面）、"
            "/stitch-design-spec（页面规格与提示词）、/stitch-ui-loop（接力迭代）、"
            "/stitch-design-harness（高保真交付）、/stitch-code-to-design（代码反向同步）、"
            "/stitch-upload（上传资产）；其余能力见 /stitch。"
            "MCP 工具经 stitch 代理提供。"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
