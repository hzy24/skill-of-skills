"""Public planning surface shared by controller help and trace auditing."""
ACTIONS={
    'init':'登记原始需求与材料结构', 'search':'检索专业能力', 'inspect':'核读候选',
    'local':'核读已安装能力', 'section':'读取方法章节', 'methods':'查看方法目录',
    'resource':'读取方法配套资料', 'probe':'补充字段类型、日期或类别取值',
    'material':'读取材料目录或有限章节', 'assess':'记录候选适配判断',
    'view':'分页读取本任务已保存的工具结果，不重复检索',
    'route-template':'生成当前任务的路线填写模板', 'route':'校验并登记业务阶段',
    'review':'记录当前路线的阶段适配判断', 'reselect':'为具体阶段补充选型',
    'publish':'生成可编辑方案附件', 'status':'读取原任务当前状态',
    'finish':'核对附件并生成收尾正文',
}
LEGACY_ACTIONS={'assign','produce','build','submit','receipt'}

def actions(phase,has_route=False):
    if phase=='authoring':return [k for k in ACTIONS if k not in ('init','finish')]
    if phase=='awaiting_delivery':return ['status','finish']
    return []
