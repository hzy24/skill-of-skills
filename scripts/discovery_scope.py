"""Task concepts for recall. Never split an English term into unrelated words.

The host maps everyday language to professional concepts; this module preserves
that mapping and checks source evidence, rather than pretending to grade meaning.
"""
import re

GENERIC_EN={'analysis','analytics','analyze','analyse','data','business','management',
 'report','reports','skill','skills','expert','professional','service','services',
 'operations','quality','system','tool','tools','of','and','the'}
GENERIC_ZH={'分析','数据','管理','报告','业务','经营','专业','技能','方法','质量','服务','系统','平台','工作','工具','任务'}

class QueryConceptError(ValueError):
    pass

def atomic_queries(queries):
    """Separate syntax, not guessed synonyms. Never send sentences to recall.

    Semantic mapping remains the host's job. A failed local preflight consumes
    no request/round and gives a single, small correction instead of junk hits.
    """
    groups=[]
    for q in queries:
        chunks=re.split(r'[\s,，、;；/|：:。！？]+|以及|并且|与|及|中的|(?<=[账表据料录库])中|的',q.strip())
        group=[]
        for term in chunks:
            if not term or term in GENERIC_ZH:continue
            # Remove an action tail only when the remaining concept is useful.
            short=re.sub(r'(?:合理性分析|数据分析|质量分析|分析|评估|检测|优化)$','',term)
            if len(short)>=2 and short not in GENERIC_ZH:term=short
            if not re.search('[\u4e00-\u9fff]',term) or not 2<=len(term)<=8:
                raise QueryConceptError('将检索词改为 2–8 字的中文业务对象或专业岗位，每项一个概念；任务中的关系与要求保留在原始目标。')
            if term not in group:group.append(term)
        groups.append(group)
    explicit=[]
    for i in range(max([len(g) for g in groups],default=0)):
        for g in groups:
            if i<len(g) and g[i] not in explicit:explicit.append(g[i])
    if not explicit:raise QueryConceptError('提供中文业务对象或专业岗位；分析、数据、报告不能单独作为检索词。')
    return explicit[:4]

def query_plan(queries,preserve_phrases=False,atomic=False):
    """Split accidentally combined concepts; pair precise terms with short recall.

    Do not invent domain synonyms or search English fragments. Aliases are the
    host's semantic judgement. The four-request cap is shared with the cache.
    """
    if atomic:return atomic_queries(queries)
    if preserve_phrases:
        # The market API treats a conjunction as a literal term and may return
        # popular recommendations. Recall atomic concepts from every query
        # before adding shortened variants; retain relationships in the goal.
        groups=[[t for t in re.split(r'[\s,，、;；/|]+',q.strip()) if t and t not in GENERIC_ZH] for q in queries]
        explicit=[]
        for i in range(max([len(g) for g in groups],default=0)):
            for g in groups:
                if i<len(g) and g[i] not in explicit:explicit.append(g[i])
        if not explicit:raise ValueError('每轮提供中文专业概念或短问题')
        for q in explicit:
            if not re.search('[\u4e00-\u9fff]',q) or len(q)>24 or len(q)<2:
                raise ValueError('每个查询使用2–24字中文专业概念')
        shorter=[re.sub(r'(?:数据分析|质量分析|合理性分析|分析|管理|评估|检测|策略|优化)$','',q) for q in explicit]
        return list(dict.fromkeys(explicit+[q for q in shorter if len(q)>=2 and q not in GENERIC_ZH]))[:4]
    concepts=[]
    for query in queries:
        for term in re.split(r'[\s,，、;；/|]+',query.strip()):
            if re.search('[\u4e00-\u9fff]',term) and 2<=len(term)<=24 and term not in GENERIC_ZH:
                concepts.append(term)
    result=[]
    for term in dict.fromkeys(concepts):
        result.append(term)
        shortened=re.sub(r'(?:数据分析|质量分析|合理性分析|分析|管理|评估|检测|策略|优化)$','',term)
        if len(shortened)>=2 and shortened not in GENERIC_ZH:result.append(shortened)
    result=list(dict.fromkeys(result))[:4]
    if not result:raise ValueError('检索使用中文业务对象、专业领域或岗位名，每项 2–24 字')
    return result

def concept_scope(goal,queries,previous=None):
    aliases=list(dict.fromkeys((previous or {}).get('queries',[])+list(queries)))
    return dict(focus=goal,request=goal,anchors=list(dict.fromkeys(t for q in aliases for t in terms(q))),
                queries=aliases,basis='professional-concepts-for-recall',match_version=3)

def terms(text):
    # Keep meaningful phrases intact; do not generate arbitrary CJK n-grams.
    out=[]
    for token in re.findall(r'[a-zA-Z][a-zA-Z0-9_ -]*|[\u4e00-\u9fff]+',text.lower()):
        token=' '.join(token.strip().split())
        if len(token)>1 and token not in GENERIC_EN|GENERIC_ZH:out.append(token)
    return list(dict.fromkeys(out))

def hits(text,anchors):
    text=text.lower();result=[]
    for term in anchors:
        found=term in text if re.search('[\u4e00-\u9fff]',term) else re.search(r'(?<![a-z0-9])'+re.escape(term)+r'(?:s|es)?(?![a-z0-9])',text)
        if found:result.append(term)
    return result

def chinese_queries(queries,focus):
    """Tencent search is Chinese-first; old mixed commands drop English safely."""
    selected=list(dict.fromkeys(q.strip() for q in queries if re.search('[\u4e00-\u9fff]',q)))
    if not selected and focus and re.search('[\u4e00-\u9fff]',focus):selected=[focus.strip()]
    if not selected:raise ValueError('腾讯检索填写中文专业概念，例：人力资源、组织设计、管理幅度；保留原始 focus')
    if len(selected)>4 or any(len(q)>24 or q in GENERIC_ZH for q in selected):
        raise ValueError('每轮提供 1–4 个中文专业概念，每个不超过24字；避免单独使用分析、管理等通用词')
    return selected

def create(goal,focus,queries):
    if not isinstance(focus,str) or focus.strip() not in goal or len(focus.strip())<2:
        raise ValueError('--focus 填用户原话中的业务对象，检索词可使用对应的中文专业概念')
    focus=focus.strip()
    if focus.lower() in GENERIC_EN or focus in GENERIC_ZH:
        raise ValueError('--focus 需要具体业务对象；分析、管理、报告等通用动作不能作为专业定位')
    # Aliases may be professional terms absent from the user's everyday wording.
    anchors=list(dict.fromkeys(terms(focus)+[t for q in queries for t in terms(q)]))
    if not anchors:raise ValueError('用具体专业概念检索')
    return dict(focus=focus,request=goal,anchors=anchors,queries=list(queries),basis='user-object-to-professional-concepts',match_version=2)

def match(scope,text):
    # Old saved tasks remain readable, including their original evidence terms.
    found=hits(text,scope['anchors'])
    for other in scope.get('additional',[]):found+=hits(text,other['anchors'])
    return dict(matched=bool(found),anchors=list(dict.fromkeys(found)))

def candidate_text(c):
    return '\n'.join(str(c.get(k) or '') for k in ('slug','name','description','description_zh'))

def filter_results(result,scope):
    kept=[];removed=[]
    for c in result['candidates']:
        evidence=match(scope,candidate_text(c))
        if evidence['matched'] or scope.get('match_version')==3:
            evidence['request_terms']=hits(candidate_text(c),terms(scope.get('focus','')))
            kept.append(dict(c,task_match=evidence))
        else:removed.append(dict(slug=c['slug'],reason='用途未出现本次中文专业概念或完整专业短语'))
    return dict(result,candidates=kept,scope=scope,excluded=removed)

def source_issue(scope,identity,sections):
    if not scope:return None
    # v3 concepts rank recall, not professional sufficiency. English sources,
    # synonyms and supporting chapters need not repeat the Chinese search word.
    # Actual source identity, provenance and role checks remain mandatory.
    if scope.get('match_version')==3:return None
    body='\n'.join(x.get('text',x.get('excerpt',''))+' '+x.get('title','') for x in sections)
    profiles=[{k:v for k,v in scope.items() if k!='additional'}]+scope.get('additional',[])
    for p in profiles:p['anchors']=p['anchors']+scope.get('source_aliases',[])
    if not any(match(p,body)['matched'] for p in profiles):
        return '所选原文章节未涉及“'+scope['focus']+'”对应的专业概念；换用对应章节或候选。'
    return None
