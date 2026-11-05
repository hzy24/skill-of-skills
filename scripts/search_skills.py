#!/usr/bin/env python3
"""Search Tencent SkillHub's documented public API; persist real results and budgets."""
import argparse, copy, json, re, time
from pathlib import Path
from urllib.parse import urlencode, quote
from urllib.request import build_opener, Request
from urllib.error import URLError
from acquire import NoRedirect
from plan_io import edit_lock
from planning_budget import session, session_path, status
from sos import save

ENDPOINT='https://api.skillhub.cn/api/skills'
SEARCH_ENDPOINT='https://api.skillhub.cn/api/v1/search'
MAX_RESPONSE=2*1024*1024
PAGE_SIZE=100
MAX_REQUESTS=8

def fetch(url,timeout):
    request=Request(url,headers={'User-Agent':'Skill-of-Skills/1.0.1','Accept':'application/json'})
    with build_opener(NoRedirect()).open(request,timeout=timeout) as response:
        data=response.read(MAX_RESPONSE+1)
        if len(data)>MAX_RESPONSE:raise ValueError('搜索响应超过 2 MiB')
        return json.loads(data)

def normalize(payload,query,url):
    semantic=url.startswith(SEARCH_ENDPOINT+'?')
    rows=payload.get('results') if semantic and isinstance(payload,dict) else payload.get('data',{}).get('skills') if isinstance(payload,dict) and isinstance(payload.get('data'),dict) else None
    if not isinstance(payload,dict) or payload.get('code',0)!=0 or not isinstance(rows,list):
        raise ValueError('SkillHub 返回非预期搜索结构')
    results=[]
    for rank,row in enumerate(rows[:PAGE_SIZE],1):
        if not isinstance(row,dict):continue
        slug=row.get('slug')
        if not isinstance(slug,str) or not slug.strip() or len(slug)>200:continue
        candidate={k:row.get(k) for k in ('name','description','description_zh','category','version','downloads','installs','stars','score','labels')}
        candidate['name']=candidate['name'] or row.get('displayName')
        candidate['description']=candidate['description'] or row.get('summary')
        candidate['score_kind']='search_score_not_quality' if semantic else 'catalog_score'
        for k in ('name','description','description_zh'):
            candidate[k]=str(candidate[k] or '')[:2000]
        candidate.update(slug=slug,source='tencent-skillhub',catalog_url='https://skillhub.cn/skills/'+quote(slug,safe=''),
                         detail_url='https://api.skillhub.cn/api/v1/skills/'+quote(slug,safe=''),matched_queries=[query],query_ranks={query:rank},search_url=url)
        results.append(candidate)
    return results

def search(task,queries,category=None,reader=fetch):
    queries=list(dict.fromkeys(q.strip() for q in queries))
    if not 1<=len(queries)<=4 or any(not q or len(q)>160 for q in queries):raise ValueError('提供 1–4 个简短的专业方法关键词，每个不超过160字符')
    if category and not re.fullmatch('[a-z-]{1,64}',category):raise ValueError('category 使用平台分类标识')
    task=Path(task).resolve();task.mkdir(parents=True,exist_ok=True)
    draft=task/'draft.json';clock=session_path(draft);cache=task/'.sos-skill-search.json'
    controller=task/'.sos-flow.json'
    state=json.loads(controller.read_text()) if controller.exists() else {}
    contract=state.get('authoring_contract',0)
    max_requests=16 if contract>=13 and state.get('method_search_used') else 12 if contract>=7 else MAX_REQUESTS
    searches=[];candidates={}
    for query in queries:
        if contract>=7:
            # Search ranks relevance before market popularity. category is a
            # local preference: the v1 endpoint does not document a category
            # filter, and a specialist can be published under another category.
            url=SEARCH_ENDPOINT+'?'+urlencode(dict(q=query,limit=50))
        else:
            params=dict(keyword=query,sortBy='score',order='desc',pageSize=PAGE_SIZE)
            if category:params['category']=category
            url=ENDPOINT+'?'+urlencode(params)
        # Reserve the request before network I/O; retries never reset the task budget.
        with edit_lock(clock):
            save(clock,session(draft));state=json.loads(cache.read_text()) if cache.exists() else {'requests':{}}
            previous=state['requests'].get(url)
            if previous:
                result=copy.deepcopy(previous);result['cached']=True
            elif status(draft)['stop_discovery'] or len(state['requests'])>=max_requests:
                result=dict(query=query,url=url,status='budget_exhausted',candidates=[])
            else:
                result=dict(query=query,url=url,status='pending',candidates=[])
                state['requests'][url]=result;save(cache,state)
        if result['status']=='pending' and not result.get('cached'):
            began=time.monotonic()
            remaining=15 if status(draft).get('budget_kind')=='bounded-actions' else max(1,min(15,300-(time.time()-session(draft)['started_epoch'])))
            try:
                payload=reader(url,remaining)
                result.update(status='searched',candidates=normalize(payload,query,url))
            except (OSError,ValueError,URLError) as e:
                result.update(status='error',error=str(e)[:500])
            result['elapsed_seconds']=round(time.monotonic()-began,3)
            with edit_lock(clock):
                state=json.loads(cache.read_text());state['requests'][url]=result;save(cache,state)
        searches.append({k:v for k,v in result.items() if k!='candidates'})
        for item in result.get('candidates',[]):
            if item['slug'] in candidates:
                current=candidates[item['slug']]['matched_queries']
                if query not in current:current.append(query)
                candidates[item['slug']].setdefault('query_ranks',{}).update(item.get('query_ranks',{}))
            else:candidates[item['slug']]=copy.deepcopy(item)
    current_slugs=set(candidates)
    # Preserve earlier useful hits even when the final query returns nothing or exhausts budget.
    state=json.loads(cache.read_text()) if cache.exists() else {'requests':{}}
    for previous in state['requests'].values():
        for item in previous.get('candidates',[]):
            candidates.setdefault(item['slug'],copy.deepcopy(item))
    # Keep conflicts visible instead of joining unrelated metadata under one slug.
    identities={};conflicts=set()
    for previous in state['requests'].values():
        for item in previous.get('candidates',[]):
            identity=(item['name'],item['description'],item['description_zh'])
            old=identities.setdefault(item['slug'],identity)
            if old!=identity:conflicts.add(item['slug'])
    for slug in conflicts:candidates.pop(slug,None)
    if contract>=8:
        for slug,c in candidates.items():c['current_round']=slug in current_slugs
    stopped=status(draft)['stop_discovery'] or len(state['requests'])>=max_requests
    ok=sum(x['status']=='searched' for x in searches)
    return dict(status='searched' if ok==len(searches) else 'partial' if ok else 'search_failed',source='tencent-skillhub',
                searches=searches,candidates=list(candidates.values()),identity_conflicts=sorted(conflicts),stop_discovery=stopped,requests_used=len(state['requests']),
                category_preference=category if contract>=7 else None,
                ranking_version=2 if contract>=8 else 1,current_queries=queries,
                next=('检索预算已结束；评估累计候选和已读方法。能力契合标准保持不变，不因预算用完改选通用能力。' if stopped and contract>=7 else '检索预算已结束；使用本次累计候选和已读方法完成选型并交付方案。不要换输出文件名重试检索。' if stopped else '结合用户目标筛选最契合的三个候选，读原文核对专业方法并生成安装提案。零命中时换中文同义词；结果偏离时收窄业务问题。搜索接口 score 只用于检索，不代表质量评分；下载量与 stars 保留平台含义。'))

def summary(result,out):
    def relevance(c,q):
        title=(c.get('name') or '').lower();description=(c.get('description_zh') or c.get('description') or '').lower();q=q.lower()
        terms=re.findall(r'[a-z0-9]{3,}|[\u4e00-\u9fff]+',q)
        return (len(c.get('task_match',{}).get('request_terms',[])),int(q in title),sum(t in title for t in terms),int(q in description),sum(t in description for t in terms))
    # Round-robin the query groups so a noisy first query cannot hide the second.
    queries=list(dict.fromkeys(q for c in result['candidates'] for q in c.get('matched_queries',[])))
    groups=[sorted([c for c in result['candidates'] if q in c.get('matched_queries',[])],key=lambda c:relevance(c,q),reverse=True) for q in queries]
    ranked=[];seen=set()
    for index in range(max([len(g) for g in groups],default=0)):
        for group in groups:
            if index<len(group) and group[index]['slug'] not in seen:
                ranked.append(group[index]);seen.add(group[index]['slug'])
    if result.get('ranking_version')==2:
        # Semantic API ranks per current query are retained. Historical object
        # keywords cannot override a refined query's business relationship.
        current=result.get('current_queries',[])
        from discovery_scope import hits,terms
        def evidence(c,q):
            anchors=terms(q);title=(c.get('name') or '')+' '+c['slug']
            desc=(c.get('description_zh') or c.get('description') or '')
            return (bool(hits(title,anchors)),bool(hits(desc,anchors)))
        groups=[sorted([c for c in result['candidates'] if c.get('current_round') and q in c.get('matched_queries',[])],
            key=lambda c:(*evidence(c,q),bool(result.get('category_preference') and c.get('category')==result['category_preference']),-c.get('query_ranks',{}).get(q,10000)),reverse=True) for q in current]
        ranked=[];seen=set()
        # Relevant matches across all active queries precede market suggestions.
        for tier in (2,1,0):
            filtered=[[c for c in g if (2 if evidence(c,q)[0] else 1 if evidence(c,q)[1] else 0)==tier] for q,g in zip(current,groups)]
            for i in range(max([len(g) for g in filtered],default=0)):
                for g in filtered:
                    if i<len(g) and g[i]['slug'] not in seen:ranked.append(g[i]);seen.add(g[i]['slug'])
        ranked += [c for c in result['candidates'] if c['slug'] not in seen]
        for c in ranked:
            c['query_evidence']=list(dict.fromkeys(t for q in current for t in hits(
                (c.get('name') or '')+' '+(c.get('description_zh') or c.get('description') or ''),terms(q))))
    elif result.get('scope',{}).get('match_version')==3:
        anchors=result['scope']['anchors']
        from discovery_scope import hits
        goal=result['scope'].get('request','')
        primary=[a for a in anchors if a in goal] or anchors[:1]
        if primary:primary=[a for a in primary if len(a)==max(map(len,primary))]
        actions=[a for a in ('分析','审核','审计','诊断','设计','编制','比较','评估','统计','筛查') if a in goal]
        def task_rank(c):
            title=(c.get('name') or '')+' '+c['slug']
            description=(c.get('description_zh') or c.get('description') or '')
            title_hits=hits(title,anchors);description_hits=hits(description,anchors)
            primary_title=bool(hits(title,primary));primary_desc=bool(hits(description,primary))
            action_match=bool(hits(title+' '+description,actions))
            # Lexical relevance orders inspection, never marks semantic fitness.
            return (primary_title and action_match,primary_title,primary_desc and action_match,primary_desc,
                    bool(result.get('category_preference') and c.get('category')==result['category_preference']),
                    bool(title_hits),len(title_hits),bool(description_hits),len(description_hits),len(c.get('matched_queries',[])))
        ranked.sort(key=task_rank,reverse=True)
    rows=[]
    for c in ranked[:12]:
        rows.append(dict(name=c['name'],slug=c['slug'],description=(c.get('description_zh') or c.get('description') or '')[:180],category=c.get('category'),downloads=c.get('downloads'),score=c.get('score'),score_kind=c.get('score_kind','catalog_score'),labels=c.get('labels'),catalog_url=c['catalog_url']))
        if c.get('task_match'):rows[-1]['matched_task_terms']=c['task_match']
        if result.get('ranking_version')==2:rows[-1].update(current_round=c.get('current_round',False),matched_queries=c.get('matched_queries',[]),query_evidence=c.get('query_evidence',[]),recall_basis='query_match' if c.get('query_evidence') else 'market_suggestion_needs_review')
    from discovery_scope import hits,terms
    unmatched=[q for q in result.get('current_queries',[]) if not any(c.get('current_round') and q in c.get('matched_queries',[]) and hits((c.get('name') or '')+' '+(c.get('description_zh') or c.get('description') or ''),terms(q)) for c in ranked)]
    next_action=result['next']
    if unmatched:next_action+='；以下概念未出现直接用途命中：'+'、'.join(unmatched)+'。不要把其他词返回的热门候选当成这些概念的专业覆盖；核读匹配项，必要时换该概念的短同义词。'
    return dict(status=result['status'],results_file=str(out),candidate_count=len(result['candidates']),candidates=rows,
                current_candidate_count=sum(c.get('current_round',True) for c in result['candidates']),
                query_matched_count=sum(bool(c.get('query_evidence')) and c.get('current_round',False) for c in ranked),
                current_queries=result.get('current_queries',[]),unmatched_queries=unmatched,searches=result['searches'],stop_discovery=result['stop_discovery'],requests_used=result['requests_used'],next=next_action)

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('queries',nargs='+');ap.add_argument('--task-dir',required=True);ap.add_argument('--category');ap.add_argument('--out',required=True);a=ap.parse_args()
    out=Path(a.out).resolve();task=Path(a.task_dir).resolve()
    if out.exists() or out.name in ('draft.json','plan.json','run.json') or out.name.startswith('.'):
        ap.error('使用新的搜索结果文件名，保留已有方案与记录')
    result=search(task,a.queries,a.category);save(out,result)
    print(json.dumps(summary(result,out),ensure_ascii=False))
if __name__=='__main__':main()
