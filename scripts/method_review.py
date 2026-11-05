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
    if 'assignment_protocol_version' in p:value['assignment_protocol_version']=p['assignment_protocol_version']
    if 'selection_policy_version' in p:value['selection_policy_version']=p['selection_policy_version']
    if 'message_protocol_version' in p:value['message_protocol_version']=p['message_protocol_version']
    for key in ('selection_review_version','primary_assignment','selection_decisions','task_route_version','task_route','stage_review_version','method_coverage_version','review_submission_version'):
        if key in p:value[key]=copy.deepcopy(p[key])
    if 'input_contract_version' in p:value['input_contract_version']=p['input_contract_version']
    if p.get('flow_protocol_version')==1:value['coverage_map']=copy.deepcopy(p.get('coverage_map'))
    if p.get('profile_policy_version')==1:value['profile_policy_version']=1
    if 'discovery_scope' in p:value['discovery_scope']=copy.deepcopy(p['discovery_scope'])
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
    state=base/'.sos-flow.json'
    exists=state.exists();s=sos.read(state) if exists else {};contract=s.get('authoring_contract',0)
    if exists and contract>=14 and p.get('review_submission_version')!=2:
        raise ValueError('判断输入与来源分离协议不可删除')
    if exists and contract>=13 and p.get('method_coverage_version')!=1:
        raise ValueError('方法覆盖与判断边界协议不可删除')
    if exists and contract>=11 and p.get('stage_review_version')!=1:
        raise ValueError('阶段适配审阅协议不可删除')
    if exists and contract>=10 and p.get('task_route_version')!=1:
        raise ValueError('业务阶段路线协议不可删除')
    if exists and contract>=9:
        from planning_session import validate_owner
        validate_owner(base)
        if p.get('message_protocol_version')!=2:raise ValueError('交付承诺协议不可删除')
        expected_profile=3 if contract>=13 else 2
        if any(c.get('source_profile',{}).get('profile_version')!=expected_profile for c in p.get('capability_candidates',[])):
            raise ValueError('用途职责画像不可退回旧版')
    if exists and contract>=7 and p.get('selection_policy_version')!=2:
        raise ValueError('专用优先的选型协议不可删除')
    if exists and contract>=6:
        if p.get('selection_review_version')!=1:raise ValueError('选型与核心职责协议不可删除')
        if p.get('primary_assignment',{}).get('request')!=s['goal']:raise ValueError('保留原始交办记录；用户修改的范围通过方案与适配复核记录')
        for c in p.get('capability_candidates',[]):
            original=next((x for x in s['candidates'].values() if x['source']==c['source'] and x['name']==c['name']),None)
            if original and original.get('assessment',{}).get('fit')=='unsuitable':raise ValueError('已淘汰候选不能通过修改方案重新入选')
            if s.get('authoring_contract',0)>=13 and original:
                chosen=c.get('selection_assessment',{});registered=original.get('assessment',{})
                if 'method' in (chosen.get('coverage'),registered.get('coverage')):
                    fields=('coverage','scope','limits','methods','reason','specific_searches','compared_candidates')
                    if any(chosen.get(k)!=registered.get(k) for k in fields):
                        raise ValueError('方法覆盖范围或比较依据与已登记选型不一致；重新评估后更新方案')
    if exists and contract>=5 and p.get('assignment_protocol_version')!=1:
        raise ValueError('专业委托协议不可删除')
    if exists and contract==4:
        from method_inputs import tabular,check
        profiles=sos.read(base/'input-profile.json')
        from capability_profile import task_kind
        if tabular(profiles) and task_kind(s['goal'])!='artifact':
            if p.get('input_contract_version')!=1:raise ValueError('输入适配协议不可删除')
            for need in p.get('capability_needs',[]):
                if need.get('role')!='core' or need.get('decision',{}).get('kind')!='skill':continue
                methods=need.get('domain_method_evidence') or need.get('method_evidence',{}).get('sections',[])
                records=need.get('method_input_checks',[])
                if {x['id'] for x in methods}!={x['section'] for x in records}:raise ValueError('每个所选方法均需保留输入适配记录')
                for record in records:
                    section=next((x for x in methods if x['id']==record['section']),None)
                    if section is None:raise ValueError('输入适配记录没有对应的原文方法')
                    found=check(record.get('inputs',[]),section['excerpt'],profiles,True)
                    if found:raise ValueError('；'.join(found))
    if exists and s.get('version')==2 and (p.get('profile_policy_version')!=1 or p.get('review_protocol_version')!=2):
        raise ValueError('当前任务的画像与方法审阅协议不可删除，恢复原方案协议后复核')
    if exists and s.get('discovery_scope')!=p.get('discovery_scope'):
        raise ValueError('任务专业对象与检索记录不同；保留原始需求及其方法范围')
    if p.get('review_protocol_version')!=2:return
    from capability_profile import issues,classify
    problems=issues(p)
    if problems:raise ValueError('；'.join(x['reason'] for x in problems))
    if p.get('profile_policy_version')==1:
        materials={m['id']:m for m in p['materials']}
        for c in p['capability_candidates']:
            if not c.get('source_profile'):continue
            m=materials[c['method_support']['material_id']];path=Path(m['path']);path=path if path.is_absolute() else base/path
            if classify(path.read_text(),c['source_profile'].get('profile_version',1))!=c['source_profile']:raise ValueError('能力画像与实际方法来源不一致，重新核对')
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
        current_work=[n['description'] for n in p['nodes'] if need['id'] in n.get('capability_need_ids',[]) and len(n.get('capability_need_ids',[]))==1]
        question='；'.join(current_work) if p.get('selection_review_version')==1 and current_work else need['standard']
        rows.append(dict(need=need['id'],role=need.get('role'),question=question,
                         skill=c['name'] if c else None,
                         method_file=materials[c['method_support']['material_id']]['path'] if c else None,
                         verdict='unverified',method_quote=((need.get('method_evidence') or {}).get('sections') or [need.get('method_evidence') or {}])[0].get('excerpt','')[:1200],reason='',input_basis='',limits=''))
    result=dict(schema='sos-method-review-v1',basis_hash=basis(p),source_hashes=sources(p,base),
                goal=p['goal'],mapping=p.get('mapping'),materials=p['materials'],deliverables=p['deliverables'],
                assignments=[dict(node=n['id'],work=n['description'],outputs=n['outputs'],skills=[b['skill'] for b in n['bindings']]) for n in p['nodes']],
                review_guide=str(ROOT/'references/composed-methods.md'),
                instruction='逐项核读所选方法与输入画像，判断能否承担 question 中的工作及负责成果。核心项的 reason 对照 mapping.domain / mapping.action：指出一个需要领域知识的实际判断及原文给出的具体规则。检验该理由换成其他行业是否仍完全成立；只剩描述统计、趋势、相关性或报告结构时标 fail。统计方法本身是用户目标时按该统计专业要求评估；通用的分析、比较、呈现、验证流程不足以证明领域判断已覆盖。缺少核心方法时标 fail 并实际寻找专业候选。用户是否熟悉术语不改变此标准。文件操作/格式验证不能证明具备业务判断方法；制作本身是目标时制作技能可以胜任。核查核心方法与制作职责是否均有实际分工；候选列表中出现技能不代表它已负责工作。仅记录本次适配、依据与判断边界，不开展分析或起草。无方法覆盖时标 fail；证据未读到标 unverified。',
                items=rows)
    if p.get('assignment_protocol_version')==1:
        result['instruction']='核对专业委托与实际 Skill 的用途、方法和运行前提是否契合。原文引用已自动绑定，字段解释与口径核实交给执行阶段。普通字段改名、派生指标或多表整理不构成规划阻塞；真实材料缺失或外部系统要求说明影响。保留原始任务范围与文件制作分工，记录适配理由及限制。'
    if p.get('task_route_version')==1:
        result['stage_reason']=p['task_route']['reason']
        for assignment,node in zip(result['assignments'],p['nodes']):
            assignment.update(method_application=node['stage_method'],depends_on=node['depends_on'])
        result['instruction']+=' 核对阶段是否覆盖原始交办、问题范围是否清楚、交接结果是否足够。结合方法判断拆分粒度；阶段数量与技能数量分别考虑。'
    if p.get('selection_review_version')==1:
        for row in rows:
            c=next((x for x in p['capability_candidates'] if x['name']==row['skill']),{})
            row.update(judged_by='host',verification='source_and_ownership_only',reason=c.get('selection_assessment',{}).get('reason',''))
    if p.get('stage_review_version')==1:
        result['instruction']='一次核对整条路线：每阶段回答原始目标中的哪个问题或提供哪个必要证据？实际方法如何支持它？关键前提由哪些材料支持或可正常整理得到？填写 verdict/pass|fail|unverified、reason、input_basis、limits；引用已绑定。字段改名、拼表、合理派生交给专业技能；不预填无依据的阈值，不新增无关决策，不计算业务结果。'
        by_need={need:n for n in p['nodes'] for need in n.get('capability_need_ids',[])}
        for row in rows:
            n=by_need[row['need']]
            row.update(stage=n['title'],method_application=n.get('stage_method',''),
                       upstream=[dict(title=v['title'],outputs=[d['title'] for d in p['deliverables'] if d['id'] in v['outputs']]) for v in p['nodes'] if v['id'] in n['depends_on']],
                       outputs=[d['title'] for d in p['deliverables'] if d['id'] in n['outputs']],
                       reason='',judged_by='host',verification='host_stage_fit_judgment')
            if p.get('method_coverage_version')==1:
                c=next((v for v in p['capability_candidates'] if v['name']==row['skill']),{})
                a=c.get('selection_assessment',{})
                row['method_boundary']={k:copy.deepcopy(a.get(k)) for k in ('coverage','scope','limits','reason')} if a.get('coverage')=='method' else None
            if p.get('review_submission_version')!=2:
                row['subject_hash']=sos.digest(dict(goal=p['goal'],constraints=p.get('constraints'),assumptions=p.get('assumptions'),questions=p.get('open_questions'),row=row,checks=n['checks'],
                    upstream_scope=[dict(question=v['description'],method=v.get('stage_method')) for v in p['nodes'] if v['id'] in n['depends_on']],
                    inputs=[dict(material=m,sha=result['source_hashes'][str((base/Path(m['path'])).resolve())]) for m in p['materials'] if m['id'] in n['inputs']]))
        if p.get('review_submission_version')==2:
            bind_subjects(result,p,base)
        result=reuse_items(result,p.get('professional_review') or p.get('professional_review_cache'))
    if p.get('method_coverage_version')==1:
        result['instruction']+=' 对 method 覆盖的阶段，逐项核对声明的 scope 与 limits：所选章节实际提供什么方法，当前阶段的结论是否超出其能力，未覆盖的业务判断是否由已有制度、其他技能或明确的人工复核承接。通用统计能承担其适用的分析工作；行业合理性结论需要另有依据。只有承诺与方法范围一致才可通过。'
    if p.get('review_submission_version')==2:
        result['instruction']='核对整条路线的目标、方法适配和输入前提。只在 decisions.json 填写 need、verdict、reason；reason 简述方法如何支持本阶段、材料是否足够以及结论范围。可选 input_basis/limits 用于额外说明。此文件是只读上下文，引用与版本由程序维护。计算、判断和成品内容留给确认后的专业执行。'
    return result

def bind_subjects(context,p,base):
    """Bind cached judgments to source bytes, all bindings and transitive inputs."""
    by_need={need:n for n in p['nodes'] for need in n.get('capability_need_ids',[])}
    rows={n['id']:[] for n in p['nodes']}
    for row in context['items']:rows[by_need[row['need']]['id']].append(row)
    nodes={n['id']:n for n in p['nodes']};needs={n['id']:n for n in p['capability_needs']}
    candidates={c['id']:c for c in p['capability_candidates']};done={}
    def bind(nid):
        if nid in done:return done[nid]
        n=nodes[nid];mids=set(n['inputs']);paths=set();subjects=[]
        for row in rows[nid]:
            subjects.append({k:v for k,v in row.items() if k not in ('subject_hash','verdict','reason','input_basis','limits')})
            need=needs[row['need']];c=candidates.get(need.get('decision',{}).get('candidate_id'),{})
            mids.add(c.get('method_support',{}).get('material_id'))
            for section in need.get('domain_method_evidence',[]):
                if section.get('source_file'):paths.add(str((base/Path(section['source_file'])).resolve()))
        paths.update(str((base/Path(m['path'])).resolve()) for m in p['materials'] if m['id'] in mids)
        source_hashes={path:context['source_hashes'][path] for path in sorted(paths) if path in context['source_hashes']}
        done[nid]=sos.digest(dict(goal=p['goal'],constraints=p.get('constraints'),assumptions=p.get('assumptions'),questions=p.get('open_questions'),
            subjects=subjects,checks=n['checks'],inputs=n['inputs'],sources=source_hashes,upstream=[bind(dep) for dep in n['depends_on']]))
        return done[nid]
    for nid,items in rows.items():
        for row in items:row['subject_hash']=sos.digest(dict(node=bind(nid),need=row['need']))

def reuse_items(packet,previous):
    """Reuse real judgments only for byte-identical stage subjects and sources."""
    if not previous:return packet
    prior={r.get('subject_hash'):r for r in previous.get('items',[]) if r.get('subject_hash') and r.get('verdict')=='pass'}
    for row in packet['items']:
        old=prior.get(row.get('subject_hash'))
        if old:
            for key in ('verdict','reason','input_basis','limits'):row[key]=old[key]
    return packet

def accept(p,data,base):
    from capability_profile import issues
    from review_form import ReviewInputError
    if not isinstance(data,dict):raise ValueError('适配判断需要对象')
    if data.get('schema')!='sos-method-review-v1' or data.get('basis_hash')!=basis(p):raise ValueError('适配审阅对应旧方案，重新 open')
    if data.get('source_hashes')!=sources(p,base):raise ValueError('适配审阅来源已变化，重新 open')
    expected=packet(p,base)['items'];rows=data.get('items')
    if not isinstance(rows,list) or len(rows)!=len(expected) or any(not isinstance(r,dict) or not isinstance(r.get('need'),str) for r in rows) or {r.get('need') for r in rows}!={r['need'] for r in expected}:raise ValueError('逐项保留全部能力需求')
    problems=issues(p)
    if problems and any(r.get('verdict')=='pass' for r in rows):raise ValueError('；'.join(x['reason'] for x in problems))
    by_need={e['need']:e for e in expected};errors=[]
    protected=['role','question','skill','method_file']
    if p.get('stage_review_version')==1:protected+=['stage','method_application','upstream','outputs','subject_hash','method_quote','judged_by','verification']
    if p.get('method_coverage_version')==1:protected+=['method_boundary']
    for i,r in enumerate(rows):
        e=by_need[r['need']]
        for key in protected:
            if r.get(key)!=e.get(key):errors.append(dict(path='items['+str(i)+'].'+key,message='审阅对象已更改；使用程序生成的来源与阶段信息。'))
        if r.get('verdict') not in ('pass','fail','unverified'):errors.append(dict(path='items['+str(i)+'].verdict',message='使用 pass/fail/unverified'))
        required=('reason','input_basis','limits') if r.get('verdict')=='pass' and p.get('review_submission_version')!=2 else ('reason',)
        for key in required:
            if not isinstance(r.get(key),str) or not r[key].strip():errors.append(dict(path='items['+str(i)+'].'+key,message='填写实际判断'))
    if errors:raise ReviewInputError(errors)
    state=base/'.sos-flow.json'
    initial=state.exists() and sos.read(state).get('phase')!='delivered'
    for r in rows:
        if r['verdict']!='pass':continue
        e=by_need[r['need']]
        candidate=next((c for c in p['capability_candidates'] if c['name']==e['skill']),{})
        if p.get('selection_review_version')==1 and e['role']=='core':
            a=candidate.get('selection_assessment',{})
            if a.get('fit')!='suitable' or r.get('judged_by')!='host' or (initial and p.get('stage_review_version')!=1 and r.get('reason')!=a.get('reason')):
                raise ValueError('原文核验不能自动替代专业适配判断；使用已记录的宿主选型结论')
        if e['role']=='core' and candidate.get('method_scope') in ('general','delivery'):
            raise ValueError('通用分析或配套制作方法不能通过核心专业适配审阅；保留为 support 并选择核心方法')
        if not e['method_file']:raise ValueError('没有方法来源的能力不能通过')
        path=Path(e['method_file']);path=path if path.is_absolute() else base/path
        quote=r.get('method_quote')
        if not isinstance(quote,str) or not quote.strip() or quote not in path.read_text(encoding='utf-8'):raise ValueError('method_quote 须为方法原文中的实际片段')
    result=copy.deepcopy(p)
    result['professional_review']=dict(basis_hash=basis(p),source_hashes=data['source_hashes'],
                                      verdict='pass' if all(r['verdict']=='pass' for r in rows) and rows else 'fail',items=copy.deepcopy(rows))
    result.pop('professional_review_cache',None)
    result['revision']+=1
    return result


def record(p):
    return dict(schema='sos-method-review-v1',**copy.deepcopy(p['professional_review']))

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('action',choices=['open','accept']);ap.add_argument('plan');ap.add_argument('--review');a=ap.parse_args()
    plan=Path(a.plan).resolve();review=Path(a.review).resolve() if a.review else plan.parent/'.sos'/'method-review.json'
    if review==plan:raise ValueError('review 不能覆盖方案')
    with edit_lock(plan):
        p=sos.read(plan);sos.require_plan(p)
        if p.get('flow_protocol_version')==1:
            state=sos.read(plan.parent/'.sos-flow.json')
            if state.get('phase')!='delivered':raise ValueError('首次规划的适配映射由 flow.py build 生成；运行 flow.py <任务目录> status 完成交付，不单独重写 verdict。')
        if a.action=='open':
            if p.get('review_protocol_version')!=2:p['review_protocol_version']=2;p['revision']+=1;sos.save(plan,p)
            if p.get('review_submission_version')==2:
                from review_form import prepare
                import shlex
                result=prepare(p,plan.parent)
                result['review']=result['review_file']
                result['next_command']=shlex.join([sys.executable,str(Path(__file__).resolve()),'accept',str(plan),'--review',result['review_file']])
                result['next']='阅读 context_file，在 review_file 填写 need、verdict、reason 后提交。程序复用未变化阶段的已通过判断。'
            else:
                protected=[(Path(x['path']) if Path(x['path']).is_absolute() else plan.parent/x['path']).resolve() for x in p['materials']]
                if review in protected or review in (plan.parent/'run.json',plan.parent/'.sos-planning.json'):raise ValueError('review 不能覆盖来源或执行状态')
                sos.save(review,packet(p,plan.parent));result=dict(review=str(review),next='核读方法与输入画像，填写此表后运行 method_review.py accept '+str(plan))
        else:
            if p.get('review_submission_version')==2:
                from review_form import accept_file,location
                updated=accept_file(p,review if a.review else location(packet(p,plan.parent),plan.parent),plan.parent)
            else:updated=accept(p,sos.read(review),plan.parent)
            sos.save(plan,updated)
            from plan_status import assess
            result=assess(updated)
    if a.action=='accept' and updated.get('handoff_protocol_version')==1:
        from plan_delivery import prepare
        result=prepare(plan)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':
    try:main()
    except (ValueError,KeyError,TypeError,OSError) as e:
        from review_form import ReviewInputError
        if isinstance(e,ReviewInputError):print(json.dumps(e.result,ensure_ascii=False))
        else:print(str(e),file=sys.stderr)
        sys.exit(2)
