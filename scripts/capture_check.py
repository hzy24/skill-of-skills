#!/usr/bin/env python3
"""Capture an explicitly selected validator; no shell, discovery, installation or approval."""
import argparse,json,math,subprocess,sys
from pathlib import Path
from datetime import datetime,timezone
from skill_runtime import sha

def capture(artifact,check_id,source,argv,cwd,timeout=120):
    if not math.isfinite(timeout) or timeout<=0: raise ValueError('timeout 需要有限正数')
    path=Path(artifact).resolve();before=sha(path)
    result=dict(schema='sos-native-v1',check_id=check_id,source=source,argv=argv,cwd=str(Path(cwd).resolve()),
                artifact=str(path),artifact_sha256_before=before,started_at=datetime.now(timezone.utc).isoformat())
    try:
        r=subprocess.run(argv,cwd=cwd,capture_output=True,text=True,errors='replace',timeout=timeout,shell=False)
        result.update(exit_code=r.returncode,stdout=r.stdout,stderr=r.stderr,status='pass' if r.returncode==0 else 'fail')
    except subprocess.TimeoutExpired as e:
        def decoded(v):return v.decode('utf-8',errors='replace') if isinstance(v,bytes) else (v or '')
        result.update(exit_code=None,status='timeout',error='验证命令超时',stdout=decoded(e.stdout),stderr=decoded(e.stderr))
    except OSError as e:
        result.update(exit_code=None,status='error',error=str(e))
    result['artifact_sha256']=sha(path) if path.is_file() else None
    if result['artifact_sha256']!=before: result['status']='changed'
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('artifact','check-id','source','out'):p.add_argument('--'+k,required=True)
    p.add_argument('--cwd',default='.');p.add_argument('--timeout',type=float,default=120)
    p.add_argument('argv',nargs=argparse.REMAINDER);a=p.parse_args();argv=a.argv[1:] if a.argv[:1]==['--'] else a.argv
    if not argv or not math.isfinite(a.timeout) or a.timeout<=0:p.error('需要明确验证命令和有限正数 timeout')
    if Path(a.out).resolve()==Path(a.artifact).resolve():p.error('验证记录不能覆盖被检查产物')
    r=capture(a.artifact,a.check_id,a.source,argv,a.cwd,a.timeout)
    Path(a.out).write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':r['status'],'report':str(Path(a.out).resolve())},ensure_ascii=False))
    return 0 if r['status']=='pass' else 1
if __name__=='__main__':
    try:sys.exit(main())
    except (OSError,ValueError) as e:print(str(e),file=sys.stderr);sys.exit(2)
