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
    except Exception:
        payload = {}

    prompt = ""
    if isinstance(payload, dict):
        prompt = str(payload.get("prompt") or "")

    if prompt.strip().startswith("/"):
        return 0

    if INTENT_RE.search(prompt):
        print(
            "提示：该请求疑似 Stitch 相关。可用 /stitch 总入口或细分命令 "
            "(/stitch-ui-designer /stitch-design-md /stitch-extract-static-html "
            "/stitch-code-to-design /stitch-manage-design-system /stitch-loop "
            "/stitch-local-setup /stitch-upload)；MCP 工具经 stitch 代理提供。"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
