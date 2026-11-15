"""Strict AI output contracts shared by generation and repair calls."""

def obj(properties):
    return {'type': 'object', 'properties': properties, 'required': list(properties), 'additionalProperties': False}


def array(items, minimum=0):
    return {'type': 'array', 'items': items, 'minItems': minimum}


def enum(*values):
    return {'type': 'string', 'enum': list(values)}


TEXT = {'type': 'string', 'minLength': 1}
STRING = {'type': 'string'}
BOOL = {'type': 'boolean'}
NUMBER = {'type': 'number'}
INTEGER = {'type': 'integer', 'minimum': 0}
MODULE = obj(dict(code=TEXT, parent_code=STRING, title=TEXT, path=TEXT,
                  depth={'type': 'integer', 'minimum': 1, 'maximum': 3}, order=INTEGER))
ATOM = obj(dict(code=TEXT, module_code=TEXT, name=TEXT, goal_statement=TEXT,
                parent_path=TEXT, goal_type=enum('概念辨析','公式推导','实操计算','机制分析','对比区分','综合应用'),
                granularity_minutes={'type': 'integer'}, cognitive_level=enum('记忆','理解','应用','分析','评价'),
                key_elements=array(TEXT), prerequisites_hint=array(TEXT), common_misconceptions=array(TEXT),
                branch_condition=STRING, order=INTEGER))
EDGE = obj(dict(from_atom=TEXT, to_atom=TEXT, edge_strength=enum('strong','weak','contrast','bidirectional','none'),
                relation_label=STRING, rationale=TEXT, confidence={'type':'number','minimum':0,'maximum':1}))
LINE = obj(dict(from_atom_code=TEXT, to_atom_code=TEXT, kind=enum('progression','contrast'), reason=TEXT))
STEP = obj(dict(step_title=TEXT, step_role=TEXT, branch_condition=STRING,
                core_atoms=array(TEXT), extension_atoms=array(TEXT), intra_lines=array(LINE)))
PLAN = obj(dict(steps=array(STEP,1), narrative_summary=TEXT))
BLOCK_NAME = obj(dict(code=TEXT,short_title=TEXT,is_entry_block=BOOL,rationale=TEXT))
BLOCK_RELATION = obj(dict(from_block=TEXT,to_block=TEXT,edge_kind=enum('unidirectional','bidirectional','none'),
                          directness_score={'type':'number','minimum':0,'maximum':5},rationale=TEXT))
INTERFACE = obj(dict(from_atom=TEXT,to_atom=TEXT,
                     interface_role=enum('prerequisite_handoff','application_transfer','diagnostic_escalation','contrast_bridge'),
                     bridge_explanation=TEXT))
SCHEMAS = {
    'archetype_classify': obj(dict(archetype=enum('institution_mechanism_theory','formula_derivation_chain','taskflow_diagnostic_tree','case_synthesis_deduction'))),
    'outline_decompose': obj(dict(modules=array(MODULE,1))),
    'atom_generate': obj(dict(atoms=array(ATOM,1))),
    'atom_repair': obj(dict(atoms=array(ATOM,1))),
    'edge_classify': obj(dict(edges=array(EDGE))),
    'edge_cycle_resolve': obj(dict(edges=array(EDGE))),
    'block_naming': obj(dict(blocks=array(BLOCK_NAME,1))),
    'interblock_review': obj(dict(edges=array(BLOCK_RELATION),entry_blocks=array(TEXT))),
    'intrablock_steps': PLAN,
    'intrablock_repair': PLAN,
    'interface_bind': obj(dict(interfaces=array(INTERFACE,1))),
}
