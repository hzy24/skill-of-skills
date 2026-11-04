#!/usr/bin/env python3
"""Three-step node handoff: open, capture, accept. Host invokes real Skills."""
import argparse, copy, json, secrets, shlex, sys
from pathlib import Path
import sos
from record_skill_use import record
from plan_io import edit_lock

def located(base, value):
    if not isinstance(value,str) or not value.strip():raise ValueError('文件路径不能为空')
    f=Path(value)
    return f.resolve() if f.is_absolute() else (base/f).resolve()

def node_of(p,nid):
    n=next((n for n in p['nodes'] if n['id']==nid),None)
    if n is None:raise ValueError('未知模块：'+str(nid))
    if n['method']=='human':raise ValueError('人工确认节点请按 execution.md 的人工确认流程记录用户决定')
    return n

def paths_for(plan,state,nid):
    # Different ledgers never share an editable receipt or review sheet.
    tag=sos.digest(str(Path(state).resolve()))[:12]
    root=plan.parent/'.sos'/tag/nid
    root.mkdir(parents=True,exist_ok=True)
    return root/'receipt.json',root/'review.json'

def command(action,plan,state,nid):
    return shlex.join([sys.executable,str(Path(__file__).resolve()),action,str(plan),'--state',str(state),'--node',nid])

def next_step(p,s,plan,state):
    for node in p['nodes']:
        if s['nodes'][node['id']]['status']!='complete' and all(s['nodes'][dep]['status']=='complete' for dep in node['depends_on']):
            if node['method']=='human':
                return shlex.join([sys.executable,str(Path(__file__).with_name('sos.py')),'start',str(plan),'--state',str(state),'--node',node['id']])
            return command('open',plan,state,node['id'])
    return shlex.join([sys.executable,str(Path(__file__).resolve()),'audit',str(plan),'--state',str(state)])

def ready(plan,state,nid,verification,base_hash):
    """Register host verification once; derive all redundant readiness fields."""
    p=sos.read(plan);n=node_of(p,nid)
    if sos.digest(p)!=base_hash:raise ValueError('方案已变化；重新 open 获取最新方案后核验')
    if not isinstance(verification,str) or not verification.strip():raise ValueError('需要 --verification 记录已读取的方法、入口与依赖核验结果')
    if p['mode']=='plan_only':return dict(status='plan_only',instruction='当前只生成方案，不准备或执行能力。')
    from method_review import check_current
    check_current(p,plan.parent)
    original=copy.deepcopy(p)
    if state.exists():
        ledger=sos.read_state(state)
        if ledger['plan_hash']!=sos.execution_digest(p):
            sos.ledger(p,state,'reconcile',plan_dir=plan.parent)
    import hashlib
    for binding in n['bindings']:
        c=next(c for c in p['capability_candidates'] if c['id']==binding['candidate_id'])
        m=next(m for m in p['materials'] if m['id']==c['method_support']['material_id'])
        source=located(plan.parent,m['path'])
        if c.get('origin')=='external':
            from acquire import validate,digest,verify_install
            proposal=validate(c['acquisition']);target=plan.parent/'.sos-installed'/digest(proposal)
            try:verify_install(proposal,target)
            except (OSError,ValueError) as e:
                raise ValueError('外部技能尚未按具体提案获准安装：'+c['name']+'；'+str(e))
            source=Path(sos.read(target/'installation.json')['method_path']) if proposal['schema']=='sos-market-proposal-v1' else target/'SKILL.md'
            m['path']=str(source);c['installation_directory']=str(target)
        if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest()!=c['method_support'].get('sha256'):
            raise ValueError('方法原文缺失或与规划版本不一致：'+c['name'])
        # Candidate readiness is shared. Rechecking another node must not rewrite
        # a verified candidate and invalidate completed users of the same Skill.
        if c['setup']['status']!='available':c['setup'].update(status='available',verification=verification)
        if binding['readiness']!='ready':
            binding['readiness']='ready';binding['contract']['verification']=verification
    if p.get('selection_needs_review'):
        remaining=[i for i in p.get('selection_review_nodes',[x['id'] for x in p['nodes']]) if i!=nid]
        p['selection_review_nodes']=remaining;p['selection_needs_review']=bool(remaining)
        p.setdefault('selection_reviews',[]).append(dict(node=nid,basis_hash=base_hash,evidence=verification))
    if p!=original:
        if original.get('review_protocol_version')==2:
            # Ready only verifies existing methods and may relocate an approved
            # external method into its installed directory; bytes were checked
            # above. Preserve the fit decision across this mechanical operation.
            from method_review import basis,sources
            p['professional_review']['basis_hash']=basis(p)
            p['professional_review']['source_hashes']=sources(p,plan.parent)
        if state.exists():
            running=sos.read_state(state)['nodes']
            changed=[x['id'] for x in p['nodes'] if running[x['id']]['status']=='running' and sos.node_signature(p,x)!=sos.node_signature(original,node_of(original,x['id']))]
            if changed:raise ValueError('准备变更会影响仍运行的模块：'+', '.join(changed)+'；先停止相关执行再准备')
        p['revision']+=1;sos.require_plan(p);sos.save(plan,p)
        if state.exists():sos.ledger(p,state,'reconcile',plan_dir=plan.parent)
    return dict(status='prepared',plan_hash=sos.digest(p),next=command('open',plan,state,nid),
                instruction='准备完成；首次 open 加 --evidence 记录实际执行授权。')

def open_node(plan,state,nid,evidence=None):
    from planning_session import validate_owner
    validate_owner(plan.parent)
    validate_owner(state.parent)
    flow=plan.parent/'.sos-flow.json'
    if flow.exists() and sos.read(flow).get('authoring_contract',0)>=9 and not state.resolve().is_relative_to(plan.parent.resolve()):
        raise ValueError('执行状态保存在本任务目录内，不能共享其他任务的 run.json')
    p=sos.read(plan);n=node_of(p,nid)
    sos.require_plan(p)
    from plan_status import assess
    readiness=assess(p)
    if p['mode']=='plan_only':return dict(status='plan_only',instruction='当前只生成方案，不准备或执行能力。')
    if readiness['status'] in ('needs_capability','needs_decision','needs_installation_details','needs_method_review','needs_input_review'):
        return dict(status=readiness['status'],issues=readiness['issues'],questions=p.get('open_questions',[]),instruction=readiness['message'],
                    next=shlex.join([sys.executable,str(Path(__file__).with_name('method_review.py')),'open',str(plan)]) if readiness['status']=='needs_method_review' else None)
    from method_review import check_current
    check_current(p,plan.parent)
    from handoff import require as require_handoff
    approved=state.exists() and sos.read_state(state).get('approved') and sos.read_state(state).get('plan_hash')==sos.execution_digest(p)
    try:require_handoff(p,plan.parent,evidence,confirm=not approved)
    except (ValueError,KeyError,OSError) as error:
        return dict(status='awaiting_user_confirmation' if (plan.parent/'.sos-handoff.json').exists() else 'needs_plan_delivery',instruction=str(error),outputs={})
    pending=[b['skill'] for b in n['bindings'] if b.get('readiness')!='ready' or next(c for c in p['capability_candidates'] if c['id']==b['candidate_id'])['setup']['status']!='available']
    review_needed=p.get('selection_needs_review') and nid in p.get('selection_review_nodes',[x['id'] for x in p['nodes']])
    if pending or review_needed:
        return dict(status='preparation_required',skills=pending,plan_hash=sos.digest(p),
                    next=command('ready',plan,state,nid)+' --base-hash '+sos.digest(p)+' --verification '+shlex.quote('填写实际核验的方法入口与必要依赖'),
                    instruction='先读取已选方法并核验入口；外部技能按方案提案取得单独安装授权。ready 自动更新关联状态，无需编辑 plan 字段或阅读源码。',
                    installation_proposals=[dict(skill=c['name'],proposal_hash=c.get('proposal_hash'),proposal=c.get('acquisition')) for c in p['capability_candidates'] if c.get('origin')=='external' and c['name'] in pending])
    if not state.exists():sos.ledger(p,state,'init',plan_dir=plan.parent)
    s=sos.read_state(state)
    if s['plan_hash']!=sos.execution_digest(p) or any(sos.record_changed(r,completed_outputs=True) for r in s['nodes'].values()):
        s=sos.ledger(p,state,'reconcile',plan_dir=plan.parent)
    if not s['approved']:
        if not evidence:raise ValueError('需要当前方案的执行授权依据：--evidence；沿用真实会话中的授权，不能自行假定')
        s=sos.ledger(p,state,'approve',evidence=evidence,plan_dir=plan.parent)
    current=s['nodes'][nid]
    if current['status']=='complete':return dict(status='complete',outputs=current.get('paths',{}),instruction='该模块已完成；修正已验收成果用 reopen，其他模块完成后 audit。')
    if current['status']=='waiting_review':
        receipt,review=paths_for(plan,state,nid)
        if review.exists():return dict(status='waiting_review',review=str(review),outputs=current.get('paths',{}),next=command('accept',plan,state,nid),instruction='继续现有成果审阅；修正成果后再 capture。')
        return capture(plan,state,nid)
    repairing=current['status']=='failed' and bool(current.get('checks'))
    if current['status']=='pending' or (current['status']=='failed' and not repairing):
        s=sos.ledger(p,state,'start',nid,plan_dir=plan.parent)
    elif s['nodes'][nid]['status']!='running' and not repairing:
        raise ValueError('当前状态 '+s['nodes'][nid]['status']+'；修正待审成果用 capture，审阅完成用 accept')
    receipt,review=paths_for(plan,state,nid)
    identity=dict(schema='sos-receipt-v1',node=nid,signature=sos.node_signature(p,n),attempt=s['nodes'][nid]['attempts'])
    old=sos.read(receipt) if receipt.exists() else {}
    if any(old.get(k)!=v for k,v in identity.items()):
        outputs={}
        for oid in n['outputs']:
            d=next((d for d in p['deliverables'] if d['id']==oid),{})
            ext=d.get('format','dat')
            # Formats are labels, never pathname components.
            if not ext.isalnum():ext='dat'
            outputs[oid]=str(plan.parent/'deliver'/(oid+'.'+ext))
        (plan.parent/'deliver').mkdir(exist_ok=True)
        sos.save(receipt,dict(identity,outputs=outputs,usage=[dict(skill=b['skill'],record=str(receipt.parent/(b['candidate_id']+'.log')),applied=[]) for b in n['bindings']]))
    b=sos.brief(p,nid,sos.digest(p),plan.parent)
    upstream={oid:path for dep in n['depends_on'] for oid,path in s['nodes'][dep].get('paths',{}).items()}
    log=receipt.parent/('execution-'+str(s['nodes'][nid]['attempts'])+'.log')
    usage_file=receipt.parent/'usage.json'
    next_submit=command('submit',plan,state,nid)
    if len(n['bindings'])>1:
        if not usage_file.exists() or any(old.get(k)!=v for k,v in identity.items()):
            sos.save(usage_file,sos.read(receipt)['usage'])
        next_submit+=' --usage '+shlex.quote(str(usage_file))
    elif n['bindings']:
        next_submit+=' --record '+shlex.quote(str(log))+' --applied '+shlex.quote('填写本次实际采用的方法及结果')
    return dict(status='repair_required' if repairing else 'running',instruction=b['instruction'],context=b['context'],upstream_files=upstream,
                receipt=str(receipt),next=next_submit,submit=next_submit,execution_log=str(log),usage_file=str(usage_file) if len(n['bindings'])>1 else None,
                outputs=sos.read(receipt)['outputs'],
                fill='按 outputs 路径生成或修正成果，实际工具/检查输出保存在 execution_log 路径；用 next 命令 submit。已有日志可改 --record，成果路径不同用 --output ID=路径。无需手工填写 receipt。')

def submit(plan,state,nid,log=None,applied=None,outputs=None,usage=None,trace=None):
    p=sos.read(plan);n=node_of(p,nid)
    if usage is not None and (log is not None or applied is not None):raise ValueError('--usage 与 --record/--applied 二选一')
    if len(n['bindings'])>1 and usage is None:raise ValueError('多技能模块请填写 open 返回的 usage_file，用 --usage 提交各技能的实际日志与方法应用')
    receipt,_=paths_for(plan,state,nid)
    if not receipt.exists():raise ValueError('先运行 open 获取当前委托')
    data=sos.read(receipt)
    if usage is None:
        usage=[dict(skill=n['bindings'][0]['skill'],record=str(located(plan.parent,log)),applied=applied)] if n['bindings'] else []
    if not isinstance(usage,list) or any(not isinstance(u,dict) for u in usage) or len(usage)!=len(n['bindings']) or {u.get('skill') for u in usage}!={b['skill'] for b in n['bindings']}:
        raise ValueError('usage 需要逐个覆盖本模块技能，包含 skill、record、applied')
    for u in usage:record(p,nid,plan.parent,u.get('record'),u.get('applied'),u['skill'])
    updates={}
    for item in outputs or []:
        if '=' not in item:raise ValueError('--output 格式为输出ID=实际路径')
        key,value=item.split('=',1)
        if key not in data['outputs'] or key in updates:raise ValueError('输出标识未知或重复：'+key)
        updates[key]=str(located(plan.parent,value))
    data['outputs'].update(updates)
    data['usage']=usage
    if trace is not None:
        from trace_review import inspect
        checked=inspect(p,n,sos.read(trace))
        if checked['unbound']:raise ValueError('实际调用记录含计划外技能：'+', '.join(checked['unbound'])+'；先同步能力分工')
        data['trace_path']=str(trace)
    sos.save(receipt,data)
    return capture(plan,state,nid)

def capture(plan,state,nid):
    p=sos.read(plan);n=node_of(p,nid);s=sos.read_state(state);r=s['nodes'][nid]
    receipt,review=paths_for(plan,state,nid);data=sos.read(receipt)
    expected=dict(schema='sos-receipt-v1',node=nid,signature=sos.node_signature(p,n),attempt=r['attempts'])
    if any(data.get(k)!=v for k,v in expected.items()):raise ValueError('交接单对应旧模块或旧尝试；重新 open 后使用新交接单')
    outputs=data.get('outputs')
    if not isinstance(outputs,dict) or set(outputs)!=set(n['outputs']):raise ValueError('receipt.outputs 需要保留全部输出标识，只修改实际路径')
    paths={k:str(located(plan.parent,v)) for k,v in outputs.items()}
    protected={plan.resolve(),state.resolve(),receipt,review}
    protected.update(located(plan.parent,m['path']) for m in p['materials'])
    protected.update(Path(v) for v in r.get('input_hashes',{}))
    if len(set(paths.values()))!=len(paths) or any(Path(v) in protected for v in paths.values()):raise ValueError('成果需要独立路径，不能覆盖输入、计划或执行记录')
    for path in paths.values():
        if not Path(path).is_file():raise ValueError('成果不存在：'+path+'；receipt 内相对路径以 plan.json 所在目录为基准')
    from artifact_integrity import verify as verify_artifact
    for oid,path in paths.items():
        d=next((d for d in p['deliverables'] if d['id']==oid),{})
        verify_artifact(path,d.get('format'))
    usage=data.get('usage');names=[b['skill'] for b in n['bindings']]
    if not isinstance(usage,list) or any(not isinstance(u,dict) for u in usage) or len(usage)!=len(names) or {u.get('skill') for u in usage}!=set(names):
        raise ValueError('实际使用技能与计划绑定不一致。先用 rebind.py 更新本模块，再按新 Skill 重新核验成果；不要把其他技能登记为旧技能。应为：'+', '.join(names))
    records=[record(p,nid,plan.parent,u.get('record'),u.get('applied'),u['skill']) for u in usage]
    trace_result=None
    if data.get('trace_path'):
        from trace_review import inspect
        trace_result=inspect(p,n,sos.read(data['trace_path']))
        if trace_result['unbound']:raise ValueError('实际调用记录含计划外技能：'+', '.join(trace_result['unbound']))
    if any(Path(u['record_path']) in protected or u['record_path'] in paths.values() for u in records):raise ValueError('执行日志需独立保存，不能使用输入、成果或协议文件充当日志')
    # Preserve the bytes submitted for review. Later appends to a shared host
    # journal must not invalidate a previously accepted node.
    token=secrets.token_hex(16)
    for i,u in enumerate(records):
        original=Path(u['record_path']);snapshot=receipt.parent/'logs'/token/(str(i)+'.log')
        snapshot.parent.mkdir(parents=True,exist_ok=True);snapshot.write_bytes(original.read_bytes())
        u.update(original_record_path=str(original),record_path=str(snapshot))
    action='finish' if r['status']=='running' else 'refresh'
    s=sos.ledger(p,state,action,nid,paths=paths,plan_dir=plan.parent,skill_use=records)
    r=s['nodes'][nid]
    # Carry the actual files for joint reviews. Their source hashes are already
    # protected by the ledger; the reviewer also needs their locations.
    available={m['id']:str(located(plan.parent,m['path'])) for m in p['materials']}
    available.update({oid:path for record in s['nodes'].values() for oid,path in record.get('paths',{}).items()})
    declared={c['id']:c for c in n['checks'] if c.get('id')}
    rows=[dict(id=c['id'],artifact=c['artifact'],path=c['path'],criteria=c['criteria'],
               review_files={ref:available[ref] for ref in declared[c['id']].get('review_inputs',[])},
               result='unverified',locator='',method='',observed='') for c in r['checks'] if c['kind']=='review']
    r['submission']=dict(token=token,checks=copy.deepcopy(r['checks']))
    r['trace_inspection']=trace_result
    sos.save_state(state,s)
    context=dict(goal=p['goal'],constraints=p.get('constraints',[]),assumptions=p.get('assumptions',[]),
                 method_use=[dict(skill=next(c['name'] for c in p['capability_candidates'] if c['id']==u['candidate_id']),
                                  applied_steps=u['applied_steps'],record_path=u['record_path']) for u in r.get('skill_usage',[])])
    packet=dict(schema='sos-review-v1',node=nid,token=token,context=context,items=rows)
    if p.get('review_protocol_version')==2:
        from substantive_review import template
        packet['quality']=template(p,n,paths,records)
        packet['context']['trace_inspection']=trace_result
    sos.save(review,packet)
    return dict(status=r['status'],review=str(review),checks=[dict(id=c.get('id'),kind=c['kind'],passed=c['passed'],detail=c.get('detail')) for c in r['checks']],
                next=command('accept',plan,state,nid) if r['status']=='waiting_review' else next_step(p,s,plan,state),
                instruction='读取真实成果与 review_files，结合 context 中的判断边界、假设及方法使用记录，逐项填写 result、locator、method、observed。修正成果或日志后再次 capture；旧审阅自动失效。')

def accept(plan,state,nid):
    p=sos.read(plan);node_of(p,nid);s=sos.read_state(state);r=s['nodes'][nid]
    _,review=paths_for(plan,state,nid);data=sos.read(review);snapshot=r.get('submission',{})
    if data.get('schema')!='sos-review-v1' or data.get('node')!=nid or not snapshot or data.get('token')!=snapshot['token']:
        raise ValueError('审阅表对应旧快照；读取最近 capture 生成的 review.json 并重新审阅')
    rows=data.get('items');checks=[c for c in snapshot['checks'] if c['kind']=='review']
    if not isinstance(rows,list) or any(not isinstance(e,dict) for e in rows) or len(rows)!=len(checks) or {e.get('id') for e in rows}!={c['id'] for c in checks}:
        raise ValueError('审阅表必须保留全部检查项，不能删除或新增检查 id')
    packet=[]
    for c in checks:
        e=next(e for e in rows if e['id']==c['id'])
        packet.append(dict(id=c['id'],artifact=c['artifact'],sha256=c['sha256'],expected=c['criteria'],
                           **{k:e.get(k) for k in ('result','locator','method','observed')}))
    result=sos.ledger(p,state,'review',nid,evidence='逐项审阅记录：'+str(review),plan_dir=plan.parent,review_data=packet,quality_data=data.get('quality'))
    return dict(status=result['nodes'][nid]['status'],node=nid,next=next_step(p,result,plan,state),
                instruction='继续 next 所列模块；人工节点记录用户真实决定。全部完成后 audit，再通过宿主附件交付实际文件。')

def reopen(plan,state,nid,evidence):
    p=sos.read(plan);node_of(p,nid);s=sos.read_state(state)
    if s['plan_hash']!=sos.execution_digest(p):raise ValueError('方案已变化，先 open 协调最新方案')
    if not isinstance(evidence,str) or not evidence.strip():raise ValueError('reopen 需要 --evidence 记录已发现的问题')
    if s['nodes'][nid]['status']!='complete':raise ValueError('reopen 用于已完成模块；待审成果修正直接 capture')
    affected={nid}
    while True:
        expanded=affected|{n['id'] for n in p['nodes'] if set(n['depends_on'])&affected}
        if affected==expanded:break
        affected=expanded
    if any(s['nodes'][i]['status']=='running' for i in affected):raise ValueError('下游仍在执行，先停止其工作并记录 fail，再重开上游')
    s.setdefault('invalidated',[]).append(dict(plan_hash=s['plan_hash'],reason=evidence,nodes={i:s['nodes'][i] for i in affected}))
    for i in affected:s['nodes'][i]=dict(status='pending',attempts=s['nodes'][i]['attempts'])
    sos.event(s,'reopen',node=nid,affected=sorted(affected),evidence=evidence);sos.save_state(state,s)
    return dict(status='pending',reset=sorted(affected),next=command('open',plan,state,nid))

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('action',choices=['ready','open','submit','capture','accept','reopen','audit']);ap.add_argument('plan');ap.add_argument('--state');ap.add_argument('--node');ap.add_argument('--evidence')
    ap.add_argument('--verification');ap.add_argument('--base-hash');ap.add_argument('--record');ap.add_argument('--applied',action='append');ap.add_argument('--output',action='append');ap.add_argument('--usage');ap.add_argument('--trace',help='实际宿主工具调用列表 JSON；辅助核对临时技能，不以方法阅读冒充执行');a=ap.parse_args()
    plan=Path(a.plan).resolve();state=Path(a.state).resolve() if a.state else plan.parent/'run.json'
    if plan==state:raise ValueError('state 不能覆盖 plan.json')
    if a.action!='audit' and not a.node:ap.error('需要 --node')
    with edit_lock(plan):
        if a.action=='ready':result=ready(plan,state,a.node,a.verification,a.base_hash)
        elif a.action=='open':result=open_node(plan,state,a.node,a.evidence)
        elif a.action=='submit':result=submit(plan,state,a.node,a.record,a.applied,a.output,sos.read(located(plan.parent,a.usage)) if a.usage else None,located(plan.parent,a.trace) if a.trace else None)
        elif a.action=='capture':result=capture(plan,state,a.node)
        elif a.action=='accept':result=accept(plan,state,a.node)
        elif a.action=='reopen':result=reopen(plan,state,a.node,a.evidence)
        else:result=sos.ledger(sos.read(plan),state,'audit',plan_dir=plan.parent)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 1 if result.get('complete') is False or result.get('status')=='failed' else 0

if __name__=='__main__':
    try:sys.exit(main())
    except (ValueError,KeyError,TypeError,OSError) as e:print(str(e),file=sys.stderr);sys.exit(2)
