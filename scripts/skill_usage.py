"""Verify method-version and artifact-linked usage records, not their semantic truth."""
import hashlib
from pathlib import Path


def verify(p,n,records,input_hashes,base):
    if p.get('capability_policy_version')!=3 or not n['bindings']:return []
    if not isinstance(records,list):raise ValueError('finish 需要 --skill-use-file：逐个技能的实际方法使用记录')
    expected={b['candidate_id'] for b in n['bindings']}
    if any(not isinstance(r,dict) for r in records):raise ValueError('技能使用记录需要对象列表')
    if len(records)!=len(expected) or {r.get('candidate_id') for r in records}!=expected:
        raise ValueError('技能使用记录必须恰好覆盖本模块的绑定技能')
    checked=[]
    for record in records:
        c=next(c for c in p['capability_candidates'] if c['id']==record['candidate_id'])
        source=next(m for m in p['materials'] if m['id']==c['method_support']['material_id'])
        method=Path(source['path']);method=method if method.is_absolute() else Path(base)/method
        expected_hash=input_hashes.get(str(method.resolve()))
        if not expected_hash or record.get('method_sha256')!=expected_hash:raise ValueError('技能使用记录的方法版本与 start 快照不一致：'+c['name'])
        steps=record.get('applied_steps')
        if not isinstance(steps,list) or not steps or any(not isinstance(v,str) or not v.strip() for v in steps):
            raise ValueError('applied_steps 需要实际采用的方法及其作用')
        outputs=record.get('outputs')
        binding=next(b for b in n['bindings'] if b['candidate_id']==c['id'])
        if not isinstance(outputs,list) or not outputs or any(not isinstance(o,str) for o in outputs) or set(outputs)!=set(binding['contract']['outputs']):
            raise ValueError('技能使用记录需要覆盖该技能负责的输出')
        path=record.get('record_path')
        if not isinstance(path,str) or not path.strip():raise ValueError('record_path 需要实际调用、脚本运行或方法执行记录文件')
        path=Path(path);path=path if path.is_absolute() else Path(base)/path
        if not path.is_file() or not path.read_bytes().strip():raise ValueError('技能执行记录文件不存在或为空')
        if str(path.resolve()) in input_hashes:raise ValueError('技能原文或输入材料不能充当执行记录')
        checked.append(dict(record,candidate_id=c['id'],record_path=str(path.resolve()),record_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    return checked
