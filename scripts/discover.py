#!/usr/bin/env python3
"""Build bounded discovery requests for host tools. No fabricated search results."""
import argparse,json
from pathlib import Path
# Claude SkillHub and Yuanjing market discovery are paused for the current release.
CHANNELS=('tencent-skillhub',)

def discovery_plan(queries,sources=CHANNELS):
    queries=list(dict.fromkeys(q.strip() for q in queries))
    if not 1<=len(queries)<=3 or any(not q for q in queries):raise ValueError('提供1–3个业务方法关键词')
    if not sources or any(s not in CHANNELS for s in sources):raise ValueError('本版只从腾讯 SkillHub（skillhub.cn）发现新能力')
    return dict(status='host_search_required',searches=[dict(source='tencent-skillhub',query=q,tool='search_skills.py',status='not_run') for q in queries],candidates=[],reading_limit=3,query_revision_limit=1,source_fetch_attempt_limit=2,source_fetch_timeout_seconds=60,
                next='运行 search_skills.py <查询词...> --task-dir <当前任务目录> --out <新搜索文件>，实际搜索腾讯官方API；按任务契合度优先、评分和下载量辅助筛选，再用 acquire.py inspect-tencent 读取原文和安装提案。')

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('query',nargs='?');ap.add_argument('--draft',help='从业务草案的 mapping 生成能力检索请求');ap.add_argument('--task-dir',help='手工关键词使用的任务目录，默认输出文件所在目录');ap.add_argument('--also',action='append',default=[])
    ap.add_argument('--source',choices=CHANNELS,default='tencent-skillhub');ap.add_argument('--out',required=True);a=ap.parse_args()
    try:
        if a.draft:
            if a.query or a.also:raise ValueError('--draft 与手工 query 分开使用')
            d=json.loads(Path(a.draft).read_text());m=d.get('mapping',{})
            if not all(isinstance(d.get(k),str) and d[k].strip() for k in ('title','goal')):raise ValueError('先填写真实 title、goal 和 mapping，再生成检索请求；空白骨架不能用于检索')
            if not all(isinstance(m.get(k),str) and m[k].strip() for k in ('domain','action','input_condition')):raise ValueError('mapping 需要业务领域、工作动作和输入条件')
            capabilities=m.get('capabilities')
            if not isinstance(capabilities,list) or not capabilities or any(not isinstance(x,str) or not x.strip() for x in capabilities):raise ValueError('mapping.capabilities 需要能力关键词列表')
            queries=[m['domain']+' '+x for x in capabilities[:3]]
        else:queries=([a.query] if a.query else [])+a.also
        r=discovery_plan(queries,[a.source])
        if a.draft:r['task_mapping']=m
        from planning_budget import status,session,session_path
        from plan_io import edit_lock
        import sos
        output=Path(a.out).resolve();output.parent.mkdir(parents=True,exist_ok=True)
        task=Path(a.draft).resolve() if a.draft else (Path(a.task_dir).resolve() if a.task_dir else output.parent)/'draft.json'
        if a.draft and a.task_dir and Path(a.task_dir).resolve()!=task.parent:raise ValueError('--draft 与 --task-dir 需属于同一任务目录')
        if output in (task,session_path(task).resolve()):raise ValueError('检索输出不能覆盖业务草案或规划记录')
        task.parent.mkdir(parents=True,exist_ok=True)
        with edit_lock(session_path(task)):
            state=session(task);sos.save(session_path(task),state)
            r['budget']=status(task)
            previous=state.setdefault('discovery_requests',[])
            key=sos.digest(r['searches']);cached=next((v for v in previous if v['key']==key),None)
            if r['budget']['stop_discovery']:
                r.update(status='planning_budget_exhausted',searches=[],next=r['budget']['next'])
            elif cached:
                r.update(status='reuse_request',searches=[],previous_request=cached['path'],next='复用该轮检索记录；仅请求生成过，不能据此声称已经搜索。')
            elif len(previous)>=2:
                r.update(status='discovery_rounds_exhausted',searches=[],next='两轮检索请求已生成；停止扩大搜索，依据实际取得的原文编译或说明能力缺口。')
            else:
                previous.append(dict(key=key,path=str(output)));sos.save(session_path(task),state)
    except ValueError as e:ap.error(str(e))
    if r.get('previous_request')!=str(Path(a.out).resolve()):Path(a.out).write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(r,ensure_ascii=False))
if __name__=='__main__':main()
