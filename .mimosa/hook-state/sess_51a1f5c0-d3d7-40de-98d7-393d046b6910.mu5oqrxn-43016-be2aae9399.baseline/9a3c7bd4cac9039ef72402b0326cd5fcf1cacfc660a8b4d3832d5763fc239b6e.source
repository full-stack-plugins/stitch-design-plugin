#!/usr/bin/env python3
"""SessionStart hook: report Stitch proxy readiness for this plugin.

Advisory only — always exits 0. The stdio proxy requires Python 3.11+.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    lines: list[str] = []
    lines.append(f"python3: {sys.version.split()[0]}")

    if sys.version_info[:2] < (3, 11):
        lines.append("Stitch MCP proxy: 需要 Python 3.11+，当前解释器过低——MCP 服务器将无法启动")
    else:
        proxy = Path(__file__).resolve().parents[1] / "scripts" / "stitch_mcp_proxy.py"
        lines.append("Stitch MCP proxy: 就绪" if proxy.is_file() else "Stitch MCP proxy: 脚本缺失")

    lines.append("Stitch 凭据: 首次使用时按 Skill 指引完成 OAuth/登录")

    try:
        sys.stdin.read()
    except Exception:
        pass

    print("Stitch 插件环境：" + "；".join(lines))
    return 0


if __name__ == "__main__":
    try:
        json.load(sys.stdin)
    except Exception:
        pass
    sys.exit(main())
