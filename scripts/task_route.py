"""Business stages are independent of the number of selected skills.

The host authors stage boundaries using the selected methods. This module checks
ownership and dependencies; it does not invent professional phases or answers.
"""
import copy
import re
from pathlib import Path


def filename(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('每个 output 填写一个独立文件名')
    value = value.strip()
    suffix = Path(value).suffix.lstrip('.').lower()
    if ('/' in value or '\\' in value or '\n' in value or
            not re.fullmatch(r'[a-z0-9]{1,12}', suffix) or
            re.search(r'\.[a-zA-Z0-9]{1,12}\s*(?:\+|、|；|;|\band\b)\s*\S+\.', value)):
        raise ValueError('每个 output 只登记一个带扩展名的文件；说明写在 question/check 中：'+value)
    return value


def normalize(document, state):
    """Validate a compact, forward-reference-friendly route before any mutation."""
    if not isinstance(document, dict) or set(document)-{'reason', 'deliver', 'stages'}:
        raise ValueError('路线使用 {reason, deliver, stages}；reason 说明阶段划分依据')
    reason = document.get('reason')
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError('reason 说明依据专业方法如何划分阶段；单阶段说明为何可完整完成任务')
    stages = document.get('stages')
    if not isinstance(stages, list) or not stages:
        raise ValueError('stages 至少包含一个有明确结果的业务阶段')
    rows=[]; titles=set(); outputs=set()
    for raw in stages:
        if not isinstance(raw, dict) or set(raw)-{'title','candidate','question','method','outputs','checks','after','role'}:
            raise ValueError('阶段字段为 title/candidate/question/method/outputs/checks/after，可选 role=production')
        row=copy.deepcopy(raw)
        for key in ('title','candidate','question','method'):
            if not isinstance(row.get(key),str) or not row[key].strip():
                raise ValueError('阶段 '+key+' 填写非空文本')
            row[key]=row[key].strip()
        if row['title'] in titles:raise ValueError('阶段标题重复：'+row['title'])
        titles.add(row['title'])
        if row['candidate'] not in state['candidates']:raise ValueError('candidate 使用已核读候选的编号')
        c=state['candidates'][row['candidate']]
        if row.get('role','core')!='production' and c.get('assessment',{}).get('fit')!='suitable':raise ValueError('阶段需要已 assess suitable 的能力：'+row['candidate'])
        for key in ('outputs','checks'):
            if not isinstance(row.get(key),list) or not row[key] or any(not isinstance(v,str) or not v.strip() for v in row[key]):
                raise ValueError(key+' 使用非空文本列表')
        row['outputs']=[filename(v) for v in row['outputs']]
        if len(set(row['outputs']))!=len(row['outputs']) or outputs.intersection(row['outputs']):
            raise ValueError('每个成果文件只由一个阶段负责')
        outputs.update(row['outputs'])
        row.setdefault('after',[]);row.setdefault('role','core')
        if row['role'] not in ('core','production'):raise ValueError('role 使用 core 或 production')
        if not isinstance(row['after'],list) or any(not isinstance(v,str) for v in row['after']):
            raise ValueError('after 使用上游阶段标题列表')
        if len(set(row['after']))!=len(row['after']):raise ValueError('after 重复引用同一阶段')
        if row['role']=='production' and (not row['after'] or c.get('registration_role')!='support' or c.get('source_profile',{}).get('kind')!='artifact_tool' or c.get('assessment',{}).get('fit')=='unsuitable'):
            raise ValueError('制作阶段需要上游成果及 local --role support 登记的制作能力')
        rows.append(row)
    if not any(r['role']=='core' for r in rows):raise ValueError('路线至少包含一个专业核心阶段')
    for row in rows:
        if set(row['after'])-titles or row['title'] in row['after']:
            raise ValueError('after 引用其他真实阶段标题：'+row['title'])
    scopes=[(r['candidate'],r['question'],r['method'],tuple(sorted(r['after']))) for r in rows]
    if len(set(scopes))!=len(scopes):raise ValueError('阶段的问题、方法和前置完全相同；合并成果或说明各自范围')
    deliver=document.get('deliver')
    if not isinstance(deliver,list) or not deliver or any(not isinstance(v,str) or v not in outputs for v in deliver):
        raise ValueError('deliver 列出需要交付用户的独立文件名，引用阶段 outputs')
    ordered=[];remaining=list(rows)
    while remaining:
        ready=[r for r in remaining if set(r['after'])<={v['title'] for v in ordered}]
        if not ready:raise ValueError('阶段依赖形成循环；保留原草案，修正 after')
        ordered.extend(ready)
        remaining=[r for r in remaining if r not in ready]
    return dict(reason=reason.strip(),deliver=list(dict.fromkeys(deliver)),stages=ordered)


def apply(plan, route):
    """Attach the authored method scope; reuse each skill's existing candidate."""
    plan['task_route_version']=1
    plan['task_route']=dict(reason=route['reason'],verification='host_authored_boundaries')
    by_title={r['title']:r for r in route['stages']}
    for node in plan['nodes']:
        row=by_title.get(node['title'])
        if row:
            node['stage_method']=row['method']
            for oid in node.get('outline_ids',[]):
                outline=next(x for x in plan['content_outline'] if x['id']==oid)
                outline['visual']=row['method']
        else:
            node['stage_method']=node['reason']  # produce --takeover appended after route
    extra_outputs={o for n in plan['nodes'] if n['title'] not in by_title for o in n['outputs']}
    for d in plan['deliverables']:
        d['delivery_role']='final' if d['title'] in route['deliver'] or d['id'] in extra_outputs else 'intermediate'
    sync(plan)


def sync(plan):
    """Rebuild stage contracts from the edited nodes, never a stale route copy."""
    if plan.get('task_route_version')!=1:return
    for node in plan['nodes']:
        for binding in node['bindings']:
            contract=binding.get('contract')
            if not contract:continue
            binding['scope']=node['description']
            contract.update(inputs=list(node['inputs']),outputs=list(node['outputs']),
                required_checks=copy.deepcopy(node['checks']),
                invocation='使用 '+binding['skill']+' 的专业方法完成当前阶段：'+node['description']+
                    '。方法应用：'+node.get('stage_method','')+
                    '。沿用已核验的原文和上游结果，按本阶段范围产出并检查；后续阶段按依赖推进。')
    primary=plan.get('primary_assignment')
    if primary and primary.get('node') not in {n['id'] for n in plan['nodes']}:
        core={n['id'] for n in plan.get('capability_needs',[]) if n.get('role')=='core'}
        primary['node']=next((n['id'] for n in plan['nodes'] if core.intersection(n.get('capability_need_ids',[]))),None)


def reconcile_edits(before, after):
    """One editable stage scope drives requirements, handoffs and execution."""
    prior={n['id']:n for n in before['nodes']}
    producers={o:n['id'] for n in before['nodes']+after['nodes'] for o in n['outputs']}
    for node in after['nodes']:
        old=prior.get(node['id'],{})
        if not old:
            # The editor may reuse an existing selection, not author new evidence.
            bindings=node.get('bindings',[]);ids=node.get('capability_need_ids',[])
            if len(bindings)!=1 or len(ids)!=1 or any(x['id']==ids[0] for x in after['capability_needs']):
                raise ValueError('新增阶段需复用一个已选技能，并使用独立的能力分工编号')
            binding=bindings[0]
            source=next((n for n in before['nodes'] if any(
                b.get('candidate_id')==binding.get('candidate_id') and b['skill']==binding['skill']
                for b in n['bindings'])),None)
            need=next((x for x in before['capability_needs'] if source and
                x['id'] in source.get('capability_need_ids',[]) and
                x.get('decision',{}).get('candidate_id')==binding.get('candidate_id')),None)
            if not need:raise ValueError('新增阶段需复用方案中已选定的技能；新的技能请在对话中选型')
            need=copy.deepcopy(need)
            need.update(id=ids[0],requirement_ids=list(node['requirements']),outline_ids=list(node.get('outline_ids',[])))
            after['capability_needs'].append(need)
            binding=copy.deepcopy(next(b for b in source['bindings'] if b.get('candidate_id')==binding.get('candidate_id') and b['skill']==binding['skill']))
            node['bindings']=[binding]
            binding['readiness']='unknown'
            if binding.get('contract'):binding['contract'].pop('verification',None)
        # Changing prerequisite checkboxes also changes upstream input references.
        if old and node['depends_on']!=old['depends_on']:
            upstream=[o for n in after['nodes'] if n['id'] in node['depends_on'] for o in n['outputs']]
            node['inputs']=list(dict.fromkeys([i for i in node['inputs'] if i not in producers]+upstream))
        outlines=[o for o in after.get('content_outline',[]) if o['id'] in node.get('outline_ids',[])]
        if len(outlines)==1:
            outline=outlines[0];prev=next((o for o in before.get('content_outline',[]) if o['id']==outline['id']),{})
            if old and node['description']==old['description'] and outline.get('claim')!=prev.get('claim'):
                node['description']=outline['claim']
            outline.update(title=node['title'],claim=node['description'],points=[node['description']],
                           visual=node.get('stage_method',''),sources=list(node['inputs']),acceptance=list(node['done_when']))
        if node['done_when']!=old.get('done_when'):
            for check in node['checks']:
                if check['kind']=='review':check['criteria']='；'.join(node['done_when'])
        for requirement in after['requirements']:
            if requirement['id'] in node['requirements']:requirement['text']=node['description']
        for d in after['deliverables']:
            if d['id'] in node['outputs']:d['description']=node['description']
        for need in after.get('capability_needs',[]):
            if need['id'] in node.get('capability_need_ids',[]):
                need['standard']=node['description'];need['decision']['application']=node['description']


def issues(plan):
    if plan.get('task_route_version')!=1:return []
    errors=[]
    if not isinstance(plan.get('task_route',{}).get('reason'),str) or not plan['task_route']['reason'].strip():errors.append('任务路线缺少划分依据')
    for node in plan['nodes']:
        if not isinstance(node.get('stage_method'),str) or not node['stage_method'].strip():errors.append(node['id']+' 缺少阶段方法应用')
        for b in node['bindings']:
            if b.get('scope')!=node['description']:errors.append(node['id']+' 阶段与技能委托范围不一致')
            c=b.get('contract')
            if c and (c.get('inputs')!=node['inputs'] or c.get('outputs')!=node['outputs'] or c.get('required_checks')!=node['checks']):
                errors.append(node['id']+' 阶段交接与执行约定不一致')
    scopes=[(tuple(b.get('candidate_id') for b in n['bindings']),n['description'],n.get('stage_method'),tuple(sorted(n['depends_on']))) for n in plan['nodes']]
    if len(set(scopes))!=len(scopes):errors.append('阶段的问题、方法和前置完全相同；合并成果或说明各自范围')
    if not any(d.get('delivery_role')=='final' for d in plan['deliverables']):errors.append('请保留至少一个最终交付文件')
    titles=[d['title'] for d in plan['deliverables']]
    if len(set(titles))!=len(titles):errors.append('不同阶段不能覆盖同名成果文件')
    for d in plan['deliverables']:
        if d.get('delivery_role') not in ('intermediate','final'):errors.append('成果需声明阶段结果或最终交付')
        try:filename(d['title'])
        except ValueError as e:errors.append(str(e))
    return errors
