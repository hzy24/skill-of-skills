#!/usr/bin/env python3
"""Portable plan validation, rendering and evidence-backed execution ledger. Python 3.9+."""
import argparse, csv, hashlib, json, re, sys, zipfile, os, tempfile
from pathlib import Path
from datetime import datetime, timezone
from xml.etree.ElementTree import ParseError
sys.path.insert(0, str(Path(__file__).resolve().parent))
from selection import validate_selection, require_selection
from pptx_parts import slide_parts
from skill_runtime import brief, native_result
from capability_policy import validate_policy, validate_depth
from scope_edits import cancel_removed_scope
from plan_shape import errors as shape_errors

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def save(path, value):
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.'+p.name+'-', dir=p.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as stream:
            json.dump(value,stream,ensure_ascii=False,indent=2);stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,p)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)

def execution_digest(p):
    return digest({k:v for k,v in p.items() if k not in ('title','revision')})

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

def save_state(path, value):
    # Detect accidental/manual ledger edits, not a security boundary: the host
    # controls these files and can recompute this checksum.
    value['state_format']=2
    value['state_checksum']=digest({k:v for k,v in value.items() if k!='state_checksum'})
    save(path,value)

def read_state(path):
    value=read(path)
    if (value.get('state_format')==2 or 'state_checksum' in value) and value.get('state_checksum')!=digest({k:v for k,v in value.items() if k!='state_checksum'}):
        raise ValueError('执行账本被脚本外修改，校验失败。保留现场，使用新的 --state 重新核验；不要手改产物哈希。')
    return value

def delivery_outline(p, artifact):
    """Select one delivery's content in its declared order, without execution."""
    if not isinstance(artifact, str) or not artifact.strip():
        raise ValueError('outline 需要 --artifact <交付物ID>，请明确要查看的交付物')
    require_plan(p)
    delivery = next((d for d in p['deliverables'] if d['id'] == artifact), None)
    if delivery is None:
        raise ValueError('未知交付物：' + artifact + '；可用交付物：' + ', '.join(d['id'] for d in p['deliverables']))
    refs = delivery.get('outline_ids')
    if not refs:
        return {'artifact':artifact,'items':[], 'requirements':p['requirements'], 'page_count':None, 'item_count':0}
    by_id = {item['id']: item for item in p.get('content_outline', [])}
    missing = [oid for oid in refs if oid not in by_id]
    if missing:
        raise ValueError('交付物 ' + artifact + ' 引用了未知内容蓝图：' + ', '.join(missing))
    page_checks = [c for n in p['nodes'] for c in n['checks']
                   if c['kind'] == 'pptx_pages' and c['artifact'] == artifact]
    fmt = delivery.get('format') or ('pptx' if page_checks else None)
    is_pptx = bool(page_checks) or (isinstance(fmt, str) and fmt.strip().lower().lstrip('.') == 'pptx')
    items = [dict(json.loads(json.dumps(by_id[oid])), number=index)
             for index, oid in enumerate(refs, 1)]
    return {'plan_id': p['id'], 'revision': p['revision'], 'plan_hash': digest(p),
            'artifact': artifact, 'title': delivery.get('title', artifact),
            'format': fmt, 'item_count': len(items),
            'outline_level': delivery.get('outline_level', 'pages' if is_pptx else 'sections'),
            'page_count': ((page_checks[0]['value'] if page_checks else None)
                           if delivery.get('outline_level') == 'sections' else len(items)) if is_pptx else None,
            'outline_ids': list(refs), 'items': items}

def node_signature(p, n):
    needs=[x for x in p.get('capability_needs',[]) if x['id'] in n.get('capability_need_ids',[])]
    candidates={x['decision'].get('candidate_id') for x in needs}
    candidates.update(b.get('candidate_id') for b in n.get('bindings',[]))
    candidates.update(i for x in needs for i in x['decision'].get('direct_basis',{}).get('candidate_ids',[]))
    outlines=set(n.get('outline_ids',[]))
    outlines.update(i for x in needs for i in x.get('outline_ids',[]))
    outlines.update(i for d in p['deliverables'] if d['id'] in n['outputs'] for i in d.get('outline_ids',[]))
    return digest({'node':n,'needs':needs,
      'candidates':[x for x in p.get('capability_candidates',[]) if x['id'] in candidates],
      'requirements':[x for x in p['requirements'] if x['id'] in n['requirements']],
      'materials':[x for x in p['materials'] if x['id'] in n['inputs']],
      'outline':[x for x in p.get('content_outline',[]) if x['id'] in outlines],
      'deliverables':[x for x in p['deliverables'] if x['id'] in n['outputs']],
      'goal':p['goal'],'mode':p['mode'],'constraints':p.get('constraints'), 'max_attempts':p.get('max_attempts'),
      'assumptions':p.get('assumptions'), 'open_questions':p.get('open_questions')})

def widget_view(p):
    """Project the review surface; keep execution machinery in the saved plan."""
    titles={m['id']:m['title'] for m in p['materials']}
    titles.update({d['id']:d['title'] for d in p['deliverables']})
    for n in p['nodes']:
        for out in n['outputs']: titles.setdefault(out,n['title']+'的产物')
    states={'ready':'已可用，无需额外安装','unknown':'安装状态待核验','needs_setup':'需安装或配置'}
    nodes=[]
    for n in p['nodes']:
        view={k:n[k] for k in ('id','title','description','reason','depends_on','done_when')}
        view['input_names']='、'.join(titles.get(i,i) for i in n['inputs']) or '无'
        view['output_names']='、'.join(titles.get(i,i) for i in n['outputs'])
        view['capability']='；'.join(b['skill']+' · '+states[b['readiness']] for b in n['bindings']) or ('等待用户判断' if n['method']=='human' else '当前模型与工具')
        nodes.append(view)
    return {k:p[k] for k in ('id','title','revision','mode','requirements')} | {'hash':digest(p),'nodes':nodes}

def apply_edits(plan, request):
    """Apply a widget change request to exactly the plan the user reviewed.

    Returns a validated plan only; authorization and execution remain host actions.
    """
    if not isinstance(request, dict): raise ValueError('修改请求需要对象')
    if request.get('action') not in ('update_plan', 'execute_plan'):
        raise ValueError('未知的方案操作')
    if (request.get('plan_id') != plan['id'] or
        request.get('base_revision') != plan['revision'] or
        request.get('base_hash') != digest(plan)):
        raise ValueError('页面对应旧版本，请展示当前方案后再修改')
    result = json.loads(json.dumps(plan))
    changes = request.get('changes', {})
    if not isinstance(changes, dict) or set(changes) - {'set', 'nodes'}:
        raise ValueError('修改请求格式无效')
    top = changes.get('set', {})
    allowed = {'title','goal','mode','requirements','materials','deliverables','content_outline',
               'assumptions','open_questions','constraints','capability_candidates','role_tasks'}
    if not isinstance(top, dict) or set(top) - allowed:
        raise ValueError('修改包含不可编辑的方案字段')
    if plan.get('selection_contract_version') == 1 and 'capability_candidates' in top:
        raise ValueError('能力核验和安装授权由宿主重新评估，页面不能直接修改')
    result.update(top)
    edits = changes.get('nodes', [])
    if not isinstance(edits, list): raise ValueError('模块修改需要列表')
    seen = set()
    node_fields = {'title','description','reason','method','depends_on','inputs',
                   'outputs','requirements','done_when','checks','bindings','outline_ids','stage_method'}
    for edit in edits:
        if not isinstance(edit, dict): raise ValueError('模块修改格式无效')
        nid = edit.get('id')
        if not isinstance(nid, str) or nid in seen: raise ValueError('模块修改标识无效或重复')
        seen.add(nid)
        ops = set(edit) - {'id'}
        if len(ops) != 1 or not ops <= {'add','set','remove'}:
            raise ValueError('每个模块修改需指定一种操作')
        current = next((n for n in result['nodes'] if n['id'] == nid), None)
        if 'add' in edit:
            if current or not isinstance(edit['add'],dict) or edit['add'].get('id') != nid:
                raise ValueError('新增模块标识无效')
            result['nodes'].append(edit['add'])
        elif not current: raise ValueError('修改引用了未知模块')
        elif 'remove' in edit:
            if edit['remove'] is not True: raise ValueError('删除操作格式无效')
            result['nodes'].remove(current)
        else:
            if not isinstance(edit['set'],dict) or set(edit['set']) - node_fields:
                raise ValueError('修改包含不可编辑的模块字段')
            current.update(edit['set'])
    malformed=shape_errors(result)
    if malformed:raise ValueError('；'.join(malformed))
    if result.get('task_route_version')==1:
        from task_route import reconcile_edits
        reconcile_edits(plan,result)
    cancel_removed_scope(plan,result)
    if result.get('selection_review_version')==1:
        previous={n['id']:n for n in plan['nodes']}
        for n in result['nodes']:
            old=previous.get(n['id'])
            if not old:continue
            if result['goal']!=plan['goal'] and result.get('primary_assignment',{}).get('node')==n['id'] and n['description']==old['description']:
                n['description']=n['description'].replace(plan['goal'],result['goal'],1)
            if n['description']!=old['description'] and len(n.get('capability_need_ids',[]))==len(n['bindings'])==1:
                need=next(x for x in result['capability_needs'] if x['id']==n['capability_need_ids'][0])
                need['standard']=n['description'];need['decision']['application']=n['description']
                b=n['bindings'][0];b['scope']=n['description'];b['readiness']='unknown'
                if b.get('contract'):
                    b['contract']['invocation']='按所选 Skill 的完整方法完成最新模块范围：'+n['description']
                    b['contract'].pop('verification',None)
                for r in result['requirements']:
                    if r['id'] in n['requirements'] and sum(r['id'] in other['requirements'] for other in result['nodes'])==1:r['text']=n['description']
    if result.get('task_route_version')==1:
        from task_route import sync
        sync(result)
    # A renamed capability cannot retain verification of the previous selection.
    old_contracts = [(b.get('skill'), b.get('scope'), b.get('contract'))
                     for n in plan['nodes'] for b in n['bindings'] if b.get('contract')]
    for n in result['nodes']:
        for b in n['bindings']:
            if b.get('contract') and any(b['contract'] == c and (b.get('skill'), b.get('scope')) != (skill, scope)
                                        for skill, scope, c in old_contracts):
                b.pop('contract'); b['readiness'] = 'unknown'
    if plan.get('selection_contract_version') == 1:
        valid_outline = {x['id'] for x in result.get('content_outline', [])}
        for need in result['capability_needs']:
            need['outline_ids'] = [x for x in need.get('outline_ids',[]) if x in valid_outline]
        if result.get('content_outline') != plan.get('content_outline'):
            counts={d['id']:len(d.get('outline_ids',[])) for d in result['deliverables'] if d.get('outline_level')!='sections'}
            for n in result['nodes']:
                for binding in n['bindings']:
                    for check in binding.get('contract',{}).get('required_checks',[]):
                        if check.get('kind')=='pptx_pages' and check.get('artifact') in counts: check['value']=counts[check['artifact']]
        def substantive(p):
            return {k:v for k,v in p.items() if k not in ('title','revision','confirmation','selection_needs_review')}
        if substantive(result) != substantive(plan):
            previous={n['id']:node_signature(plan,n) for n in plan['nodes']}
            affected={n['id'] for n in result['nodes'] if previous.get(n['id'])!=node_signature(result,n)}
            affected.update(result.get('selection_review_nodes',[]))
            affected.intersection_update(n['id'] for n in result['nodes'])
            result['selection_review_nodes']=sorted(affected)
            result['selection_needs_review']=bool(affected)
    if result != plan:
        if result.get('review_protocol_version')==2:
            from method_review import basis
            if basis(result)!=basis(plan):result.pop('professional_review',None)
        result['revision'] = plan['revision'] + 1
        result.pop('confirmation', None)
    require_plan(result)
    return result

def prose(value):
    if isinstance(value, str): yield value
    elif isinstance(value, list):
        for v in value: yield from prose(v)
    elif isinstance(value, dict):
        for v in value.values(): yield from prose(v)

def validate_content_outline(p):
    """Check reviewable content structure and page accounting, not factual depth.

    Sources are human-readable anchors into the materials. Their existence and
    support for a claim must still be assessed against the actual source files.
    """
    errors = []
    outlines = p.get('content_outline', [])
    if not isinstance(outlines, list):
        return ['content_outline 须为列表']
    ids = set()
    for item in outlines:
        if not isinstance(item, dict):
            errors.append('content_outline 每项须为对象'); continue
        oid = item.get('id')
        if not isinstance(oid, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', oid):
            errors.append('content_outline 标识须使用字母、数字、下划线或连字符')
        elif oid in ids:
            errors.append('content_outline 标识重复：' + oid)
        else:
            ids.add(oid)
        label = str(oid or 'content_outline')
        for key in ('title', 'claim', 'visual'):
            if not isinstance(item.get(key), str) or not item[key].strip():
                errors.append(label + ' 的 ' + key + ' 须为非空字符串')
        for key in ('points', 'sources', 'acceptance'):
            values = item.get(key)
            if not isinstance(values, list) or not values or any(not isinstance(v, str) or not v.strip() for v in values):
                errors.append(label + ' 的 ' + key + ' 须为非空字符串列表')

    references = {}
    for group in ('deliverables', 'nodes'):
        for owner in p[group]:
            if 'outline_ids' not in owner: continue
            refs = owner['outline_ids']
            label = group + '.' + owner['id']
            if not isinstance(refs, list) or (not refs and group == 'deliverables') or any(not isinstance(v, str) or not v.strip() for v in refs):
                errors.append(label + ' 的 outline_ids 须为非空字符串列表'); continue
            if len(set(refs)) != len(refs):
                errors.append(label + ' 的 outline_ids 存在重复引用')
            unknown = set(refs) - ids
            if unknown: errors.append(label + ' 引用了未知内容蓝图：' + ', '.join(sorted(unknown)))
            references[(group, owner['id'])] = refs

    pages = {}
    for n in p['nodes']:
        for c in n['checks']:
            if c.get('kind') == 'pptx_pages' and isinstance(c.get('artifact'), str):
                pages.setdefault(c['artifact'], []).append(c)
    deliverables = {d['id']: d for d in p['deliverables']}
    pptx_ids = set(pages)
    for d in p['deliverables']:
        if 'outline_level' in d and d['outline_level'] not in ('sections','pages'):
            errors.append(d['id'] + ' 的 outline_level 须为 sections / pages')
        fmt = d.get('format')
        if 'format' in d and (not isinstance(fmt, str) or not fmt.strip()):
            errors.append(d['id'] + ' 的 format 须为非空字符串')
        elif isinstance(fmt, str) and fmt.strip().lower().lstrip('.') == 'pptx':
            pptx_ids.add(d['id'])
    if pptx_ids and not outlines:
        errors.append('PPT 规划需要 content_outline，列出本次汇报主题、来源与完成标准')
    for artifact in sorted(pptx_ids):
        if artifact not in deliverables:
            errors.append('PPT 产物 ' + artifact + ' 需要在 deliverables 中关联内容范围')
            continue
        refs = references.get(('deliverables', artifact), [])
        if not refs:
            errors.append(artifact + ' 需要非空 outline_ids，关联本次汇报内容')
        if deliverables[artifact].get('outline_level') == 'sections':
            values={c['value'] for c in pages.get(artifact,[]) if type(c.get('value')) is int}
            if len(values)>1:errors.append(artifact + ' 的页数要求相互冲突')
            continue
        if artifact not in pages:
            errors.append(artifact + ' 需要 pptx_pages 检查以核对完整页数')
        for c in pages.get(artifact, []):
            if type(c.get('value')) is int and c['value'] > 0 and refs and c['value'] != len(refs):
                errors.append(artifact + ' 的页数检查值 ' + str(c['value']) + ' 与逐页蓝图数量 ' + str(len(refs)) + ' 不一致')
    return errors

def validate_capabilities(p):
    """Validate declared capability contracts; source truth remains a host check."""
    errors, warnings = [], []
    version = p.get('capability_contract_version')
    if version is not None and (type(version) is not int or version != 1):
        errors.append('capability_contract_version 需要为 1')
    def text_ok(v): return isinstance(v, str) and bool(v.strip())
    for n in p['nodes']:
        for b in n['bindings']:
            label = n['id'] + ' / ' + str(b.get('skill', '技能'))
            if b.get('readiness') not in ('ready', 'unknown', 'needs_setup'):
                errors.append(label + ' 可用状态无效')
            c = b.get('contract')
            if c is None:
                message = label + ' 尚未核对能力约定'
                (errors if version == 1 and b.get('readiness') == 'ready' else warnings).append(message)
                continue
            if not isinstance(c, dict):
                errors.append(label + ' contract 需要对象'); continue
            for key in ('source', 'source_evidence', 'invocation'):
                if not text_ok(c.get(key)): errors.append(label + ' 缺少 ' + key)
            if c.get('mode') not in ('full', 'branch'):
                errors.append(label + ' mode 需要 full 或 branch')
            if c.get('mode') == 'branch' and not text_ok(c.get('branch_basis')):
                errors.append(label + ' 局部使用需要 branch_basis，保留分支的前置与检查')
            for key in ('inputs', 'outputs'):
                refs = c.get(key)
                if not isinstance(refs, list) or (key == 'outputs' and not refs) or any(not text_ok(x) for x in refs):
                    errors.append(label + ' ' + key + ' 需要产物或材料 ID 列表')
                elif set(refs) - set(n[key]):
                    errors.append(label + ' ' + key + ' 超出模块分工')
            prereqs = c.get('prerequisites')
            if not isinstance(prereqs, list):
                errors.append(label + ' prerequisites 需要列表')
            else:
                for r in prereqs:
                    if not isinstance(r, dict) or not text_ok(r.get('requirement')) or r.get('status') not in ('verified', 'pending'):
                        errors.append(label + ' 前置条件格式无效'); continue
                    if r['status'] == 'verified' and not text_ok(r.get('evidence')):
                        errors.append(label + ' 已核验前置条件需要依据')
                    if b.get('readiness') == 'ready' and r['status'] != 'verified':
                        errors.append(label + ' 前置条件尚未核验，不能标为 ready')
            if b.get('readiness') == 'ready' and not text_ok(c.get('verification')):
                errors.append(label + ' ready 需要本次调用条件的 verification')
            required = c.get('required_checks')
            if not isinstance(required, list) or not required:
                errors.append(label + ' required_checks 需要至少一项交付检查')
            else:
                for check in required:
                    if not isinstance(check, dict) or check.get('artifact') not in (c.get('outputs') if isinstance(c.get('outputs'), list) else []) or check not in n['checks']:
                        errors.append(label + ' 必需检查未完整纳入模块 checks')
                    elif check.get('kind') == 'review' and not text_ok(check.get('criteria')):
                        errors.append(label + ' 人工内容检查需要具体 criteria')
    return errors, warnings

def validate_quality(p):
    errors = []
    version = p.get('quality_contract_version')
    if version is None: return errors
    if type(version) is not int or version != 1:
        return ['quality_contract_version 需要为 1']
    for n in p.get('nodes', []):
        reviews = [c for c in n.get('checks', []) if isinstance(c, dict) and c.get('kind') == 'review']
        ids = [c.get('id') for c in reviews]
        if any(not isinstance(i, str) or not i.strip() for i in ids) or len(set(ids)) != len(ids):
            errors.append(n['id'] + ' 审阅检查需要唯一 id')
        if any(not isinstance(c.get('criteria'), str) or not c['criteria'].strip() for c in reviews):
            errors.append(n['id'] + ' 审阅检查需要具体 criteria')
    if p.get('professional_task') is True and p.get('selection_contract_version') != 1:
        m = p.get('method_assessment', {})
        if not isinstance(m, dict) or m.get('status') not in ('covered', 'limited'):
            errors.append('专业任务需要方法覆盖评估 covered/limited')
        elif not all(m.get(k) for k in ('questions', 'basis', 'planning_effect')):
            errors.append('方法评估需要 questions、basis、planning_effect')
        elif m['status'] == 'limited' and not all(m.get(k) for k in ('gap', 'discovery_result', 'fallback')):
            errors.append('方法不足需记录缺口、检索结果和降级范围')
    return errors


def review_packet(checks, packet):
    """Validate per-check attestations; content truth still needs host inspection."""
    if not isinstance(packet, list): raise ValueError('review-file 内容需要 JSON 列表；请用 execute.py capture 自动生成审阅表，再填写审阅结果')
    expected = [c for c in checks if c['kind'] == 'review']
    ids = [x.get('id') for x in packet if isinstance(x, dict)]
    if len(ids) != len(packet) or len(set(ids)) != len(ids) or set(ids) != {c['id'] for c in expected}:
        raise ValueError('审阅证据必须逐项覆盖检查 id，且不能重复或多余')
    for c in expected:
        e = next(x for x in packet if x['id'] == c['id'])
        if e.get('artifact') != c['artifact'] or e.get('sha256') != c['sha256']:
            raise ValueError('审阅证据的产物或版本不匹配：'+c['id']+'。文件修正后用 execute.py capture 生成新快照并重新审阅，不能修改 run.json。')
        if e.get('result') != 'pass': raise ValueError('存在未通过或未验证的审阅项')
        for key in ('locator', 'method', 'observed', 'expected'):
            if not isinstance(e.get(key), str) or not e[key].strip():
                raise ValueError('审阅证据缺少 ' + key)
    return packet

def validate(p):
    errors, warnings = shape_errors(p), []
    if errors:return errors,warnings
    if not isinstance(p, dict): return ['计划须为对象'], []
    for key in ('id', 'title', 'goal', 'revision', 'mode', 'requirements', 'materials', 'deliverables', 'nodes'):
        if key not in p: errors.append('缺少字段：' + key)
    if errors: return errors, warnings
    if p['mode'] not in ('plan_only', 'execute_after_confirmation'): errors.append('使用方式无效')
    if 'max_attempts' in p and (type(p['max_attempts']) is not int or p['max_attempts']<1): errors.append('max_attempts 须为正整数')
    if type(p['revision']) is not int or p['revision'] < 1: errors.append('版本须为正整数')
    for key in ('requirements', 'materials', 'deliverables', 'nodes'):
        if not isinstance(p[key], list): errors.append(key + ' 须为列表')
    if errors: return errors, warnings
    if not p['nodes'] or not p['requirements'] or not p['deliverables']: errors.append('任务、需求和交付物不能为空')
    for key in ('id','title','goal'):
        if not isinstance(p[key],str) or not p[key].strip(): errors.append(key+' 须为非空文本')
    for group, fields in [('requirements',('text',)),('materials',('title','path')),('deliverables',('title','description'))]:
        for item in p[group]:
            if not isinstance(item,dict): errors.append(group+' 需要对象'); continue
            for key in fields:
                if not isinstance(item.get(key),str) or not item[key].strip(): errors.append(group+'.'+key+' 须为非空文本')
            if group=='materials' and isinstance(item.get('path'),str) and '://' in item['path']:
                errors.append('远程材料请先保存本地快照，原 URL 放 source_url')
    if errors: return errors,warnings
    groups = {}
    for key in ('requirements', 'materials', 'deliverables', 'nodes'):
        ids = [v.get('id') for v in p[key] if isinstance(v, dict)]
        if len(ids) != len(p[key]) or any(not isinstance(i,str) or not re.fullmatch(r'[A-Za-z0-9_-]+',i) for i in ids) or len(set(ids)) != len(ids):
            errors.append(key + ' 标识须唯一且使用字母、数字、下划线或连字符')
        groups[key] = set(i for i in ids if isinstance(i,str))
    if errors: return errors, warnings
    producers, covered = {}, set()
    for n in p['nodes']:
        for key in ('title', 'description', 'reason', 'method', 'depends_on', 'inputs', 'outputs', 'requirements', 'done_when', 'checks', 'bindings'):
            if key not in n: errors.append(n['id'] + ' 缺少 ' + key)
        for key in ('depends_on','inputs','outputs','requirements','done_when','checks','bindings'):
            if key in n and not isinstance(n[key],list): errors.append(n['id'] + ' 的 ' + key + ' 须为列表')
        for key in ('checks', 'bindings'):
            if isinstance(n.get(key), list) and any(not isinstance(v, dict) for v in n[key]):
                errors.append(n['id'] + ' 的 ' + key + ' 每项须为对象')
    if errors: return errors, warnings
    from task_route import issues as route_issues
    errors.extend(route_issues(p))
    for n in p['nodes']:
        for key in ('depends_on','inputs','outputs','requirements','done_when'):
            if any(not isinstance(x,str) or not x.strip() for x in n[key]): errors.append(n['id']+' '+key+' 需要非空字符串')
    if errors: return errors,warnings
    for n in p['nodes']:
        for key in ('inputs','outputs','requirements','depends_on'):
            if any(not re.fullmatch(r'[A-Za-z0-9_-]+',x) for x in n[key]): errors.append(n['id']+' '+key+' 标识格式无效')
    if errors: return errors,warnings
    errors.extend(validate_content_outline(p))
    if errors:return errors,warnings
    errors.extend(validate_quality(p))
    policy_errors,policy_warnings=validate_policy(p)
    errors.extend(policy_errors);warnings.extend(policy_warnings)
    selection_errors, selection_warnings = validate_selection(p)
    errors.extend(selection_errors); warnings.extend(selection_warnings)
    capability_errors, capability_warnings = validate_capabilities(p)
    errors.extend(capability_errors); warnings.extend(capability_warnings)
    for n in p['nodes']:
        nid = n['id']
        if any(not isinstance(n[k],str) or not n[k].strip() for k in ('title','description','reason')): errors.append(nid + ' 文本字段需要清楚填写')
        if n['method'] not in ('direct','skill','human'): errors.append(nid + ' 执行方式无效')
        if not n['outputs'] or not n['done_when']: errors.append(nid + ' 需要产物和完成条件')
        if n['method']=='skill' and not n['bindings']: errors.append(nid + ' 缺少技能绑定')
        for b in n['bindings']:
            if not all(b.get(k) for k in ('skill','scope','reason','readiness')): errors.append(nid + ' 技能说明不完整')
            if b.get('readiness') != 'ready': warnings.append(nid + ' 能力待准备：' + b.get('skill',''))
        for rid in n['requirements']:
            if rid not in groups['requirements']: errors.append(nid + ' 引用了未知需求 ' + str(rid))
            covered.add(rid)
        for dep in n['depends_on']:
            if dep not in groups['nodes'] or dep == nid: errors.append(nid + ' 依赖无效：' + str(dep))
        for out in n['outputs']:
            if out in producers or out in groups['materials']: errors.append('产物重复：' + str(out))
            producers[out] = nid
        check_ids=[c.get('id') for c in n['checks'] if c.get('kind') in ('native','review') and isinstance(c.get('id'),str)]
        if len(set(check_ids))!=len(check_ids): errors.append(nid+' 原生验证和审阅检查 id 不能重复')
        for c in n['checks']:
            if c.get('kind') not in ('file','text_contains','csv_columns','pptx_pages','review','native'): errors.append(nid + ' 检查类型无效')
            if c.get('artifact') not in n['outputs']: errors.append(nid + ' 检查产物无效')
            if c.get('kind') in ('text_contains','csv_columns') and (not isinstance(c.get('values'),list) or not c['values'] or any(not isinstance(v,str) for v in c['values'])): errors.append(nid + ' 检查需要非空字符串列表')
            if c.get('kind')=='text_contains':
                fmt=next((d.get('format','').lower().lstrip('.') for d in p['deliverables'] if d['id']==c.get('artifact')),'')
                if fmt in ('docx','xlsx','pptx','pdf'):errors.append(nid+' 二进制文档需要格式解析或内容审阅，不能使用 text_contains')
                if c.get('values') and all(str(v).strip() in ('复核通过','检查通过','通过','合格','pass','PASS') for v in c['values']):errors.append(nid+' 结论标签不能单独作为检查证据')
            if c.get('kind')=='native':
                for key in ('id','criteria','source','evidence','cwd'):
                    if not isinstance(c.get(key),str) or not c[key].strip(): errors.append(nid+' 原生验证缺少 '+key)
                if c.get('evidence') not in n['outputs'] or c.get('evidence')==c.get('artifact'): errors.append(nid+' 原生验证需要独立的证据输出')
                if not isinstance(c.get('argv'),list) or not c['argv'] or any(not isinstance(x,str) or not x for x in c['argv']): errors.append(nid+' 原生验证 argv 需要非空字符串列表')
                if not any(x.get('kind')=='file' and x.get('artifact')==c.get('evidence') for x in n['checks']): errors.append(nid+' 原生验证记录需要 file 检查')
            if c.get('kind')=='pptx_pages' and (type(c.get('value')) is not int or c['value']<1): errors.append(nid + ' 页数须为正整数')
    graph = {n['id']: n['depends_on'] for n in p['nodes']}
    def ancestors(nid, trail=()):
        if nid in trail: raise ValueError('依赖关系存在循环')
        found=set()
        for dep in graph.get(nid,[]): found.add(dep); found.update(ancestors(dep, trail+(nid,)))
        return found
    for n in p['nodes']:
        try: prev=ancestors(n['id'])
        except ValueError as e: errors.append(str(e)); break
        for inp in n['inputs']:
            if inp not in groups['materials'] and (inp not in producers or producers[inp] not in prev): errors.append(n['id'] + ' 输入缺少有效上游：' + str(inp))
        for c in n['checks']:
            if 'review_inputs' in c and (c['kind']!='review' or not c['review_inputs'] or any(i not in n['outputs']+n['inputs'] for i in c['review_inputs'])):
                errors.append(n['id']+' 联合审阅只能引用本模块产物及已声明的上游输入')
        checked={c.get('artifact') for c in n['checks']}
        if set(n['outputs']) - checked: errors.append(n['id'] + ' 每项产物需要检查')
    if groups['requirements'] - covered: errors.append('需求未覆盖：' + ', '.join(sorted(groups['requirements'] - covered)))
    for d in p['deliverables']:
        if d['id'] not in producers: errors.append('交付物没有负责模块：' + d['id'])
    for s in prose([{k:n[k] for k in ('title','description','reason','done_when')} for n in p['nodes']]):
        if re.search(r'不是[^。！？\n]{0,80}而是|是[^。！？\n]{0,80}而不是|并非[^。！？\n]{0,80}而', s): warnings.append('文风待润色：' + s[:100])
    return list(dict.fromkeys(errors)), list(dict.fromkeys(warnings))

def require_plan(p):
    errors,warnings=validate(p)
    if errors: raise ValueError('；'.join(errors))
    return warnings

def event(s, action, **data):
    s['events'].append(dict(time=datetime.now(timezone.utc).isoformat(), action=action, **data))

def inspect_check(c, paths):
    path=Path(paths[c['artifact']]).resolve()
    result={'kind':c['kind'],'artifact':c['artifact'],'path':str(path),'passed':False}
    if c.get('id'): result['id'] = c['id']
    if c.get('criteria'): result['criteria'] = c['criteria']
    if not path.is_file(): result['detail']='产物文件缺失'; return result
    data=path.read_bytes(); result['sha256']=hashlib.sha256(data).hexdigest()
    kind=c['kind']
    try:
        if kind=='file': result['passed']=len(data)>0; result['detail']=f'{len(data)} bytes'
        elif kind=='text_contains':
            if path.suffix.lower() in ('.docx','.xlsx','.pptx','.pdf') or data.startswith((b'PK\x03\x04',b'%PDF')):raise ValueError('text_contains 仅适用于纯文本；请解析实际格式或配置内容审阅')
            text=data.decode('utf-8'); missing=[v for v in c['values'] if v not in text]
            result.update(passed=not missing,detail={'missing':missing})
        elif kind=='csv_columns':
            columns=next(csv.reader(data.decode('utf-8-sig').splitlines()),[])
            missing=[v for v in c['values'] if v not in columns]; result.update(passed=not missing,detail={'columns':columns,'missing':missing})
        elif kind=='pptx_pages':
            with zipfile.ZipFile(path) as z: count=len(slide_parts(z))
            result.update(passed=count==c['value'],detail={'expected':c['value'],'actual':count})
        elif kind=='native':
            passed,detail=native_result(c,paths,result['sha256']);result.update(passed=passed,detail=detail)
        elif kind=='review': result['detail']='等待宿主提供基于实际内容的审阅证据'
    except (ValueError, OSError, KeyError, ParseError, zipfile.BadZipFile, UnicodeError) as e: result['detail']=str(e)
    return result

def record_changed(record, completed_outputs=False):
    """Compare actual evidence bytes; pending review edits use refresh instead."""
    snapshots=list(record.get('input_hashes',{}).items())
    snapshots.extend((r['record_path'],r['record_sha256']) for r in record.get('skill_usage',[]))
    if completed_outputs and record.get('status')=='complete':
        snapshots.extend((c['path'],c.get('sha256')) for c in record.get('checks',[]))
    return any(not Path(path).is_file() or hashlib.sha256(Path(path).read_bytes()).hexdigest()!=sha for path,sha in snapshots)

def ledger(p, statepath, action, node_id=None, evidence=None, paths=None, plan_dir=None, review_data=None, skill_use=None, quality_data=None):
    # A CLI invocation may run from the skill's scripts directory. References
    # inside the task belong to the plan directory, without rewriting its hash.
    base_dir = Path(plan_dir).resolve() if plan_dir is not None else Path.cwd()
    def task_path(value):
        path = Path(value)
        return path if path.is_absolute() else base_dir / path
    def input_snapshot(n):
        return {str(task_path(m['path']).resolve()):hashlib.sha256(task_path(m['path']).read_bytes()).hexdigest()
                for m in p['materials'] if m['id'] in n['inputs']}
    def sources_changed(record):
        return record_changed(record)
    require_plan(p)
    if action=='init':
        if Path(statepath).exists(): raise ValueError('执行记录已存在，请使用新的路径')
        s={'signatures':{n['id']:node_signature(p,n) for n in p['nodes']},'plan_hash':execution_digest(p),'plan_revision':p['revision'],'approved':False,'nodes':{n['id']:{'status':'pending','attempts':0} for n in p['nodes']},'events':[]}
        event(s,'init'); save_state(statepath,s); return s
    s=read_state(statepath)
    if action=='reconcile':
        signatures={n['id']:node_signature(p,n) for n in p['nodes']}
        affected={nid for nid,signature in signatures.items() if s.get('signatures',{}).get(nid)!=signature}
        while True:
            expanded=affected | {n['id'] for n in p['nodes'] if set(n['depends_on']) & affected}
            if expanded==affected: break
            affected=expanded
        for n in p['nodes']:
            old=s['nodes'].get(n['id'],{})
            if record_changed(old,completed_outputs=True): affected.add(n['id'])
        while True:
            expanded=affected | {n['id'] for n in p['nodes'] if set(n['depends_on']) & affected}
            if expanded==affected: break
            affected=expanded
        retired={nid:r for nid,r in s['nodes'].items() if nid in affected or nid not in signatures}
        if retired:s.setdefault('invalidated',[]).append({'plan_hash':s['plan_hash'],'nodes':retired})
        s['nodes']={n['id']:({'status':'pending','attempts':0} if n['id'] in affected else s['nodes'][n['id']]) for n in p['nodes']}
        s.update(signatures=signatures,plan_hash=execution_digest(p),plan_revision=p['revision'],approved=False if affected else s['approved'])
        event(s,'reconcile',affected=sorted(affected));save_state(statepath,s);return s
    if s['plan_hash']!=execution_digest(p): raise ValueError('计划已修改，请复核新版本并 reconcile 更新执行记录')
    if action=='audit':
        failures=[]
        from handoff import require as require_handoff
        try:require_handoff(p,base_dir)
        except (ValueError,KeyError,OSError) as error:failures.append(str(error))
        if p.get('review_protocol_version')==2:
            from method_review import check_current
            try:check_current(p,base_dir)
            except (ValueError,OSError) as error:failures.append(str(error))
        for nid,r in s['nodes'].items():
            if sources_changed(r): failures.append(nid + ' 来源材料已变化')
            node=next(n for n in p['nodes'] if n['id']==nid)
            if r['status']=='complete' and any(m['id'] in node['inputs'] for m in p['materials']) and 'input_hashes' not in r: failures.append(nid+' 缺少来源版本记录，请重新执行')
            if r['status']!='complete': failures.append(nid + ' 尚未完成')
            if p.get('review_protocol_version')==2 and node['method']!='human' and not r.get('substantive_review',{}).get('passed'):failures.append(nid+' 计划履约核对未通过')
            if p.get('capability_policy_version')==3 and node['bindings'] and not r.get('skill_usage'):failures.append(nid+' 缺少专业技能执行记录')
            for check in r.get('checks',[]):
                f=Path(check['path'])
                if not f.is_file() or hashlib.sha256(f.read_bytes()).hexdigest()!=check.get('sha256'): failures.append(nid + ' 产物已变化')
        event(s,'audit',failures=failures); save_state(statepath,s)
        return {'complete':not failures,'failures':failures,'plan_revision':p['revision']}
    if action=='approve':
        from handoff import require as require_handoff
        require_handoff(p,base_dir,evidence,confirm=True)
        if p['mode']=='plan_only': raise ValueError('当前为仅规划模式')
        if not evidence: raise ValueError('需记录用户的明确执行指令')
        s['approved']=True; event(s,'approve',evidence=evidence)
    else:
        if not s['approved']: raise ValueError('等待用户授权执行')
        n=next((n for n in p['nodes'] if n['id']==node_id),None)
        if not n: raise ValueError('未知模块')
        r=s['nodes'][node_id]
        if action=='start':
            from handoff import require as require_handoff
            require_handoff(p,base_dir)
            from method_review import check_current
            check_current(p,base_dir)
            require_selection(p, n)
            if r['status'] not in ('pending','failed'): raise ValueError('模块当前无法启动')
            if p.get('max_attempts') is not None and r['attempts']>=p['max_attempts']: raise ValueError('已达到本任务启动预算，请调整方法或预算')
            if any(s['nodes'][d]['status']!='complete' for d in n['depends_on']): raise ValueError('上游尚未完成检查或确认')
            if any(b['readiness']!='ready' for b in n['bindings']): raise ValueError('能力尚未准备完成')
            for material in p['materials']:
                if material['id'] in n['inputs'] and not task_path(material.get('path','')).is_file(): raise ValueError('材料缺失：' + material['id'])
            # Re-read upstream files: previously accepted evidence must remain valid.
            upstream=set()
            def collect(nid):
                for d in next(x for x in p['nodes'] if x['id']==nid)['depends_on']:
                    if d not in upstream: upstream.add(d); collect(d)
            collect(node_id)
            for dep in upstream:
                if sources_changed(s['nodes'][dep]): raise ValueError('上游来源材料已变化，请重新检查')
                for check in s['nodes'][dep].get('checks',[]):
                    f=Path(check['path'])
                    if not f.is_file() or hashlib.sha256(f.read_bytes()).hexdigest()!=check.get('sha256'): raise ValueError('上游产物已变化，请重新检查并规划')
            r['input_hashes']=input_snapshot(n)
            r.pop('skill_usage',None)
            if p.get('capability_policy_version')==3:
                for binding in n['bindings']:
                    candidate=next(c for c in p['capability_candidates'] if c['id']==binding['candidate_id'])
                    support=candidate.get('method_support',{})
                    material=next(m for m in p['materials'] if m['id']==support['material_id'])
                    actual=r['input_hashes'].get(str(task_path(material['path']).resolve()))
                    if support.get('sha256') and support['sha256']!=actual:raise ValueError('技能原文已变化，请重新核对适配：'+candidate['name'])
                if p.get('method_evidence_version')==1:
                    from method_source import entry,verify_evidence
                    for need in p['capability_needs']:
                        if need['id'] not in n.get('capability_need_ids',[]) or need.get('role')!='core':continue
                        ev=need.get('method_evidence',{})
                        m=next(m for m in p['materials'] if m['id']==ev['material_id'])
                        _,body=entry(task_path(m['path']).read_text(encoding='utf-8'))
                        if not verify_evidence(body,ev):raise ValueError('核心方法片段无法在原文正文定位，请重新评估：'+need['id'])
            # Snapshot accepted upstream evidence as inputs for the whole run.
            for dep in upstream:
                r['input_hashes'].update(s['nodes'][dep].get('input_hashes',{}))
                r['input_hashes'].update({c['path']:c['sha256'] for c in s['nodes'][dep].get('checks',[])})
                r['input_hashes'].update({u['record_path']:u['record_sha256'] for u in s['nodes'][dep].get('skill_usage',[])})
            r.update(status='waiting_user' if n['method']=='human' else 'running',attempts=r['attempts']+1)
        elif action in ('finish','refresh'):
            changed=(any(not Path(path).is_file() or hashlib.sha256(Path(path).read_bytes()).hexdigest()!=sha for path,sha in r.get('input_hashes',{}).items()) if action=='refresh' else sources_changed(r))
            if changed: raise ValueError('来源材料已变化，请 fail 后重新 start')
            if action=='finish' and r['status']!='running': raise ValueError('模块尚未运行')
            if action=='refresh' and (r['status'] not in ('waiting_review','failed') or not r.get('checks')): raise ValueError('refresh 仅用于已提交产物的修正；其他情况先 start')
            if not paths or set(paths)!=set(n['outputs']): raise ValueError('实际产物映射需覆盖全部输出')
            from skill_usage import verify as verify_skill_use
            usage=verify_skill_use(p,n,skill_use,r.get('input_hashes',{}),base_dir)
            if r.get('checks'):
                r.setdefault('superseded',[]).append({k:r[k] for k in ('checks','paths','skill_usage','review_details') if k in r})
            r.pop('review_details',None)
            if usage:r['skill_usage']=usage
            r['paths']={k:str(task_path(v).resolve()) for k,v in paths.items()}
            r.pop('substantive_review',None)
            r['checks']=[inspect_check(c,r['paths']) for c in n['checks']]
            hard=[c for c in r['checks'] if c['kind']!='review']
            r['status']='failed' if any(not c['passed'] for c in hard) else ('waiting_review' if any(c['kind']=='review' for c in r['checks']) else 'complete')
            if p.get('review_protocol_version')==2 and r['status']=='complete':r['status']='waiting_review'
        elif action=='review':
            if sources_changed(r): raise ValueError('来源材料已变化，请 fail 后重新 start')
            if r['status'] not in ('waiting_review','waiting_user'): raise ValueError('当前无需审阅')
            if not evidence: raise ValueError('需记录审阅依据或用户确认原文')
            if p.get('review_protocol_version')==2 and n['method']!='human':
                from substantive_review import validate as substantive_validate
                assessment=substantive_validate(p,n,quality_data,r.get('paths',{}))
                if not assessment['passed']:raise ValueError('计划履约核对未通过，修正成果后重新 capture')
                observed={x['skill'] for x in (r.get('trace_inspection') or {}).get('observed',[])}
                if not observed.issubset(quality_data['observed_skills']):raise ValueError('计划履约核对遗漏了实际调用记录中的技能')
                r['substantive_review']=assessment
            if r['status']=='waiting_user':
                if not paths or set(paths)!=set(n['outputs']): raise ValueError('请保存人工确认记录并提供全部产物')
                r['paths']={k:str(task_path(v).resolve()) for k,v in paths.items()}
                r['checks']=[inspect_check(c,r['paths']) for c in n['checks']]
            if p.get('quality_contract_version') == 1 and n['method'] != 'human':
                review_packet(r.get('checks', []), review_data)
                r['review_details'] = review_data
            for check in r.get('checks',[]):
                f=Path(check['path'])
                if not f.is_file() or hashlib.sha256(f.read_bytes()).hexdigest()!=check.get('sha256'): raise ValueError('审阅产物已变化，请重新检查')
                if check['kind']=='review': check.update(passed=True,review_evidence=evidence)
            if any(not c['passed'] for c in r['checks']): raise ValueError('产物检查尚未通过')
            r['status']='complete'
        elif action=='fail':
            if r['status'] not in ('running','waiting_review','waiting_user'): raise ValueError('模块未处于执行阶段')
            if not evidence: raise ValueError('请记录失败依据')
            r.update(status='failed',failure=evidence)
        event(s,action,node=node_id,status=r['status'],evidence=evidence)
    save_state(statepath,s); return s

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('command',choices=['validate','render','outline','apply-edits','init','approve','start','finish','refresh','review','fail','audit','reconcile','brief'])
    ap.add_argument('plan'); ap.add_argument('--out'); ap.add_argument('--state'); ap.add_argument('--node'); ap.add_argument('--evidence'); ap.add_argument('--artifacts',help='JSON file mapping output IDs to actual file paths')
    ap.add_argument('--verbose',action='store_true',help='Print full execution state; default prints compact status')
    ap.add_argument('--current', action='store_true', help='Require current selection, capability and quality protocols for new plans')
    ap.add_argument('--review-file', help='JSON list of per-check evidence for quality contract v1')
    ap.add_argument('--skill-use-file', help='JSON list of method-version, execution-record and output references for each selected skill')
    ap.add_argument('--widget',action='store_true',help='Render a ShowWidget HTML fragment')
    ap.add_argument('--edit',help='JSON widget interaction request')
    ap.add_argument('--artifact',help='Deliverable ID whose ordered content outline to read')
    a=ap.parse_args(); p=read(a.plan)
    if a.command=='validate':
        e,w=validate(p)
        if a.current:
            if not isinstance(p,dict):return 1
            if p.get('capability_policy')!='skills_first':e.append('新计划需要 capability_policy: skills_first')
            if p.get('capability_policy_version')!=3:e.append('新计划需要 capability_policy_version: 3')
            e.extend(k + ' 新计划须为 1' for k in ('selection_contract_version','capability_contract_version','quality_contract_version','method_evidence_version') if type(p.get(k)) is not int or p.get(k) != 1)
        if a.current and not e:e.extend(validate_depth(p))
        print(json.dumps({'errors':e,'warnings':w},ensure_ascii=False,indent=2)); return bool(e)
    require_plan(p)
    if a.command=='brief':
        if not a.node: raise ValueError('需要 --node 指定模块')
        if a.out and Path(a.out).resolve()==Path(a.plan).resolve(): raise ValueError('调用说明不能覆盖方案文件')
        data=brief(p,a.node,digest(p),Path(a.plan).resolve().parent)
        if a.out: save(a.out,data)
        else: print(json.dumps(data,ensure_ascii=False,indent=2))
    elif a.command=='outline':
        print(json.dumps(delivery_outline(p,a.artifact),ensure_ascii=False,indent=2))
    elif a.command=='render':
        template=Path(__file__).resolve().parents[1]/'assets'/'plan.html'
        payload=json.dumps(p,ensure_ascii=False,indent=2).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
        out=Path(a.out or 'plan.html')
        if out.resolve()==Path(a.plan).resolve():raise ValueError('HTML 输出不能覆盖 plan.json')
        out.parent.mkdir(parents=True,exist_ok=True)
        html=template.read_text(encoding='utf-8').replace('__PLAN_DATA__',payload).replace('__PLAN_HASH__',digest(p))
        from plan_status import assess
        html=html.replace('__PLAN_READINESS__',json.dumps(assess(p),ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026'))
        if a.widget: raise ValueError('旧 widget 已退出；请使用 plan_server.py 交付当前 HTML')
        out.write_text(html,encoding='utf-8'); print(out.resolve())
    elif a.command=='apply-edits':
        if not a.edit or not a.out: raise ValueError('需要 --edit 和 --out')
        updated=apply_edits(p,read(a.edit)); save(a.out,updated)
        print(json.dumps({'path':str(Path(a.out).resolve()),'revision':updated['revision'],'execution_started':False},ensure_ascii=False))
    else:
        if not a.state: raise ValueError('需要 --state')
        result=ledger(p,a.state,a.command,a.node,a.evidence,read(a.artifacts) if a.artifacts else None,plan_dir=Path(a.plan).resolve().parent,review_data=read(a.review_file) if a.review_file else None,skill_use=read(a.skill_use_file) if a.skill_use_file else None)
        if not a.verbose and 'nodes' in result:
            result={'state':str(Path(a.state).resolve()),'plan_revision':result['plan_revision'],
                    'approved':result['approved'],'nodes':{k:v['status'] for k,v in result['nodes'].items()},
                    'last_event':result['events'][-1] if result['events'] else None}
        print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0

if __name__=='__main__':
    try: sys.exit(main())
    except (ValueError,KeyError,TypeError,OSError) as e: print(str(e),file=sys.stderr); sys.exit(2)
