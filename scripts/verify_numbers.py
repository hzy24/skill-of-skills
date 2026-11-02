#!/usr/bin/env python3
"""Recompute selected assertions from final files. No code execution or formula evaluation."""
import argparse, hashlib, json, re, sys, zipfile, posixpath
from decimal import Decimal, InvalidOperation
from pptx_parts import slide_parts
from pathlib import Path
from xml.etree import ElementTree as ET

S = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
A = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'

def extract(ref, base, evidence):
    path = (base / ref['file']).resolve()
    data = path.read_bytes()
    evidence[str(path)] = hashlib.sha256(data).hexdigest()
    if path.suffix.lower() == '.xlsx':
        with zipfile.ZipFile(path) as z:
            book = ET.fromstring(z.read('xl/workbook.xml'))
            sheet = next(x for x in book.findall('.//' + S + 'sheet') if x.get('name') == ref['sheet'])
            rels = ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
            target = next(x.get('Target') for x in rels if x.get('Id') == sheet.get(R+'id'))
            target = target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/' + target)
            root = ET.fromstring(z.read(target))
            cell = next(x for x in root.iter(S+'c') if x.get('r') == ref['cell'])
            value = cell.find(S+'v')
            if cell.get('t') == 's':
                strings = ET.fromstring(z.read('xl/sharedStrings.xml'))
                text = ''.join(strings[int(value.text)].itertext())
            elif cell.get('t') == 'inlineStr': text = ''.join(x.text or '' for x in cell.iter(S+'t'))
            else:
                if value is None or value.text is None: raise ValueError('单元格缺少缓存数值，请先用表格引擎重算')
                text = value.text
    elif path.suffix.lower() == '.pptx':
        with zipfile.ZipFile(path) as z:
            parts = slide_parts(z)
            index = ref['slide']
            if type(index) is not int or not 1 <= index <= len(parts): raise ValueError('页码超出范围')
            root = ET.fromstring(z.read(parts[index-1]))
            text = '\n'.join(''.join(x.text or '' for x in p.iter(A+'t')) for p in root.iter(A+'p'))
    else: text = data.decode('utf-8')
    if 'pattern' in ref:
        pattern = re.compile(ref['pattern'])
        if 'value' not in pattern.groupindex: raise ValueError('定位表达式需要 value 命名组')
        matches = list(pattern.finditer(text))
        if len(matches) != 1: raise ValueError('定位表达式必须唯一命中，实际 %d 处' % len(matches))
        text = matches[0].group('value')
    number = Decimal(text.strip().replace(',', '').replace('−', '-'))
    if not number.is_finite(): raise ValueError('数值必须有限')
    return number


def verify(spec, base):
    if not isinstance(spec, dict): raise ValueError('spec 需要对象')
    checks = spec.get('checks')
    if not isinstance(checks, list) or not checks: raise ValueError('checks 不能为空')
    results, hashes = [], {}
    if any(not isinstance(c,dict) or not isinstance(c.get('id'),str) or not c['id'] for c in checks): raise ValueError('检查需要非空 id')
    ids = [c['id'] for c in checks]
    if len(set(ids)) != len(ids): raise ValueError('检查 id 重复')
    for c in checks:
        result = {'id': c['id'], 'passed': False}
        try:
            refs = c['inputs']
            if not refs: raise ValueError('inputs 不能为空')
            # Metadata is asserted by the host after reading the actual labels.
            if not c.get('context') or any(r.get('context') != c['context'] for r in refs):
                raise ValueError('对象、期间、单位或基数口径不一致')
            values = [extract(r, base, hashes) for r in refs]
            op = c['op']
            if op == 'sum': actual = sum(values, Decimal(0))
            elif op == 'ratio' and len(values) == 2: actual = values[0] / values[1]
            elif op == 'difference' and len(values) == 2: actual = values[0] - values[1]
            else: raise ValueError('不支持的运算或输入数量')
            actual *= Decimal(str(c.get('scale', 1)))
            expected = c['expected']
            if isinstance(expected, dict):
                if expected.get('context') != c['context']: raise ValueError('目标口径不一致')
                expected = extract(expected, base, hashes)
            else: expected = Decimal(str(expected))
            tolerance = Decimal(str(c.get('tolerance', '0.000001')))
            if not expected.is_finite() or not tolerance.is_finite() or tolerance < 0: raise ValueError('目标值及容差无效')
            result.update(passed=abs(actual-expected)<=tolerance, actual=str(actual), expected=str(expected), inputs=[str(v) for v in values])
        except (KeyError, ValueError, TypeError, AttributeError, IndexError, re.error, OSError, StopIteration, InvalidOperation, ArithmeticError, zipfile.BadZipFile, ET.ParseError) as e:
            result['status'] = 'input_error'
            result['error'] = str(e) or type(e).__name__
        results.append(result)
    return {'passed': all(x['passed'] for x in results), 'checks': results, 'file_hashes': hashes,
            'limitations': '仅验证声明范围内的数字关系；定位、对象与业务口径须审阅。xlsx使用已有缓存，未执行重算；不证明因果、视觉或完整性。'}

if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('spec'); ap.add_argument('--out', required=True)
    args = ap.parse_args()
    try:
        p = Path(args.spec).resolve(); report = verify(json.loads(p.read_text()), p.parent)
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(json.dumps(report, ensure_ascii=False, indent=2)); sys.exit(2 if any(x.get('status')=='input_error' for x in report['checks']) else (0 if report['passed'] else 1))
    except (ValueError, OSError, KeyError, TypeError) as e:
        Path(args.out).write_text(json.dumps({'passed':False,'status':'input_error','error':str(e)},ensure_ascii=False))
        print(str(e), file=sys.stderr); sys.exit(2)
