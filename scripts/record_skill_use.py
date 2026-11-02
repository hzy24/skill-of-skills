#!/usr/bin/env python3
"""Link an actual execution log to the selected skill, source version and outputs."""
import argparse,hashlib,json,sys
from pathlib import Path


def record(p,node,base,log,steps,skill=None):
    n=next((n for n in p['nodes'] if n['id']==node),None)
    if n is None:raise ValueError('未知模块')
    bindings=[b for b in n['bindings'] if skill is None or b['skill']==skill]
    if len(bindings)!=1:raise ValueError('多技能模块请用 --skill 指定准确名称')
    b=bindings[0];c=next(c for c in p['capability_candidates'] if c['id']==b['candidate_id'])
    source=next(m for m in p['materials'] if m['id']==c['method_support']['material_id'])
    def locate(v):
        if not isinstance(v,str) or not v.strip():raise ValueError('需要实际执行日志路径')
        f=Path(v);return f if f.is_absolute() else Path(base)/f
    method=locate(source['path']);trace=locate(log)
    if not trace.is_file() or not trace.read_bytes().strip():raise ValueError('执行记录文件不存在或为空：'+str(trace.resolve())+'；相对路径以 plan.json 所在目录为基准。建议使用 execute.py open 生成的绝对路径。')
    if trace.resolve()==method.resolve():raise ValueError('技能原文不能作为执行记录')
    if not isinstance(steps,list) or not steps or any(not isinstance(s,str) or not s.strip() for s in steps):raise ValueError('applied 需要非空列表，说明实际采用的方法及作用')
    return dict(candidate_id=c['id'],method_sha256=hashlib.sha256(method.read_bytes()).hexdigest(),record_path=str(trace.resolve()),applied_steps=steps,outputs=b['contract']['outputs'])


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('plan');ap.add_argument('--node',required=True);ap.add_argument('--record',required=True)
    ap.add_argument('--applied',action='append',required=True);ap.add_argument('--skill');ap.add_argument('--out',required=True);a=ap.parse_args()
    plan=Path(a.plan).resolve();out=Path(a.out).resolve()
    if plan==out:raise ValueError('执行记录不能覆盖计划')
    p=json.loads(plan.read_text());item=record(p,a.node,plan.parent,a.record,a.applied,a.skill)
    if out==Path(item['record_path']):raise ValueError('记录清单不能覆盖执行日志')
    records=json.loads(out.read_text()) if out.exists() else []
    if not isinstance(records,list):raise ValueError('输出文件须为记录列表')
    if any(x.get('candidate_id')==item['candidate_id'] for x in records):raise ValueError('该技能已有记录；复核后使用新的记录文件')
    records.append(item);out.write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n');print(out)

if __name__=='__main__':
    try:main()
    except (ValueError,KeyError,TypeError,OSError) as e:print(str(e),file=sys.stderr);sys.exit(2)
