"""Keep the base anchor on its card while using the base body as cover."""
_previous_base_guard = max_guard


def base_body_blocks(a, b, body):
    lo,hi=0.,1.
    for p,d,low,high in ((a[0],b[0]-a[0],body['x'],body['x']+body['w']),
                          (a[1],b[1]-a[1],body['y'],body['y']+body['h'])):
        if abs(d)<1e-9:
            if not low<p<high:return False
        else:
            left,right=sorted(((low-p)/d,(high-p)/d));lo,hi=max(lo,left),min(hi,right)
    return lo<hi and hi>0 and lo<1


def max_guard(robot, ctx):
    fields=_previous_base_guard(robot,ctx)
    ctx.state['guard_secure']=False
    if ctx.time<25 or robot.get('weak'):return fields
    memory=ctx.state.setdefault('guard_cover',{})
    base=ctx.obs['bases'][ctx.team]
    on_card=robot['id'] in ctx.obs['zones'].get(f'{ctx.team}_base',{}).get('occupants',[])
    relief=any(r['slot']!=robot['slot'] and r['alive'] and not r.get('weak')
        and r['id'] in ctx.obs['zones'].get(f'{ctx.team}_base',{}).get('occupants',[])
        for r in ctx.obs['robots'])
    if ctx.state.get('guard_recover') and relief:return fields
    if not on_card and (not memory or distance(robot,(base['x'],base['y']))>4.):return fields
    threats=[e for e in ctx.obs['enemies'] if e['alive'] and not e.get('invulnerable')
        and e.get('role')!='aerial' and distance(e,(base['x'],base['y']))<9.]
    points=[max_local(ctx,p) for p in ((1.05,7.5),(1.05,8.8),(2.4,8.8),(3.85,8.8),
                                      (3.85,7.5),(3.85,6.2),(2.4,6.2),(1.05,6.2))]
    body=min((w for w in ctx.arena['forbidden'] if w['kind']=='base'),
        key=lambda w:math.hypot(w['x']+w['w']/2-base['x'],w['y']+w['h']/2-base['y']))
    def risk(point):
        return sum((.015 if base_body_blocks((e['x'],e['y']),point,body) else 1.)/
                   max(.6,distance(e,point)) for e in threats)
    closest=min(range(len(points)),key=lambda i:distance(robot,points[i]))
    recent=ctx.time-robot.get('last_damage_time',-99)<2.5
    ctx.state['guard_secure']=on_card and not ctx.state.get('guard_recover') and not recent and ctx.time-robot.get('last_damage_time',-99)>6.2 and risk((robot['x'],robot['y']))<.08
    exposed=risk((robot['x'],robot['y']))>min(risk(p) for p in points)+.08
    if 'target' not in memory and not (exposed or recent and robot['hp']<robot['max_hp']*.85):
        return fields
    if threats:
        desired=min((0,2,4,6),key=lambda i:risk(points[i])+.006*distance(robot,points[i]))
        old=memory.get('target',desired)
        if 'target' not in memory or risk(points[old])>risk(points[desired])+.08:
            memory.update(target=desired,since=ctx.time,until=ctx.time+8.)
    elif recent and robot['hp']<robot['max_hp']*.9:
        # A close attacker can be outside every camera. React to our own
        # damage telemetry without assuming a hidden opponent position.
        if 'target' not in memory or ctx.time>memory.get('until',0):
            memory.update(target=max((0,2,4,6),key=lambda i:distance(robot,points[i])),
                since=ctx.time,until=ctx.time+8.)
    if 'target' not in memory:return fields
    desired=memory['target']
    if memory.get('route_target')!=desired:
        clockwise=(desired-closest)%len(points);counter=(closest-desired)%len(points)
        direction=1 if clockwise<=counter else -1
        route=[];index=closest
        if distance(robot,points[index])>.25:route.append(index)
        while index!=desired:
            index=(index+direction)%len(points);route.append(index)
        memory.update(route_target=desired,route=route,heading=robot['heading'])
    route=memory['route']
    while route and distance(robot,points[route[0]])<.18:route.pop(0)
    goal=points[route[0]] if route else points[desired]
    dx,dy=goal[0]-robot['x'],goal[1]-robot['y'];gap=math.hypot(dx,dy)
    if gap<.15:fields.update(move=(0,0),brake=True)
    else:
        speed=min(1.8,gap*3.)/robot['speed_reference_mps']
        fields.update(move=(dx/gap*speed,dy/gap*speed),heading=memory['heading'],brake=True,power=200)

    return fields


ROLES['heavy']=max_guard
