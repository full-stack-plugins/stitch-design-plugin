#!/usr/bin/env python3
"""离线检查 Stitch 设计包的可追踪结构；不能证明语义或远程效果。"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def validate(root: Path) -> list[str]:
    """返回结构错误；输入为完整包目录，不执行文档或远程调用。"""
    root = root.resolve()
    errors: list[str] = []
    try:
        data = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        return [f'manifest.json: {exc}']
    if not isinstance(data, dict) or data.get('version') != 'stitch-design-spec/v1':
        return ['manifest version must be stitch-design-spec/v1']

    def file_text(name: object) -> str:
        if not isinstance(name, str) or not name or Path(name).is_absolute():
            errors.append(f'invalid relative file: {name!r}')
            return ''
        path = (root / name).resolve()
        if not path.is_relative_to(root):
            errors.append(f'file escapes package: {name}')
            return ''
        try:
            text = path.read_text(encoding='utf-8')
        except (OSError, UnicodeError):
            errors.append(f'missing/unreadable file: {name}')
            return ''
        if not text.strip() or re.search(r'\{\{[^{}]+\}\}', text):
            errors.append(f'empty or unresolved template: {name}')
        return text

    def index(key: str) -> dict[str, dict]:
        rows = data.get(key)
        if not isinstance(rows, list) or not rows:
            errors.append(f'{key}: nonempty list required')
            return {}
        result = {}
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get('id'), str) or not row['id'].strip():
                errors.append(f'{key}: invalid row/id')
                continue
            if row['id'] in result:
                errors.append(f'{key}: duplicate {row["id"]}')
            result[row['id']] = row
        return result

    def values(row: dict, key: str, label: str, allow_empty: bool = False) -> list[str]:
        value = row.get(key)
        if not isinstance(value, list) or not all(isinstance(x, str) and x.strip() for x in value):
            errors.append(f'{label}: invalid {key}')
            return []
        if not allow_empty and not value:
            errors.append(f'{label}: empty {key}')
        if len(set(value)) != len(value):
            errors.append(f'{label}: duplicate {key}')
        return value

    for name in ('README.md', 'DESIGN-SPEC.md', 'COVERAGE.md', 'MASTER-PLAN.md'):
        file_text(name)
    sources, pages, prompts, tasks = (index(key) for key in ('sources', 'pages', 'prompts', 'tasks'))
    # 先验证容器和标量类型，错误输入应返回诊断而不是崩溃。
    for rows, fields in ((pages, ('file',)), (prompts, ('file', 'page_id', 'mode'))):
        for identifier, row in rows.items():
            for key in fields:
                if not isinstance(row.get(key), str) or not row[key].strip():
                    errors.append(f'{identifier}: nonempty string required for {key}')
    for tid, task in tasks.items():
        for key in ('page_ids', 'prompt_ids', 'depends_on'):
            values(task, key, tid, allow_empty=(key == 'depends_on'))
    if errors:
        return errors
    for sid, source in sources.items():
        if not source.get('ref') or source.get('status') not in ('confirmed', 'proposed', 'pending', 'example'):
            errors.append(f'{sid}: source ref/status required')
    required: set[tuple[str, str]] = set()
    covered: set[tuple[str, str]] = set()
    for pid, page in pages.items():
        file_text(page.get('file'))
        for sid in values(page, 'source_ids', pid):
            if sid not in sources:
                errors.append(f'{pid}: unknown source {sid}')
        required.update((pid, state) for state in values(page, 'states', pid))
    used_files = set()
    for qid, prompt in prompts.items():
        body = file_text(prompt.get('file'))
        if prompt.get('file') in used_files:
            errors.append(f'{qid}: prompt file reused')
        used_files.add(prompt.get('file'))
        sections = re.findall(r'^\[(Context|Layout|Components)\]\s*$', body, re.M)
        if sections != ['Context', 'Layout', 'Components']:
            errors.append(f'{qid}: three sections out of order/missing/duplicated')
        elif not re.search(r'^\d+\.\s+\S', body.split('[Layout]', 1)[1].split('[Components]', 1)[0], re.M):
            errors.append(f'{qid}: numbered layout required')
        pid = prompt.get('page_id')
        if pid not in pages:
            errors.append(f'{qid}: unknown page {pid}')
        for state in values(prompt, 'states', qid):
            pair = (pid, state)
            if pair not in required:
                errors.append(f'{qid}: unknown page-state {pair}')
            covered.add(pair)
        mode = prompt.get('mode')
        if mode not in ('inline', 'applied-system', 'targeted-edit'):
            errors.append(f'{qid}: invalid mode')
        if mode == 'applied-system':
            system = prompt.get('system')
            if not isinstance(system, dict) or not all(system.get(k) for k in ('project_id', 'id', 'evidence')):
                errors.append(f'{qid}: applied system needs project/id/evidence')
            # 保守扫描常见 token；自然语言视觉约束仍需人工审阅。
            if re.search(r'#[0-9a-f]{3,8}\b|font-family|border-radius|primary (?:color|accent)|dark theme|主色|圆角|字体|色板', body, re.I):
                errors.append(f'{qid}: visual tokens in applied-system prompt')
        if mode == 'targeted-edit' and not (prompt.get('target') and prompt.get('delta')):
            errors.append(f'{qid}: targeted edit needs target/delta')
    deferrals = data.get('deferrals', [])
    if not isinstance(deferrals, list):
        errors.append('deferrals must be a list')
        deferrals = []
    for item in deferrals:
        if not isinstance(item, dict):
            errors.append('invalid deferral')
            continue
        if not all(isinstance(item.get(key), str) for key in ('page_id', 'state', 'reason')):
            errors.append('deferral page_id/state/reason must be strings')
            continue
        pair = (item.get('page_id'), item.get('state'))
        if pair not in required or not item.get('reason'):
            errors.append(f'invalid deferral: {pair}')
        covered.add(pair)
    for pair in sorted(required - covered):
        errors.append(f'uncovered page-state: {pair}')
    task_pages, task_prompts, dependencies = set(), set(), {}
    for tid, task in tasks.items():
        for key, known, used in (('page_ids', pages, task_pages), ('prompt_ids', prompts, task_prompts)):
            for identifier in values(task, key, tid):
                if identifier not in known:
                    errors.append(f'{tid}: unknown {key} {identifier}')
                used.add(identifier)
        deps = values(task, 'depends_on', tid, allow_empty=True)
        dependencies[tid] = deps
        if any(dep not in tasks for dep in deps):
            errors.append(f'{tid}: unknown dependency')
        if not isinstance(task.get('acceptance'), str) or not task['acceptance'].strip():
            errors.append(f'{tid}: acceptance required')
        for qid in task.get('prompt_ids', []) if isinstance(task.get('prompt_ids'), list) else []:
            if qid in prompts and prompts[qid].get('page_id') not in task.get('page_ids', []):
                errors.append(f'{tid}: prompt page absent from task scope')
    if set(pages) - task_pages or set(prompts) - task_prompts:
        errors.append('pages/prompts without tasks')
    pending = dict(dependencies)
    while pending:
        ready = [tid for tid, deps in pending.items() if not any(dep in pending for dep in deps)]
        if not ready:
            errors.append('task dependency cycle')
            break
        for tid in ready:
            del pending[tid]
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    args = parser.parse_args()
    errors = validate(args.package)
    for error in errors:
        print(f'ERROR: {error}')
    print(f'Structural validation: {len(errors)} errors; semantic review and remote generation NOT_VERIFIED')
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
