
_crossfire_hold=max_hold

def max_hold(robot,goal,ctx,tolerance=.18):
    if robot['slot']==3 and robot['alive'] and not robot.get('weak') and goal is not None and not ctx.state.get('max_recovery',{}).get('3'):
        card=next(z for z in ctx.arena['zones'] if z['id']==f'{ctx.enemy}_central')
        if point_in_polygon(goal[0],goal[1],card['polygon']) and (ctx.time>=25. or leg_memory(robot,ctx.obs,ctx.memory).get('entry_done')):
            goal=outpost_card_spot(ctx,ctx.enemy)
    return _crossfire_hold(robot,goal,ctx,tolerance)
