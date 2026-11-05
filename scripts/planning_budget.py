#!/usr/bin/env python3
"""Read the starter's durable planning clock; never restart it on resume."""
import argparse,json,time
from pathlib import Path

def session_path(draft):return Path(draft).resolve().parent/'.sos-planning.json'

def session(draft,now=None):
    path=session_path(draft)
    if path.exists():return json.loads(path.read_text())
    clock=Path(draft).with_suffix('.clock.json')
    start=json.loads(clock.read_text()).get('started_epoch') if clock.exists() else (time.time() if now is None else now)
    if type(start) not in (float,int):raise ValueError('规划计时 started_epoch 无效，请保留真实起点')
    return dict(started_epoch=start,attempts=[])

def status(draft,now=None):
    clock=Path(draft).with_suffix('.clock.json')
    shared=session_path(draft)
    if not clock.exists() and not shared.exists():return dict(measured=False,stop_discovery=False,reason='未发现 starter 计时记录；宿主依据本次会话开始时间判断，不能重置已有计时')
    data=session(draft);start=data.get('started_epoch')
    if type(start) not in (float,int):raise ValueError('规划计时 started_epoch 无效，请保留真实起点')
    elapsed=max(0,(time.time() if now is None else now)-start)
    attempts=len(data.get('attempts',[]))
    controller=shared.parent/'.sos-flow.json'
    if controller.exists():
        state=json.loads(controller.read_text())
        if state.get('authoring_contract',0)>=5:
            selecting_again=state.get('authoring_contract',0)>=11 and bool(state.get('reselection_stage'))
            closed=state.get('phase')!='authoring' or bool(state.get('discovery_closed') or state.get('assignment_started') and not selecting_again)
            return dict(measured=True,elapsed_seconds=round(elapsed,1),stop_discovery=closed,
                        budget_kind='bounded-actions',max_search_requests=16 if state.get('authoring_contract',0)>=13 and state.get('method_search_used') else 12 if state.get('authoring_contract',0)>=7 else 8,compile_attempts=attempts,
                        next='按控制器返回的剩余动作推进；来源读取失败另用替补额度，能力契合标准保持不变。已选型则登记委托并交付。')
    compiled=any(a.get('status') in ('compiled','compiled_unresolved') for a in data.get('attempts',[]))
    unresolved=bool(data.get('attempts') and data['attempts'][-1].get('status')=='compiled_unresolved')
    if compiled:next_step=('方案已生成，能力引用待修复；停止扩展检索，可用 --repair 修正一次原文章节引用。' if unresolved and attempts<2 else '方案已编译，交付时说明当前能力状态；现有方案通过编辑或能力换用更新，停止首次规划检索。')
    elif attempts>=2:next_step='编译机会已用完，停止检索和修字段；交付草案与 .planning-error.json 的阻塞说明。'
    elif data.get('input_errors'):next_step='按输入校验诊断修复当前草案；保留计时与已选方法，停止扩展检索。'
    elif elapsed>=300:next_step='停止新增检索与补读，按已核实能力编译；未解决能力写 skill=null 与 gap，交付方案。'
    else:next_step='只补齐影响选型的原文，确认前不做业务分析。'
    return dict(measured=True,elapsed_seconds=round(elapsed,1),target_seconds=300,stop_discovery=compiled or elapsed>=300 or attempts>=2 or bool(data.get('input_errors')),compile_attempts=attempts,compile_attempts_remaining=max(0,2-attempts) if not compiled or unresolved else 0,next=next_step)

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('draft');a=ap.parse_args()
    try:print(json.dumps(status(a.draft),ensure_ascii=False))
    except (ValueError,OSError) as e:ap.error(str(e))
