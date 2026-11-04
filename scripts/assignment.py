"""Compile a professional assignment, keeping source identifiers out of authoring.

Source binding proves provenance, not semantic adequacy. The host reads the Skill
and explains the choice; the specialist interprets fields and performs the work.
"""
import copy,hashlib,re
from pathlib import Path
from method_source import entry,sections

def form(goal):
    return dict(brief_version=3,title=goal,constraints=[],assumptions=[],questions_for_user=[],suggestions=[],work=[])

def source_refs(candidate,questions):
    """Select real source anchors deterministically, including inspected resources."""
    path=Path(candidate['method_file']);raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=candidate['sha256']:raise ValueError('已核读的技能原文发生变化')
    catalog=[dict(x,ref=x['id']) for x in sections(entry(raw.decode('utf-8'))[1])]
    for relative,resource in candidate.get('resources',{}).items():
        raw=Path(resource['file']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=resource['sha256']:raise ValueError('已核读的方法资源发生变化')
        catalog += [dict(x,ref=relative+'::'+x['id']) for x in sections(raw.decode('utf-8'))]
    concepts=re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z][a-zA-Z-]{2,}',' '.join(questions).lower())
    def rank(row):
        heading=row['title'].lower();body=row['text'].lower()
        operational=bool(re.search(r'install|setup|license|changelog|安装|部署|许可|更新日志',heading))
        methodological=bool(re.search(r'workflow|method|process|analysis|procedure|步骤|流程|方法|分析|审查|操作',heading))
        return (not operational,methodological,sum(t in body for t in concepts))
    return [r['ref'] for r in sorted(catalog,key=rank,reverse=True)[:3]]

def expand(brief,state):
    """The v3 author never supplies section IDs, quotations or input mappings."""
    b=copy.deepcopy(brief)
    if b.get('brief_version')!=3:return b
    b['brief_version']=2
    multiple_core=sum(w.get('purpose','core')=='core' for w in b.get('work',[]) if isinstance(w,dict))>1
    for w in b.get('work',[]):
        if not isinstance(w,dict):raise ValueError('每份委托填写工作对象')
        candidate=state['candidates'].get(w.get('candidate'))
        questions=w.get('questions',[])
        if isinstance(questions,str):questions=[questions]
        # A single specialist keeps the whole request. With several specialists,
        # preserve each explicit professional scope and the plan-level request;
        # do not ask the first specialist to perform everyone else's discipline.
        if 6<=state.get('authoring_contract',0)<10 and multiple_core and w.get('title')==state.get('primary_title') and len(questions)>1:
            questions=[q for q in questions if q!=state['goal']]
        if not questions or any(not isinstance(q,str) or not q.strip() for q in questions):raise ValueError('questions 填写需要专业 Skill 回答的问题文本')
        refs=(candidate.get('assessment',{}).get('methods',[]) if state.get('authoring_contract',0)>=6 else source_refs(candidate,questions)) if candidate else []
        reason=w.get('expertise','')
        if isinstance(reason,dict):reason=reason.get('reason','')
        if candidate and not reason.strip():raise ValueError('填写选择该专业技能的理由')
        w['questions']=[dict(question=q,methods=[dict(section=r,application=reason) for r in refs]) for q in questions]
        w['input_basis']='已提供：'+'、'.join(x['name'] for x in state['inputs'])+'。专业 Skill 在执行开始时解释字段、确认口径与适用条件，再完成委托。'
    return b

def item(candidate,title,reason,questions,outputs,checks,role='core',after=()):
    if not title.strip() or not reason.strip():raise ValueError('填写工作标题和选型理由')
    if not questions or not outputs or not checks:raise ValueError('委托需要业务问题、成果文件名和交付要求')
    if any(not isinstance(x,str) or not x.strip() for x in [*questions,*outputs,*checks,*after]):raise ValueError('委托条目使用非空文本')
    deliverables=[]
    for name in dict.fromkeys(outputs):
        from task_route import filename
        name=filename(name)
        suffix=Path(name).suffix.lstrip('.').lower()
        if not suffix or '/' in name or '\\' in name:raise ValueError('成果使用带扩展名的文件名，如 分析报告.md；路径由执行阶段确定')
        deliverables.append(dict(title=name,format=suffix,criteria=list(dict.fromkeys(checks))))
    return dict(title=title,purpose=role,candidate=candidate,expertise=reason,questions=list(dict.fromkeys(questions)),after=list(after),deliverables=deliverables)
