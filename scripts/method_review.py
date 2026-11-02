"""A short substantive review, separate from locating a Skill quotation.

The host supplies judgement; Python binds it to the plan and real sources.
No keyword classifier can establish professional suitability.
"""
import argparse, copy, hashlib, json, sys
from pathlib import Path
import sos
from plan_io import edit_lock

ROOT = Path(__file__).resolve().parents[1]

def basis(p):
    value = {k:copy.deepcopy(p.get(k)) for k in ('goal','mapping','constraints','assumptions','open_questions','materials','requirements','deliverables','content_outline','nodes','capability_needs','capability_candidates')}
    for n in value['nodes']:
        for b in n['bindings']:
            b.pop('readiness',None)
            b.get('contract',{}).pop('verification',None)
    for c in value['capability_candidates']:
        c.pop('setup',None); c.pop('installation_directory',None)
    return sos.digest(value)

def pending(p):
    if p.get('review_protocol_version') != 2:return False
    review=p.get('professional_review') or {}
    return review.get('basis_hash') != basis(p) or review.get('verdict') != 'pass'

def sources(p,base):
    result={}
    for m in p['materials']:
        path=Path(m['path']);path=path if path.is_absolute() else base/path
        if not path.is_file():raise ValueError('审阅来源不存在：'+str(path))
        result[str(path.resolve())]=hashlib.sha256(path.read_bytes()).hexdigest()
    return result

def check_current(p,base):
    if p.get('review_protocol_version')!=2:return
    if pending(p):raise ValueError('专业适配尚未通过实质审阅；运行 method_review.py open <plan.json>')
    if p['professional_review'].get('source_hashes')!=sources(p,base):
        raise ValueError('适配审阅后的输入或方法已变化；重新运行 method_review.py open')

def packet(p,base):
    candidates={c['id']:c for c in p['capability_candidates']}
    materials={m['id']:m for m in p['materials']}
    rows=[]
    for need in p['capability_needs']:
        if need.get('task_kind')=='basic':continue
        c=candidates.get(need['decision'].get('candidate_id'))
        rows.append(dict(need=need['id'],role=need.get('role'),question=need['standard'],
                         skill=c['name'] if c else None,
                         method_file=materials[c['method_support']['material_id']]['path'] if c else None,
                         verdict='unverified',method_quote='',reason='',input_basis='',limits=''))
    return dict(schema='sos-method-review-v1',basis_hash=basis(p),source_hashes=sources(p,base),
                goal=p['goal'],mapping=p.get('mapping'),materials=p['materials'],deliverables=p['deliverables'],
                assignments=[dict(node=n['id'],work=n['description'],outputs=n['outputs'],skills=[b['skill'] for b in n['bindings']]) for n in p['nodes']],
                review_guide=str(ROOT/'references/composed-methods.md'),
                instruction='逐项核读所选方法与输入画像，判断能否承担 question 中的工作及负责成果。核心项的 reason 要指出本任务需要的专业判断，以及原文提供的对应方法；通用的分析、比较、呈现、验证流程不足以证明领域判断已覆盖。缺少核心方法时标 fail 并实际寻找专业候选。用户是否熟悉术语不改变此标准。文件操作/格式验证不能证明具备业务判断方法；制作本身是目标时制作技能可以胜任。核查核心方法与制作职责是否均有实际分工；候选列表中出现技能不代表它已负责工作。仅记录本次适配、依据与判断边界，不开展分析或起草。无方法覆盖时标 fail；证据未读到标 unverified。',
                items=rows)

def accept(p,data,base):
    if data.get('schema')!='sos-method-review-v1' or data.get('basis_hash')!=basis(p):raise ValueError('适配审阅对应旧方案，重新 open')
    if data.get('source_hashes')!=sources(p,base):raise ValueError('适配审阅来源已变化，重新 open')
    expected=packet(p,base)['items'];rows=data.get('items')
    if not isinstance(rows,list) or len(rows)!=len(expected) or any(not isinstance(r,dict) for r in rows) or {r.get('need') for r in rows}!={r['need'] for r in expected}:raise ValueError('逐项保留全部能力需求')
    for e in expected:
        r=next(x for x in rows if x['need']==e['need'])
        if any(r.get(k)!=e[k] for k in ('role','question','skill','method_file')):raise ValueError('审阅对象已更改，重新 open')
        if r.get('verdict') not in ('pass','fail','unverified'):raise ValueError('verdict 使用 pass/fail/unverified')
        if not isinstance(r.get('reason'),str) or not r['reason'].strip():raise ValueError('填写实际适配判断及原因')
        if r['verdict']=='pass':
            if not e['method_file']:raise ValueError('没有方法来源的能力不能通过')
            path=Path(e['method_file']);path=path if path.is_absolute() else base/path
            quote=r.get('method_quote')
            if not isinstance(quote,str) or not quote.strip() or quote not in path.read_text(encoding='utf-8'):raise ValueError('method_quote 须为方法原文中的实际片段')
            if any(not isinstance(r.get(k),str) or not r[k].strip() for k in ('input_basis','limits')):raise ValueError('填写输入适配及本次判断边界；无实质限制也说明适用范围')
    result=copy.deepcopy(p)
    result['professional_review']=dict(basis_hash=basis(p),source_hashes=data['source_hashes'],
                                      verdict='pass' if all(r['verdict']=='pass' for r in rows) and rows else 'fail',items=rows)
    result['revision']+=1
    return result

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('action',choices=['open','accept']);ap.add_argument('plan');ap.add_argument('--review');a=ap.parse_args()
    plan=Path(a.plan).resolve();review=Path(a.review).resolve() if a.review else plan.parent/'.sos'/'method-review.json'
    if review==plan:raise ValueError('review 不能覆盖方案')
    with edit_lock(plan):
        p=sos.read(plan);sos.require_plan(p)
        if a.action=='open':
            if p.get('review_protocol_version')!=2:p['review_protocol_version']=2;p['revision']+=1;sos.save(plan,p)
            protected=[(Path(x['path']) if Path(x['path']).is_absolute() else plan.parent/x['path']).resolve() for x in p['materials']]
            if review in protected or review in (plan.parent/'run.json',plan.parent/'.sos-planning.json'):raise ValueError('review 不能覆盖来源或执行状态')
            sos.save(review,packet(p,plan.parent));result=dict(review=str(review),next='核读方法与输入画像，填写此表后运行 method_review.py accept '+str(plan))
        else:
            updated=accept(p,sos.read(review),plan.parent);sos.save(plan,updated)
            from plan_status import assess
            result=assess(updated)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':
    try:main()
    except (ValueError,KeyError,TypeError,OSError) as e:print(str(e),file=sys.stderr);sys.exit(2)
