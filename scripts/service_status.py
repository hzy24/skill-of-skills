#!/usr/bin/env python3
"""Check this task's live saving connection without exposing its credential."""
import argparse,json,sys
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import urlsplit
import sos
from plan_status import assess

def status(meta):
    state=sos.read(meta);endpoint=state['endpoint'];u=urlsplit(endpoint)
    if u.scheme!='http' or u.hostname!='127.0.0.1' or u.path!='/plan' or u.username or u.password or u.query or u.fragment:
        raise ValueError('保存服务地址须为本机回环 /plan')
    with urlopen(Request(endpoint,headers={'X-Skill-Of-Skills-Token':state['token']}),timeout=3) as response:
        remote=json.load(response)
    plan=sos.read(state['plan']);sos.require_plan(plan)
    if remote.get('hash')!=sos.digest(plan) or remote.get('plan')!=plan:raise ValueError('服务与磁盘版本不一致')
    if not Path(state['html']).is_file():raise ValueError('plan.html 尚未生成，不能交付')
    readiness=assess(plan)
    return {'ready':True,'plan_readiness':readiness,'revision':plan['revision'],'plan':state['plan'],'html':state['html'],
            'delivery_files':[state['html'],state['plan']],
            'execution_plan':state['plan'],
            'next':readiness['message']+' 用 PresentToUser 同时交付 delivery_files 中的两个文件；核对工具回执含 plan.html 和 plan.json。保存实际回执后运行 handoff.py record 登记交付，结束规划回复等待用户确认。执行时读取 execution_plan 最新版本。'}

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('meta');a=ap.parse_args()
    print(json.dumps(status(a.meta),ensure_ascii=False))
if __name__=='__main__':
    try:main()
    except (ValueError,KeyError,TypeError,OSError) as e:
        print(json.dumps({'ready':False,'error':str(e)},ensure_ascii=False));sys.exit(2)
