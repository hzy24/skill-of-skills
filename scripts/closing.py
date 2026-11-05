"""Program-owned end-of-turn replies. A prepared reply is not a sent message.

Hosts may dispatch final_reply directly. Skills running through a general shell
cannot suppress a subsequent model message; observed chat must be audited.
"""
import hashlib,json
from pathlib import Path

SCHEMA='sos-terminal-v1'
FILE='.sos-terminal.json'
FAILED='本轮方案未完成，尚未开始执行。已保留材料、检索结果和问题记录，供修复后继续。'
BLOCKED='规划附件交付未完成，当前不启动执行。方案和交付记录已保留，供恢复交付。'

def digest(text):return hashlib.sha256(text.encode('utf-8')).hexdigest()

def envelope(phase,message,plan_hash=None,revision=None):
    if phase not in ('planning_failed','delivery_blocked','delivered'):raise ValueError('收尾需要确定的规划终态')
    result=dict(schema=SCHEMA,terminal=True,phase=phase,dispatch='final_reply_only',
                final_reply=message,reply_sha256=digest(message),allowed_actions=[],
                execution_authorized=False,
                next='下一条消息仅发送 final_reply 的完整正文，然后结束本轮。')
    if phase=='delivered':result.update(plan_hash=plan_hash,plan_revision=revision)
    return result

def record(base,phase,message,plan_hash=None,revision=None):
    from sos import save,read
    result=envelope(phase,message,plan_hash,revision)
    path=Path(base)/FILE
    if path.exists():
        old=read(path)
        if old.get('phase')=='planning_failed' and old!=result:
            raise ValueError('原任务已规划失败；保留终态，不能覆盖为替代方案')
    save(path,result)
    return result

def guard_failure(base):
    """Fail before reading a plan, preparing/installing a skill or starting work.

    Checks the task record independently of removable plan protocol flags.
    This is workflow enforcement, not a security boundary against file edits.
    """
    from planning_session import resolve,LINK
    base=Path(base).resolve()
    # Standalone installer callers need not own a planning task. Follow only an
    # actual task alias; do not reinterpret their directory as a new task.
    if (base/LINK).is_file():base=resolve(base)
    for name in ('.sos-flow.json',FILE):
        path=base/name
        if path.is_file() and json.loads(path.read_text()).get('phase')=='planning_failed':
            raise ValueError(FAILED)

def check_reply(expected,message):
    valid=(isinstance(expected,dict) and expected.get('schema')==SCHEMA
           and expected.get('terminal') is True and expected.get('dispatch')=='final_reply_only'
           and expected.get('reply_sha256')==digest(expected.get('final_reply','')))
    # Exact text apart from transport line endings/outer whitespace. In a sealed
    # reply even Markdown characters may belong to a filename or an approval.
    matched=bool(valid and isinstance(message,str)
                 and message.replace('\r\n','\n').strip()==expected['final_reply'].replace('\r\n','\n').strip())
    return dict(consistent=matched,commitments_consistent=matched,
                verification='observed_reply' if valid else 'invalid_terminal_record',
                reason='实际收尾与程序正文一致' if matched else '实际收尾改写了程序正文；本轮收尾未通过，聊天不改变任务授权')

def json_objects(raw):
    """Read JSON inside host XML/error wrappers and pretty-printed tool output."""
    if not isinstance(raw,str):return
    decoder=json.JSONDecoder();offset=0
    while True:
        start=raw.find('{',offset)
        if start<0:return
        try:value,length=decoder.raw_decode(raw[start:])
        except ValueError:offset=start+1;continue
        offset=start+length
        if isinstance(value,dict):yield value
