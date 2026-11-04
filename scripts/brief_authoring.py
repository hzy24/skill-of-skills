"""One question record owns its methods and input limits; no repeated text joins."""
import copy

def as_list(value):
    """Lossless scalar-to-list normalization; never synthesize business evidence."""
    return value if isinstance(value,list) else [] if value is None else [value]

def normalize(brief):
    """Convert the small authoring form to the existing compiler interface.

    v1 remains readable for saved tasks. v2 has no model-authored coverage/gap
    cross references. Missing methods become capability state, not schema errors.
    """
    if not isinstance(brief,dict):raise ValueError('业务委托需要 JSON 对象')
    b=copy.deepcopy(brief)
    if b.get('brief_version',1)==1:return b,[]
    if b.pop('brief_version')!=2:raise ValueError('brief_version 使用 2')
    suggestions=b.pop('suggestions',[])
    if not isinstance(suggestions,list):suggestions=[suggestions] if suggestions else []
    suggestions=[x if isinstance(x,str) else '：'.join(str(x[k]) for k in ('title','detail','description','reason') if x.get(k)) if isinstance(x,dict) else str(x) for x in suggestions]
    suggestions=[x for x in suggestions if x.strip()]
    for key in ('constraints','assumptions'):b[key]=as_list(b.get(key,[]))
    b['work']=as_list(b.get('work',[]))
    if not b['work']:raise ValueError('work 需要至少一个业务委托')
    if not isinstance(b.get('constraints',[]),list):raise ValueError('constraints 使用文本列表')
    pending=b.pop('questions_for_user',[])
    if isinstance(pending,str):pending=[pending] if pending.strip() else []
    if not isinstance(pending,list):raise ValueError('questions_for_user 使用问题文本列表')
    choices=b.pop('decisions',[])
    if not isinstance(choices,list):choices=[choices] if choices else []
    decisions=[]
    titles=[w.get('title','') for w in b['work'] if isinstance(w,dict)]
    for choice in choices:
        if isinstance(choice,dict) and choice.get('question'):
            decisions.append(dict(question=choice['question'],affects=choice.get('affects',titles),reason=choice.get('reason') or '执行前需用户明确的业务取舍'))
        else:
            note=choice if isinstance(choice,str) else '：'.join(str(choice[k]) for k in ('title','detail','description','reason') if choice.get(k)) if isinstance(choice,dict) else str(choice)
            if note.strip():
                if '?' in note or '？' in note or '是否' in note:pending.append(note)
                else:b.setdefault('constraints',[]).append('规划说明：'+note)
    for question in pending:
        if not isinstance(question,str) or not question.strip():raise ValueError('questions_for_user 填写实际需要用户决定的问题')
        decisions.append(dict(question=question,affects=titles,reason='执行前需用户明确的业务取舍'))
    b['decisions']=decisions
    for i,w in enumerate(b['work']):
        if not isinstance(w,dict):raise ValueError('work[%s] 需要对象'%i)
        w['after']=as_list(w.get('after',[]));w['deliverables']=as_list(w.get('deliverables',[]))
        for deliverable in w['deliverables']:
            if isinstance(deliverable,dict):deliverable['criteria']=as_list(deliverable.get('criteria',[]))
        if any(k in w for k in ('coverage','missing_methods')):raise ValueError('新版每个 questions 条目内填写 methods；移除旧 coverage / missing_methods，问题只写一次。')
        items=as_list(w.get('questions'));questions=[];coverage=[];gaps=[]
        if not isinstance(items,list) or not items:raise ValueError('work[%s].questions 至少包含一个问题记录'%i)
        for j,q in enumerate(items):
            at='work[%s].questions[%s]'%(i,j)
            if not isinstance(q,dict):raise ValueError(at+' 使用 {question, methods, limits} 对象')
            extra=set(q)-{'question','methods','limits'}
            if extra:raise ValueError(at+' 不支持 '+', '.join(sorted(extra)))
            question=q.get('question','')
            if not isinstance(question,str) or not question.strip():raise ValueError(at+'.question 填写本次问题')
            if question in questions:raise ValueError(at+' 重复；同一问题的多个方法合并到 methods')
            questions.append(question)
            methods=as_list(q.get('methods',[]));limits=as_list(q.get('limits',[]))
            if not isinstance(methods,list):raise ValueError(at+'.methods 使用列表')
            if not isinstance(limits,list) or any(not isinstance(x,str) for x in limits):raise ValueError(at+'.limits 使用材料或适用条件文本列表')
            b.setdefault('constraints',[]).extend(question+'：'+x for x in limits if x.strip())
            for method in methods:
                if not isinstance(method,dict) or set(method)-{'section','application','inputs'}:raise ValueError(at+'.methods 使用 {section, application, inputs}')
                coverage.append(dict(method,question=question))
            if not methods and w.get('purpose','core')!='basic':gaps.append(dict(question=question,required_method='尚无已核读的专业方法对应此问题'))
        w.update(questions=questions,coverage=coverage,missing_methods=gaps)
    # Suggestions are visible to users but never inserted as blocking work.
    return b,suggestions
