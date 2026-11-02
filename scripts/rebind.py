#!/usr/bin/env python3
"""Replace one module's whole-task Skill without rewriting scope or user edits."""
import argparse, copy, json, sys
from pathlib import Path
import sos
from business_draft import expand
from plan_io import edit_lock

def replace(p,nid,skill,base,reason,verification):
    if not isinstance(reason,str) or not reason.strip() or not isinstance(verification,str) or not verification.strip():
        raise ValueError('需要实际的换用原因和宿主入口/依赖验证依据')
    result=copy.deepcopy(p)
    n=next((n for n in result['nodes'] if n['id']==nid),None)
    if n is None:raise ValueError('未知模块')
    needs=[x for x in result['capability_needs'] if x['id'] in n['capability_need_ids']]
    if len(n['bindings'])!=1 or len(needs)!=1 or n['bindings'][0]['contract']['mode']!='full':
        raise ValueError('此入口用于一个 Skill 整体负责一个模块；多绑定或部分分支需重新评估分工后修改方案')
    if result.get('selection_needs_review') and nid in result.get('selection_review_nodes',[x['id'] for x in result['nodes']]):
        raise ValueError('用户修改后的业务范围尚待复核；先处理 selection_review_nodes，再调整技能')
    # Reuse original-source validation instead of a second hand-authored schema.
    draft=dict(draft_version=2,title=p['title'],goal=p['goal'],mapping=p['mapping'],
               inputs=[dict(name='已有输入',path=p['materials'][0]['path'])],skills=[skill],
               work=[dict(title=n['title'],role='core',skill=skill.get('name'),inputs=['已有输入'],
                          questions=[n['description']],deliverables=[dict(title='当前委托成果',format='md',criteria=n['done_when'])])])
    compiled=expand(draft,base)
    c=compiled['capability_candidates'][0];m=compiled['materials'][-1]
    def fresh(prefix,values):
        i=1
        while prefix+str(i) in values:i+=1
        return prefix+str(i)
    cid=fresh('C',[x['id'] for x in result['capability_candidates']])
    mid=fresh('S',[x['id'] for x in result['materials']]+[o for x in result['nodes'] for o in x['outputs']])
    c['id']=cid;c['method_support']['material_id']=mid;m['id']=mid
    c['setup'].update(status='available',verification=verification)
    old=n['bindings'][0];oldcandidate=next(x for x in result['capability_candidates'] if x['id']==old['candidate_id'])
    oldmid=oldcandidate['method_support']['material_id']
    n['inputs']=[mid if x==oldmid else x for x in n['inputs']]
    if mid not in n['inputs']:n['inputs'].append(mid)
    contract=copy.deepcopy(old['contract'])
    contract.update(inputs=copy.deepcopy(n['inputs']),source=c['source'],source_evidence=c['evidence'][0]['finding'],
                    invocation='按 '+m['path']+' 的完整 Skill 指令完成本模块，使用宿主已核验的入口',verification=verification)
    n['bindings']=[dict(skill=c['name'],candidate_id=cid,readiness='ready',scope=old['scope'],reason=reason,contract=contract)]
    if c.get('origin')=='external':
        c['setup']['status']='approval_needed';n['bindings'][0]['readiness']='needs_setup'
    needs[0]['existing_assessment']=reason
    fit=compiled['capability_needs'][0]['decision']['fit'] if needs[0].get('role')=='core' else 'supported'
    needs[0]['decision'].update(kind='skill',candidate_id=cid,fit=fit,reason=reason,
                                application=c['method_support']['workflow']+'；本次委托：'+n['description'])
    needs[0]['decision'].pop('method_issue',None)
    if fit!='supported':needs[0]['decision']['method_issue']=compiled['capability_needs'][0]['decision'].get('method_issue','方法适配待核验')
    needs[0].pop('method_evidence',None)
    if compiled['capability_needs'][0].get('method_evidence'):
        needs[0]['method_evidence']=dict(compiled['capability_needs'][0]['method_evidence'],material_id=mid)
    if fit!='supported':n['bindings'][0]['readiness']='unknown'
    result['materials'].append(m);result['capability_candidates'].append(c);result['revision']+=1
    result.setdefault('capability_changes',[]).append(dict(node=nid,previous=oldcandidate['name'],selected=c['name'],reason=reason,revision=result['revision']))
    sos.require_plan(result)
    return result

def add_support(p,nid,skill,base,reason,verification,outputs):
    n=next((n for n in p['nodes'] if n['id']==nid),None)
    if not n:raise ValueError('未知模块')
    if not isinstance(outputs,list) or not outputs or len(set(outputs))!=len(outputs) or not set(outputs)<=set(n['outputs']):raise ValueError('--outputs 指定辅助技能负责的现有成果 ID')
    if any(b['skill']==skill.get('name') for b in n['bindings']):raise ValueError('该技能已绑定；按原有职责执行')
    # Compile and validate the new method through the same source validator.
    temp=copy.deepcopy(p);tn=next(x for x in temp['nodes'] if x['id']==nid)
    if not tn['bindings']:raise ValueError('先为模块落实核心能力，再增加辅助能力')
    omitted=set(tn['capability_need_ids'][1:])
    tn['bindings']=tn['bindings'][:1];tn['capability_need_ids']=tn['capability_need_ids'][:1]
    referenced={ref for x in temp['nodes'] for ref in x['capability_need_ids']}
    temp['capability_needs']=[x for x in temp['capability_needs'] if x['id'] not in omitted or x['id'] in referenced]
    replacement=replace(temp,nid,skill,base,reason,verification)
    added_node=next(x for x in replacement['nodes'] if x['id']==nid)
    b=copy.deepcopy(added_node['bindings'][0]);c=next(x for x in replacement['capability_candidates'] if x['id']==b['candidate_id'])
    mid=c['method_support']['material_id'];m=next(x for x in replacement['materials'] if x['id']==mid)
    result=copy.deepcopy(p);n=next(x for x in result['nodes'] if x['id']==nid)
    need=copy.deepcopy(next(x for x in replacement['capability_needs'] if x['id'] in added_node['capability_need_ids']))
    index=1
    while 'support-'+str(index) in {x['id'] for x in result['capability_needs']}:index+=1
    need.update(id='support-'+str(index),role='support',task_kind='production',standard=reason)
    need['decision']['fit']='supported';need['decision']['reason']=reason
    b.update(scope=reason,reason=reason)
    b['contract'].update(inputs=list(dict.fromkeys(n['inputs']+[mid])),outputs=outputs,
                         required_checks=[copy.deepcopy(x) for x in n['checks'] if x.get('artifact') in outputs])
    n['inputs'].append(mid);n['bindings'].append(b);n['capability_need_ids'].append(need['id'])
    result['capability_needs'].append(need);result['capability_candidates'].append(c);result['materials'].append(m)
    result['revision']+=1;result.pop('professional_review',None)
    result.setdefault('capability_changes',[]).append(dict(node=nid,added=c['name'],outputs=outputs,reason=reason,revision=result['revision']))
    sos.require_plan(result)
    return result

def update(plan,state,nid,skill,reason,verification,base_hash,add=False,outputs=None):
    p=sos.read(plan)
    if sos.digest(p)!=base_hash:raise ValueError('方案已有新版本；读取最新 plan.json 后重新评估换用，保留用户修改')
    if state.exists():sos.read_state(state)
    updated=add_support(p,nid,skill,plan.parent,reason,verification,outputs) if add else replace(p,nid,skill,plan.parent,reason,verification)
    updated.pop('professional_review',None)
    # Lock held by CLI also excludes HTML saves. Reconciliation is recoverable
    # after interruption: open always compares current plan with the ledger.
    backup=plan.parent/'.sos'/('before-rebind-'+str(p['revision'])+'-'+sos.digest(p)[:12]+'.json')
    sos.save(backup,p);sos.save(plan,updated)
    result=sos.ledger(updated,state,'reconcile',plan_dir=plan.parent) if state.exists() else None
    return dict(revision=updated['revision'],plan_hash=sos.digest(updated),backup=str(backup),
                reset=result['events'][-1]['affected'] if result else [nid],
                next='重新 open 受影响模块，沿用实际会话授权；按新 Skill 工作并重新检查成果。已有未受影响节点保留；本命令不证明新技能已执行。')

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('plan');ap.add_argument('--state');ap.add_argument('--node',required=True)
    ap.add_argument('--skill',required=True,help='单个业务草案 skills 对象的 JSON 文件；原文路径以 plan 目录为基准')
    ap.add_argument('--reason',required=True);ap.add_argument('--verification',required=True);ap.add_argument('--base-hash',required=True)
    ap.add_argument('--add-support',action='store_true');ap.add_argument('--outputs',nargs='+',help='辅助能力负责的现有成果 ID');a=ap.parse_args()
    if bool(a.outputs)!=a.add_support:ap.error('--add-support 和 --outputs 一起使用')
    plan=Path(a.plan).resolve();state=Path(a.state).resolve() if a.state else plan.parent/'run.json'
    if state==plan:raise ValueError('state 不能覆盖 plan')
    with edit_lock(plan):result=update(plan,state,a.node,sos.read(a.skill),a.reason,a.verification,a.base_hash,a.add_support,a.outputs)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':
    try:main()
    except (ValueError,KeyError,TypeError,OSError) as e:print(str(e),file=sys.stderr);sys.exit(2)
