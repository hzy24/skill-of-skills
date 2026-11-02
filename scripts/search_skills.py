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
MAX_RESPONSE=512*1024
MAX_REQUESTS=8

def fetch(url,timeout):
    request=Request(url,headers={'User-Agent':'Skill-of-Skills/1.0.1','Accept':'application/json'})
    with build_opener(NoRedirect()).open(request,timeout=timeout) as response:
        data=response.read(MAX_RESPONSE+1)
        if len(data)>MAX_RESPONSE:raise ValueError('搜索响应超过 512 KiB')
        return json.loads(data)

def normalize(payload,query,url):
    if not isinstance(payload,dict) or payload.get('code',0)!=0 or not isinstance(payload.get('data'),dict) or not isinstance(payload['data'].get('skills'),list):
        raise ValueError('SkillHub 返回非预期搜索结构')
    results=[]
    for row in payload['data']['skills'][:10]:
        if not isinstance(row,dict):continue
        slug=row.get('slug')
        if not isinstance(slug,str) or not slug.strip() or len(slug)>200:continue
        candidate={k:row.get(k) for k in ('name','description','description_zh','category','version','downloads','installs','stars','score','labels')}
        for k in ('name','description','description_zh'):
            candidate[k]=str(candidate[k] or '')[:2000]
        candidate.update(slug=slug,source='tencent-skillhub',catalog_url='https://skillhub.cn/skills/'+quote(slug,safe=''),
                         detail_url='https://api.skillhub.cn/api/v1/skills/'+quote(slug,safe=''),matched_queries=[query],search_url=url)
        results.append(candidate)
    return results

def search(task,queries,category=None,reader=fetch):
    queries=list(dict.fromkeys(q.strip() for q in queries))
    if not 1<=len(queries)<=4 or any(not q or len(q)>160 for q in queries):raise ValueError('提供 1–4 个简短的专业方法关键词，每个不超过160字符')
    if category and not re.fullmatch('[a-z-]{1,64}',category):raise ValueError('category 使用平台分类标识')
    task=Path(task).resolve();task.mkdir(parents=True,exist_ok=True)
    draft=task/'draft.json';clock=session_path(draft);cache=task/'.sos-skill-search.json'
    searches=[];candidates={}
    for query in queries:
        params=dict(keyword=query,sortBy='score',order='desc',pageSize=10)
        if category:params['category']=category
        url=ENDPOINT+'?'+urlencode(params)
        # Reserve the request before network I/O; retries never reset the task budget.
        with edit_lock(clock):
            save(clock,session(draft));state=json.loads(cache.read_text()) if cache.exists() else {'requests':{}}
            previous=state['requests'].get(url)
            if previous:
                result=copy.deepcopy(previous);result['cached']=True
            elif status(draft)['stop_discovery'] or len(state['requests'])>=MAX_REQUESTS:
                result=dict(query=query,url=url,status='budget_exhausted',candidates=[])
            else:
                result=dict(query=query,url=url,status='pending',candidates=[])
                state['requests'][url]=result;save(cache,state)
        if result['status']=='pending' and not result.get('cached'):
            began=time.monotonic()
            remaining=max(1,min(15,300-(time.time()-session(draft)['started_epoch'])))
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
            else:candidates[item['slug']]=copy.deepcopy(item)
    ok=sum(x['status']=='searched' for x in searches)
    return dict(status='searched' if ok==len(searches) else 'partial' if ok else 'search_failed',source='tencent-skillhub',
                searches=searches,candidates=list(candidates.values()),
                next='结合用户目标筛选最契合的三个候选，读原文核对专业方法并生成安装提案。零命中时换英文、同义词或上位方法词；结果偏离时收窄领域。复用缓存与剩余预算。搜索结果是候选，平台 score/stars 不是专业适配评分或 GitHub 星数。')

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('queries',nargs='+');ap.add_argument('--task-dir',required=True);ap.add_argument('--category');ap.add_argument('--out',required=True);a=ap.parse_args()
    out=Path(a.out).resolve();task=Path(a.task_dir).resolve()
    if out.exists() or out.name in ('draft.json','plan.json','run.json') or out.name.startswith('.'):
        ap.error('使用新的搜索结果文件名，保留已有方案与记录')
    result=search(task,a.queries,a.category);save(out,result)
    print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
