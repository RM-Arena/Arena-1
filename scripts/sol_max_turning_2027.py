"""Give serial turns a bounded settling window instead of waiting at an edge."""
_turn_context=Context
_road_pointed=pointed_move
_turn_time=0.
_turn_memory={}
_turn_models={}


class Context(_turn_context):
    def __init__(self,obs,state):
        global _turn_time,_turn_memory,_turn_models
        super().__init__(obs,state)
        _turn_time=obs['time']
        _turn_memory=state.setdefault('turn_settle',{})
        _turn_models=obs['robot_models']


def pointed_move(robot,goal,speed):
    fields=_road_pointed(robot,goal,speed)
    model=_turn_models.get(str(robot.get('model_slot')), {})
    if model.get('leg_type')!='serial' or 'heading' not in fields:
        return fields
    key=robot['id'];heading=fields['heading'];turn=_turn_memory.get(key)
    if turn is None or abs(wrap(heading-turn['heading']))>.3:
        turn={'heading':heading,'since':_turn_time}
        _turn_memory[key]=turn
    if abs(wrap(heading-robot['heading']))>.18 and _turn_time-turn['since']<.7:
        fields['move']=(0,0)
    return fields
