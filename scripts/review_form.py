"""Separate host judgments from program-owned review evidence and versioning."""
import copy
import json
from pathlib import Path

import sos

FIELDS = ('verdict', 'reason', 'input_basis', 'limits')


class ReviewInputError(ValueError):
    def __init__(self, errors, status='review_invalid', **recovery):
        self.result = dict(status=status, diagnostics=errors, **recovery)
        super().__init__('\n'.join(e['path'] + ': ' + e['message'] for e in errors))


def location(context, base):
    # The generated path carries the version. The host never copies a hash.
    identity = dict(task=str(base.resolve()), basis=context['basis_hash'], sources=context['source_hashes'])
    return base / '.sos' / 'reviews' / sos.digest(identity) / 'decisions.json'


def prepare(p, base, previous=None):
    from method_review import packet, reuse_items
    context = reuse_items(packet(p, base), previous)
    path = location(context, base)
    context_path = path.with_name('context.json')
    # Always regenerate evidence, even when a previous context file was damaged.
    sos.save(context_path, context)
    if not path.exists():
        sos.save(path, dict(items=[dict(need=r['need'], verdict=r['verdict'], reason=r['reason'])
                                  for r in context['items']]))
    return dict(review_file=str(path), context_file=str(context_path), review=context)


def judgments(data, expected):
    """Validate all input errors together; never use host-supplied evidence."""
    errors = []
    def error(path, message): errors.append(dict(path=path, message=message))
    if not isinstance(data, dict) or set(data) != {'items'} or not isinstance(data.get('items'), list):
        raise ReviewInputError([dict(path='review', message='使用 {"items": [...]}，每项填写 need、verdict、reason。')])
    by_need = {r['need']: r for r in expected}
    seen = set()
    result = []
    for i, row in enumerate(data['items']):
        at = 'items[' + str(i) + ']'
        if not isinstance(row, dict):
            error(at, '需要判断对象'); continue
        extra = set(row) - {'need', *FIELDS}
        for key in sorted(extra):
            error(at + '.' + key, '移除此字段；阶段、方法原文和版本由程序维护。')
        need = row.get('need')
        if not isinstance(need, str) or need not in by_need:
            error(at + '.need', '使用当前阶段编号：' + ', '.join(by_need)); continue
        if need in seen: error(at + '.need', '阶段重复：' + need)
        seen.add(need)
        if row.get('verdict') not in ('pass', 'fail', 'unverified'):
            error(at + '.verdict', '使用 pass / fail / unverified')
        if not isinstance(row.get('reason'), str) or not row['reason'].strip():
            error(at + '.reason', '说明该阶段的方法适配、输入前提与结论范围；发现问题时说明具体原因。')
        for key in ('input_basis', 'limits'):
            if key in row and not isinstance(row[key], str): error(at + '.' + key, '可省略；填写时使用文本。')
        merged = copy.deepcopy(by_need[need])
        # Clear cached decisions before applying the host's current judgment.
        merged.update({key: row.get(key, '') for key in FIELDS})
        result.append(merged)
    for need in by_need.keys() - seen: error('items', '缺少阶段判断：' + need)
    if errors: raise ReviewInputError(errors)
    return sorted(result, key=lambda r: list(by_need).index(r['need']))


def differences(old, current):
    changes = []
    for key in ('basis_hash', 'source_hashes'):
        if old.get(key) != current[key]: changes.append(key)
    rows = old.get('items')
    before = {r['need']: r for r in rows if isinstance(r, dict) and isinstance(r.get('need'), str)} if isinstance(rows, list) else {}
    for row in current['items']:
        prior = before.get(row['need'], {})
        for key in ('question', 'method_application', 'skill', 'outputs', 'upstream', 'method_boundary', 'subject_hash'):
            if prior.get(key) != row.get(key): changes.append(row['need'] + '.' + key)
    return changes


def accept_file(p, path, base):
    from method_review import packet, accept
    expected = packet(p, base)
    current = location(expected, base)
    path = Path(path).resolve()
    if path != current.resolve():
        try: old = sos.read(path.with_name('context.json')) if path.is_relative_to(base.resolve()/'.sos'/'reviews') else {}
        except (OSError, ValueError): old = {}
        if not isinstance(old, dict): old = {}
        recovery = prepare(p, base)
        raise ReviewInputError([dict(path='review_file', message='判断文件对应旧方案或其他任务，使用当前返回的文件。')],
                               status='review_stale', changed_fields=differences(old, expected),
                               **{k: recovery[k] for k in ('review_file', 'context_file')})
    # Read-only context is for the host to inspect, never an authority for accept.
    sos.save(current.with_name('context.json'), expected)
    try: data = sos.read(path)
    except json.JSONDecodeError as e:
        lines = path.read_text(encoding='utf-8').splitlines()
        raise ReviewInputError([dict(path='line ' + str(e.lineno), message=e.msg)], status='review_json_invalid',
                               line=e.lineno, column=e.colno, excerpt=lines[e.lineno-1][:240], review_file=str(path)) from e
    except FileNotFoundError as e:
        prepare(p, base)
        raise ReviewInputError([dict(path='review_file', message='判断文件不存在，已生成当前阶段的填写模板。')], review_file=str(current)) from e
    expected['items'] = judgments(data, expected['items'])
    return accept(p, expected, base)
