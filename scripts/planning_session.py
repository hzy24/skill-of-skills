"""Keep a planning request attached to one directory across host retries.

Yuanjing exposes /sessions/<conversation>. Outside that host, identical input
files share a registry in their common workspace. This is durable coordination,
not a sandbox against an agent deliberately editing the registry.
"""
import hashlib,json,os
from pathlib import Path
from acquire import write,digest
from plan_io import edit_lock

LINK='.sos-task-link.json'

def session_of(path):
    parts=Path(path).resolve().parts
    if 'sessions' in parts:
        i=parts.index('sessions')
        if len(parts)>i+1:return Path(*parts[:i+2])

def protected(path):
    path=Path(path).resolve()
    installed=Path(__file__).resolve().parents[1]
    if path==installed or installed in path.parents:return True
    if path.is_relative_to(Path('/mnt/skills')):return True
    return any((p/'SKILL.md').is_file() for p in (path,*path.parents))

def active_session(inputs=()):
    sessions={s for p in (Path.cwd(),*inputs) for s in [session_of(p)] if s}
    if len(sessions)>1:raise ValueError('输入来自多个会话；使用本次会话的附件副本')
    return next(iter(sessions),None)

def task_root(root,inputs=()):
    """Route shared/output paths before reading links or creating any lock/file."""
    root=Path(root).resolve();owner=active_session(inputs);given=session_of(root)
    if owner and given and owner!=given:raise ValueError('任务目录属于其他会话；使用当前会话的 task_dir')
    if owner and (not given or root==owner or protected(root)):
        return owner/'sos-task'
    if protected(root):raise ValueError('技能安装目录不能保存任务；在当前会话工作目录运行 init')
    return root

def validate_owner(root,inputs=()):
    root=Path(root).resolve();owner=active_session(inputs) or session_of(root)
    if protected(root):raise ValueError('任务引用指向技能安装目录；保留旧文件，在当前会话建立独立任务')
    if owner and session_of(root)!=owner:raise ValueError('任务引用属于其他会话或共享目录；保留现场')
    state=root/'.sos-flow.json'
    if state.exists():
        data=json.loads(state.read_text());recorded=data.get('owner_session')
        old_inputs=[x['path'] for x in data.get('inputs',[]) if isinstance(x,dict) and x.get('path')]
        if owner and (recorded and recorded!=str(owner) or any(session_of(p) and session_of(p)!=owner for p in old_inputs)):
            raise ValueError('任务状态或输入归属其他会话；保留现场，禁止恢复')
    return root

def resolve(root,inputs=()):
    root=task_root(root,inputs)
    validate_owner(root,inputs)
    link=root/LINK
    if link.exists():
        target=Path(json.loads(link.read_text())['task_dir']).resolve()
        if target==root or (target/LINK).exists():raise ValueError('任务引用形成循环；保留现场')
        # A link cannot change the originating conversation, even from a shell
        # outside /sessions. Check the source directory as well as the cwd.
        if session_of(root) and session_of(target)!=session_of(root):raise ValueError('任务引用跨会话；保留现场')
        return validate_owner(target,inputs)
    return root

def scope(root,inputs,goal):
    paths=[Path(root).resolve(),Path.cwd().resolve(),*[Path(p).resolve() for p in inputs]]
    sessions=set()
    for p in paths:
        parts=p.parts
        if 'sessions' in parts:
            i=parts.index('sessions')
            if len(parts)>i+1:sessions.add(Path(*parts[:i+2]))
    if len(sessions)>1:raise ValueError('输入来自多个会话；使用本次会话的附件副本')
    if sessions:return sessions.pop(),'conversation'
    parents=[p.parent for p in paths[2:]]
    base=Path(os.path.commonpath([str(p) for p in parents])) if parents else paths[0].parent
    if str(base) in ('/','/tmp','/private/tmp'):base=paths[0].parent
    # Method examples may be supplied as inputs. Their package stays read-only;
    # keep the coordination registry beside the task, never beside that source.
    if protected(base):base=paths[0].parent
    # Copies/renames of the same attachments remain the same request. A changed
    # task-directory name or paraphrased goal does not grant a new budget.
    hashes=sorted(hashlib.sha256(p.read_bytes()).hexdigest() for p in paths[2:])
    return base,digest(hashes if hashes else [' '.join(goal.split())])

def claim(root,inputs,goal,new_request=None):
    root=validate_owner(root,inputs);base,key=scope(root,inputs,goal)
    registry=base/'.sos-planning-session.json'
    with edit_lock(registry):
        records=json.loads(registry.read_text()) if registry.exists() else {}
        old=records.get(key)
        if new_request is not None:
            if not isinstance(new_request,str) or len(new_request.strip())<4:
                raise ValueError('新任务需记录用户另行交办的完整原话')
            if old and Path(old['task_dir']).resolve()==root:
                raise ValueError('新任务使用新目录，保留原任务及用户修改')
            records.setdefault('_history',[]).append(dict(key=key,previous=old,new_request=new_request))
            records[key]=dict(task_dir=str(root),original_request=goal,user_new_request=new_request)
            write(registry,records)
            return root
        if old:
            target=Path(old['task_dir']).resolve()
            validate_owner(target,inputs)
            if session_of(root) and session_of(target)!=session_of(root):raise ValueError('原任务登记指向共享或其他会话目录；保留现场，使用新任务目录及用户原话恢复')
            if target!=root:
                if not (target/'.sos-flow.json').is_file():
                    raise ValueError('原规划目录缺失；恢复原目录，不能以重建方式重置规划：'+str(target))
                root.mkdir(parents=True,exist_ok=True)
                write(root/LINK,dict(task_dir=str(target),registry=str(registry)))
                return target
        else:
            records[key]=dict(task_dir=str(root),original_request=goal)
            write(registry,records)
    return root
