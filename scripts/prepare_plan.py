#!/usr/bin/env python3
"""Expand mechanical plan fields; keep professional decisions supplied by the host."""
import argparse,copy,hashlib,json,shlex,sys,time
from pathlib import Path
import sos
from plan_io import edit_lock
from planning_budget import session,session_path,status
from plan_status import assess

def prepare(draft, base_dir=None):
    if isinstance(draft,dict) and draft.get('draft_version')==2:
        from business_draft import expand
        draft=expand(draft,base_dir)
    malformed=sos.shape_errors(draft)
    if malformed:raise ValueError('；'.join(malformed))
    p=copy.deepcopy(draft)
    p.setdefault('capability_policy','skills_first')
    p['capability_policy_version']=3
    for k in ('capability_contract_version','quality_contract_version','selection_contract_version'):p.setdefault(k,1)
    p.setdefault('revision',1);p.setdefault('mode','execute_after_confirmation')
    p.setdefault('capability_candidates',[])
    candidates={c.get('id'):c for c in p['capability_candidates']}
    # Derive only mechanical links from explicit artifact ownership and requirements.
    producers={}
    for node in p.get('nodes',[]):
        for output in node.get('outputs',[]):
            producers.setdefault(output,[]).append(node['id'])
    for n in p.get('nodes',[]):
        if 'depends_on' not in n:
            deps=[]
            for item in n.get('inputs',[]):
                owners=[owner for owner in producers.get(item,[]) if owner!=n['id']]
                if len(owners)>1:
                    raise ValueError(n['id']+' 输入 '+item+' 有多个产出节点，请显式填写 depends_on')
                for owner in owners:
                    if owner not in deps:deps.append(owner)
            n['depends_on']=deps
        if 'capability_need_ids' not in n:
            n['capability_need_ids']=[need['id'] for need in p.get('capability_needs',[])
                if set(need.get('requirement_ids',[])) & set(n.get('requirements',[]))]
        # A method reference is an execution input, including for reference-only adoption.
        for need in p.get('capability_needs',[]):
            if need['id'] not in n.get('capability_need_ids',[]):continue
            candidate=candidates.get(need.get('decision',{}).get('candidate_id'),{})
            source=candidate.get('method_support',{}).get('material_id')
            if source and source not in n['inputs']:n['inputs'].append(source)
        for k in ('depends_on','bindings'):n.setdefault(k,[])
        used={c.get('id') for c in n.get('checks',[]) if c.get('id')}
        for i,c in enumerate(n.get('checks',[]),1):
            if c.get('kind')=='review' and not c.get('id'):
                cid=n['id']+'-review-'+str(i)
                while cid in used:cid+='x'
                c['id']=cid;used.add(cid)
        if 'done_when' not in n:
            n['done_when']=[c['criteria'] for c in n.get('checks',[]) if c.get('criteria')]
        for b in n['bindings']:
            b.setdefault('readiness','unknown')
            contract=b.get('contract',{})
            inherit=contract.pop('inherit',None)
            if inherit is not None:
                if inherit!='node' or len(n['bindings'])!=1 or contract.get('mode','full')!='full':
                    raise ValueError(n['id']+' contract.inherit=node 仅适用于单一完整技能负责整个模块；多技能或分支须显式分配输入、输出和检查')
                candidate=candidates.get(b.get('candidate_id'))
                if not candidate:raise ValueError(n['id']+' contract.inherit 引用了未知候选')
                contract.setdefault('inputs',copy.deepcopy(n['inputs']))
                contract.setdefault('outputs',copy.deepcopy(n['outputs']))
                contract.setdefault('source',candidate.get('source',''))
                contract.setdefault('source_evidence','；'.join(
                    e.get('locator','')+'：'+e.get('finding','') for e in candidate.get('evidence',[])))
                if 'required_checks' not in contract and 'check_ids' not in contract:
                    contract['required_checks']=copy.deepcopy(n.get('checks',[]))
            # Explicit references only: no guessing which checks a skill owns.
            refs=contract.pop('check_ids',None)
            if refs is not None:
                if 'required_checks' in contract:raise ValueError('check_ids 与 required_checks 只能填写一个')
                if not isinstance(refs,list) or not refs or any(not isinstance(x,str) for x in refs) or len(set(refs))!=len(refs):raise ValueError('check_ids 需要唯一非空列表')
                byid={c.get('id'):c for c in n.get('checks',[]) if c.get('id')}
                if any(x not in byid for x in refs):raise ValueError('check_ids 引用了未知检查')
                contract['required_checks']=[copy.deepcopy(byid[x]) for x in refs]
            if contract:
                contract.setdefault('mode','full');contract.setdefault('prerequisites',[]);contract.setdefault('verification','')
                b['contract']=contract
    for key in ('capability_contract_version','quality_contract_version','selection_contract_version'):
        if type(p.get(key)) is not int or p[key]!=1:raise ValueError(key+' 需要为 1')
    warnings=sos.require_plan(p)
    depth_errors=sos.validate_depth(p)
    if depth_errors:raise ValueError('；'.join(depth_errors))
    return p,warnings

def repair_scope(d):
    """Only source-reference corrections are allowed in the initial repair."""
    d=copy.deepcopy(d)
    for item in d.get('skills',[])+d.get('work',[]):
        for key in ('method_sections','method_excerpt'):item.pop(key,None)
    return d

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('draft',nargs='?');ap.add_argument('--out',required=True);ap.add_argument('--starter',action='store_true',help='写出空白业务骨架并开始持久计时');ap.add_argument('--goal',default='',help='starter 使用用户的真实目标');ap.add_argument('--repair',action='store_true',help='仅修正尚未编辑的首次方案方法引用，一次机会');ap.add_argument('--base-hash',help='--repair 所依据的最新方案哈希');a=ap.parse_args()
    if Path(a.out).name=='.sos-planning.json':raise ValueError('输出不能覆盖规划计时与修正记录 .sos-planning.json')
    if a.repair and (a.starter or not a.base_hash):ap.error('--repair 需要 --base-hash，且与 --starter 分开使用')
    if Path(a.out).exists() and not a.repair:raise ValueError('目标已存在；编辑现有方案请使用保存或 apply-edits，避免覆盖用户修改')
    if a.starter:
        if a.draft:ap.error('--starter 不接受输入草案')
        draft=dict(draft_version=2,title='',goal=a.goal,mapping=dict(domain='',action='',input_condition='',capabilities=[]),inputs=[],skills=[],
                   work=[dict(title='',role='core',skill=None,inputs=[],questions=[],gap='',deliverables=[dict(title='',format='',criteria=[])])])
        Path(a.out).resolve().parent.mkdir(parents=True,exist_ok=True)
        with edit_lock(session_path(a.out)):
            state=session(a.out);sos.save(session_path(a.out),state)
            sos.save(a.out,draft);sos.save(Path(a.out).with_suffix('.clock.json'),{'started_epoch':state['started_epoch']})
        print(json.dumps({'path':str(Path(a.out).resolve()),'status':'starter_written','draft':draft,'skill_fields':dict(name='',source='',method_file='',method_sections=[],fit_reason='',input_fit=''),
                          'next':'用上面的骨架填写真实目标、mapping 与 inputs；相关方法读到后用 method_source.py 获取章节 ID。结构字段由编译器生成。'},ensure_ascii=False))
        return
    if not a.draft:ap.error('需要草案路径或 --starter')
    draft=Path(a.draft).resolve()
    if Path(a.out).resolve()==session_path(draft).resolve():raise ValueError('输出不能覆盖任务规划记录')
    Path(a.out).resolve().parent.mkdir(parents=True,exist_ok=True)
    # Same plan lock as HTML saves; reference repair cannot race user edits.
    with edit_lock(Path(a.out)),edit_lock(session_path(draft)):
        state=session(draft)
        compiled=[x for x in state['attempts'] if x.get('status') in ('compiled','compiled_unresolved')]
        if a.repair:
            if not compiled or compiled[-1]['status']!='compiled_unresolved':raise ValueError('--repair 仅用于首次方案的未解决方法引用')
            previous=compiled[-1];current=sos.read(a.out)
            if str(Path(a.out).resolve())!=previous.get('output') or sos.digest(current)!=a.base_hash or a.base_hash!=previous.get('plan_hash'):
                raise ValueError('方案已编辑或目标不匹配；保留用户修改，按最新方案复核能力')
            initial=sos.read(draft.parent/'.sos-planning'/('attempt-'+str(previous['number'])+'.json'))
            if repair_scope(initial)!=repair_scope(sos.read(draft)):raise ValueError('--repair 只修正 method_sections / method_excerpt；范围、技能选择和输入调整通过最新方案处理')
        elif compiled:raise ValueError('本任务首次方案已编译；通过 HTML 保存或能力换用更新现有方案，不能换输出名重新编译覆盖用户选择。')
        if len(state['attempts'])>=2:raise ValueError('本任务已用完两次编译机会；停止改字段和读源码。保留草案及 .planning-error.json 交付阻塞情况，不重命名草案重试。')
        # Validate editable input before consuming a publication/reference-repair slot.
        # Preserve the original clock and every diagnostic; never fabricate a plan.
        try:
            raw=draft.read_bytes()
            fingerprint=hashlib.sha256(raw).hexdigest()
            value=json.loads(raw)
            p,w=prepare(value,draft.parent)
        except (ValueError,KeyError,TypeError,OSError) as e:
            diagnostic=dict(status='invalid_draft',errors=str(e).splitlines(),
                            compile_attempts=len(state['attempts']),attempts_remaining=2-len(state['attempts']),
                            next='按错误位置修正当前草案后重试；输入校验不消耗编译机会。保留计时与已选方法，停止扩展检索。尚未生成 plan.json，不能确认执行。')
            if isinstance(e,json.JSONDecodeError):
                diagnostic.update(line=e.lineno,column=e.colno)
            history=state.setdefault('input_errors',[])
            if history and history[-1].get('sha256')==locals().get('fingerprint'):
                diagnostic['unchanged_input']=True
                diagnostic['next']='草案内容未改变；先修正已列错误，重复运行不会解决问题。'
            else:
                history.append(dict(sha256=locals().get('fingerprint'),epoch=time.time(),errors=diagnostic['errors']))
            sos.save(session_path(draft),state)
            sos.save(draft.parent/'.planning-error.json',diagnostic)
            raise ValueError(json.dumps(diagnostic,ensure_ascii=False))
        attempt=dict(number=len(state['attempts'])+1,draft=str(draft),started_epoch=time.time(),status='running')
        state['attempts'].append(attempt);sos.save(session_path(draft),state)
        try:
            sos.save(draft.parent/'.sos-planning'/('attempt-'+str(attempt['number'])+'.json'),value)
            p['review_protocol_version']=2
            p['handoff_protocol_version']=1
            p['planning_summary']=dict(attempt=attempt['number'],elapsed_seconds=round(time.time()-state['started_epoch'],1),
                                       unresolved_core=[n['id'] for n in p['capability_needs'] if n.get('role')=='core' and n['decision'].get('fit')!='supported'])
            readiness=assess(p)
            if a.repair:
                p['revision']=current['revision']+1
                sos.save(draft.parent/'.sos-planning'/('before-repair-'+str(current['revision'])+'.json'),current)
            sos.save(a.out,p);attempt.update(status='compiled_unresolved' if readiness['status']=='needs_capability' else 'compiled',output=str(Path(a.out).resolve()),plan_hash=sos.digest(p))
        except (ValueError,KeyError,TypeError,OSError) as e:
            attempt.update(status='failed',error=str(e));sos.save(session_path(draft),state)
            diagnostic=dict(errors=str(e).splitlines(),attempt=attempt['number'],attempts_remaining=2-len(state['attempts']),
                            next='仅修正上面字段。保留技能原文；缺少专业方法证据可先交付待核验方案。' if len(state['attempts'])<2 else '停止编译，保留草案与此错误记录，报告阻塞。')
            sos.save(draft.parent/'.planning-error.json',diagnostic)
            raise ValueError(json.dumps(diagnostic,ensure_ascii=False))
        sos.save(session_path(draft),state)
    budget=status(draft)
    result=dict(path=str(Path(a.out).resolve()),plan_hash=sos.digest(p),nodes=len(p['nodes']),budget=budget,readiness=readiness,next=readiness['message'],warnings=w)
    if readiness['status']=='needs_method_review':
        from method_review import packet
        review=Path(a.out).resolve().parent/'.sos'/'method-review.json'
        if review in [Path(m['path']).resolve() for m in p['materials']]:raise ValueError('审阅文件路径与输入冲突；保留输入及已生成方案，指定独立 --review 路径打开审阅')
        sos.save(review,packet(p,Path(a.out).resolve().parent))
        result.update(review=str(review),next='核读所选方法与现有输入画像，填写适配审阅后运行 method_review.py accept '+str(Path(a.out).resolve()))
    if readiness['status']=='needs_capability' and budget['compile_attempts_remaining']:
        result['repair']=shlex.join([sys.executable,str(Path(__file__).resolve()),str(draft),'--out',str(Path(a.out).resolve()),'--repair','--base-hash',sos.digest(p)])
    print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':
    try:main()
    except (ValueError,KeyError,TypeError,OSError) as e:print(str(e),file=sys.stderr);sys.exit(2)
