#!/usr/bin/env python3
"""Record observed planning cost. Context occupancy is not billable token usage."""
import argparse,json,time
from pathlib import Path

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('action',choices=['start','finish']);ap.add_argument('file');ap.add_argument('--context-used',type=int);ap.add_argument('--tool-calls',type=int);ap.add_argument('--early-execution',help='Observed work done before confirmation');a=ap.parse_args();path=Path(a.file)
    if any(x is not None and x<0 for x in (a.context_used,a.tool_calls)):ap.error('计数不能为负数')
    if a.action=='start':
        if path.exists():ap.error('记录已存在，请使用新路径')
        data={'started_at_epoch':time.time(),'context_start':a.context_used,'measurement':'host_observed','note':'上下文占用增量受压缩影响，不等于生成或计费 token'}
    else:
        data=json.loads(path.read_text())
        if 'finished_at_epoch' in data:ap.error('本次记录已经结束')
        data.update(finished_at_epoch=time.time(),context_end=a.context_used,tool_calls=a.tool_calls,early_execution=a.early_execution)
        data['elapsed_seconds']=round(data['finished_at_epoch']-data['started_at_epoch'],3)
        data['context_occupancy_delta']=a.context_used-data['context_start'] if a.context_used is not None and data['context_start'] is not None else None
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2));print(json.dumps(data,ensure_ascii=False))
if __name__=='__main__':main()
