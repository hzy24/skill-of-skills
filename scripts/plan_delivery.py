#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prepare connected plan attachments; host delivery is a separate, explicit step."""
import argparse,json,os,shlex,subprocess,sys,time,threading
from pathlib import Path
import sos
from plan_io import edit_lock
from plan_status import assess

_services=[]

def paths(plan):
    plan=Path(plan).resolve()
    return plan,plan.with_suffix('.html'),plan.parent/'.plan-server.json'

def prepare(plan,timeout=5):
    from service_status import status
    _services[:]=[p for p in _services if p.poll() is None]
    plan,html,meta=paths(plan);p=sos.read(plan);sos.require_plan(p)
    protected={(Path(m['path']) if Path(m['path']).is_absolute() else plan.parent/m['path']).resolve() for m in p['materials']}
    if html in protected or meta in protected:raise ValueError('交付路径与输入材料冲突，请使用独立任务目录')
    log=plan.parent/'.sos-delivery.log'
    if log in protected:raise ValueError('服务日志路径与输入材料冲突')
    with edit_lock(plan.parent/'.sos-delivery-start'):
        service=None
        if meta.exists():
            state=sos.read(meta)
            if Path(state['plan']).resolve()!=plan or Path(state['html']).resolve()!=html:raise ValueError('保存服务属于其他方案，保留原文件并使用独立任务目录')
            try:service=status(meta)
            except (OSError,ValueError):pass
        if service is None:
            with log.open('ab') as stream:
                proc=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'serve',str(plan)],stdin=subprocess.DEVNULL,stdout=stream,stderr=stream,start_new_session=True)
            _services.append(proc)
            end=time.monotonic()+timeout
            while time.monotonic()<end:
                try:
                    if meta.exists():service=status(meta);break
                except (OSError,ValueError,KeyError):pass
                if proc.poll() is not None:break
                time.sleep(.05)
            if service is None:
                return dict(status='delivery_setup_failed',plan=str(plan),error='保存服务未就绪',log=str(log),next='读取该日志修复实际错误，再运行同一 prepare 命令；保留现有 plan.json，不重新规划。')
        # Refresh after review/revision, preserving the running bridge and canonical file.
        from plan_server import PlanStore
        state=sos.read(meta);store=PlanStore(plan,html,meta);store.token=state['token'];store.endpoint=state['endpoint']
        from plan_server import atomic_write
        with edit_lock(plan):atomic_write(html,store.render_html(sos.read(plan)))
    return dict(status='awaiting_attachment_delivery',plan_readiness=assess(sos.read(plan)),
                delivery_files=[str(html),str(plan)],execution_plan=str(plan),
                next_tool={'name':'PresentToUser','arguments':{'filepaths':[str(html),str(plan)]}},
                receipt_command=shlex.join([sys.executable,str(Path(__file__).resolve()),'confirm',str(plan),'--receipt',str(plan.parent/'present-result.txt')]),
                next='现在调用 next_tool 交付两个文件；将工具原始返回保存到 present-result.txt，再运行 receipt_command。尚未交付，先不要结束规划回复。')

def serve(plan):
    from plan_server import PlanStore,PlanServer
    plan,html,meta=paths(plan)
    with PlanServer(PlanStore(plan,html,meta)) as server:
        def watch():
            while plan.exists():time.sleep(1)
            server.shutdown()
        threading.Thread(target=watch,daemon=True).start()
        server.serve_forever()

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('action',choices=['prepare','confirm','serve']);ap.add_argument('plan');ap.add_argument('--receipt');a=ap.parse_args()
    if a.action=='serve':serve(a.plan);return
    if a.action=='prepare':result=prepare(a.plan)
    else:
        if not a.receipt:ap.error('confirm 需要 --receipt，保存 PresentToUser 原始结果，不重新组织格式')
        from handoff import record
        plan,html,_=paths(a.plan);result=record(plan,html,a.receipt)
        result['plan_readiness']=assess(sos.read(plan))
    print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':
    try:main()
    except (ValueError,KeyError,TypeError,OSError) as e:raise SystemExit(str(e))
