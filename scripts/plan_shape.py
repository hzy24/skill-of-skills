"""Validate JSON container/scalar types before relational plan validation.

Missing fields are reported by the existing semantic validator. Unknown metadata
is preserved. This layer also accepts incomplete drafts before expansion.
"""
TEXTS=[str]
CHECK={'id':str,'kind':str,'artifact':str,'criteria':str,'values':TEXTS,
       'value':int,'source':str,'evidence':str,'cwd':str,'argv':TEXTS,'review_inputs':TEXTS}
CONTRACT={'inherit':str,'mode':str,'source':str,'source_evidence':str,'invocation':str,
          'inputs':TEXTS,'outputs':TEXTS,'check_ids':TEXTS,'required_checks':[CHECK],
          'branch_basis':str,'verification':str,
          'prerequisites':[{'requirement':str,'status':str,'evidence':str}]}
BINDING={'skill':str,'candidate_id':str,'scope':str,'reason':str,'readiness':str,'contract':CONTRACT}
NODE={k:str for k in ('id','title','description','reason','method','stage_method')}
NODE.update({k:TEXTS for k in ('depends_on','inputs','outputs','requirements','done_when','outline_ids','capability_need_ids')})
NODE.update(checks=[CHECK],bindings=[BINDING])
NEED={'id':str,'task_kind':str,'requirement_ids':TEXTS,'standard':str,'existing_assessment':str,
      'role':str,
      'method_evidence':{'material_id':str,'excerpt':str,'source_sha256':str,'sections':[{'id':str,'title':str,'sha256':str,'excerpt':str}]},
      'outline_ids':TEXTS,'gap':str,'discovery':{'status':str,'evidence':str},
      'decision':{'kind':str,'reason':str,'application':str,'candidate_id':str,'fit':str,'fallback_limit':str,
                  'direct_basis':{'candidate_ids':TEXTS,'reason':str,'coverage':str,'limitations':str},
                  'fallback_authorization':{'actor':str,'evidence':str,'scope':str}}}
CANDIDATE={k:str for k in ('id','name','source','version','license')}
CANDIDATE.update(evidence=[{'kind':str,'locator':str,'finding':str}],setup={k:str for k in
 ('status','dependencies','permissions','verification','request_reason','installation','fallback','authorization')})
CANDIDATE['method_support']={'material_id':str,'workflow':str,'checks':str,'sha256':str}
SHAPE={k:str for k in ('id','title','goal','mode','capability_policy')}
SHAPE.update(handoff_protocol_version=int,review_protocol_version=int,professional_review={'basis_hash':str,'verdict':str,'source_hashes':{},'items':[{}]})
SHAPE.update({k:int for k in ('revision','max_attempts','capability_contract_version','selection_contract_version','quality_contract_version','capability_policy_version')})
SHAPE.update(requirements=[{'id':str,'text':str}],materials=[{'id':str,'title':str,'path':str,'source_url':str}],
 deliverables=[{'id':str,'title':str,'description':str,'format':str,'outline_level':str,'outline_ids':TEXTS,'delivery_role':str}],nodes=[NODE],
 content_outline=[{'id':str,'title':str,'claim':str,'visual':str,'points':TEXTS,'sources':TEXTS,'acceptance':TEXTS}],
 role_tasks=[{'id':str,'capability_need_ids':TEXTS}],scope_changes=[{}],capability_needs=[NEED],capability_candidates=[CANDIDATE],selection_needs_review=bool,selection_review_nodes=TEXTS)

def errors(value,schema=SHAPE,path='plan'):
    if isinstance(schema,dict):
        if not isinstance(value,dict):return [path+' 须为对象']
        return [e for k,s in schema.items() if k in value for e in errors(value[k],s,path+'.'+k)]
    if isinstance(schema,list):
        if not isinstance(value,list):return [path+' 须为列表']
        return [e for i,x in enumerate(value) for e in errors(x,schema[0],path+'['+str(i)+']')]
    if type(value) is not schema:
        return [path+' 须为'+{str:'文本',int:'整数',bool:'布尔值'}[schema]]
    return []

SHAPE.update(task_route_version=int,task_route={'reason':str,'verification':str})
SHAPE['stage_review_version']=int
