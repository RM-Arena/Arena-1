"""Acquire hidden approaches through staggered, legal gimbal searches."""
_search_weapon=weapon
_search_decide=decide

def search_bearing(robot,ctx):
    phase={1:1.,3:0.,4:2.1,7:4.2}.get(robot['slot'],0.)
    return wrap(ctx.time*2.2+phase+(math.pi if ctx.team=='blue' else 0.))

def weapon(robot,ctx,reach=9.,structures=False,drones_too=False):
    fields=_search_weapon(robot,ctx,reach,structures,drones_too)
    if 'aim' not in fields:fields['aim']=search_bearing(robot,ctx)
    return fields

def decide(robot,ctx):
    fields=_search_decide(robot,ctx)
    if robot['alive'] and robot['role']!='aerial' and not robot.get('tipped'):
        fields.setdefault('aim',search_bearing(robot,ctx))
    return fields
