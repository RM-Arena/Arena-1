"""Keep useful firing lanes and maintain distance from armor targets."""
_formation_hold=max_hold


def max_hold(robot,goal,ctx,tolerance=.18):
    if robot['role'] not in ('infantry','sentry') or robot.get('weak') or goal is None:
        return _formation_hold(robot,goal,ctx,tolerance)
    contacts=set(robot.get('last_raw_zones',[]))
    card=next((z for z in ctx.arena['zones'] if z['kind']=='central' and z['id'] in contacts
        and point_in_polygon(goal[0],goal[1],z['polygon'])),None)
    enemies=[e for e in ctx.obs['enemies'] if e['alive'] and not e.get('invulnerable')
        and distance(e,(robot['x'],robot['y']))<5.]
    close=any(distance(e,(robot['x'],robot['y']))<1.35 for e in enemies)
    spacing=ctx.state.setdefault('spacing',{})
    memory=spacing.setdefault(str(robot['slot']),{})
    if card and close and (ctx.time>=memory.get('until',0) or memory.get('card')!=card['id']):
        owner=card['owner']
        points=[local_point(owner,(x,y)) for x in (10.6,11.0) for y in (6.,7.7,9.25)]
        friends=[]
        for r in ctx.obs['robots']:
            if r['id']==robot['id'] or not r['alive'] or r['role']=='aerial':continue
            intent=spacing.get(str(r['slot']),{})
            friends.append(intent['goal'] if intent.get('card')==card['id'] else (r['x'],r['y']))
        def shadow(p,e,f):
            dx,dy=e['x']-p[0],e['y']-p[1];square=dx*dx+dy*dy
            u=((f[0]-p[0])*dx+(f[1]-p[1])*dy)/max(.01,square)
            return .03<u<.97 and math.hypot(p[0]+u*dx-f[0],p[1]+u*dy-f[1])<.27
        def score(p):
            return sum(1/max(.5,distance(e,p)) for e in enemies) \
                +sum(max(0.,1.-math.dist(f,p))*2 for f in friends) \
                +sum(1.5*shadow(p,e,f) for f in friends for e in enemies)+.025*distance(robot,p)
        memory.update(goal=min(points,key=score),until=ctx.time+3.,card=card['id'])
    if card and memory.get('card')==card['id'] and (enemies or ctx.time<memory.get('until',0)):
        goal=memory['goal']
    if card and robot['slot']==4 and (enemies or ctx.time-robot.get('last_damage_time',-99)<2.):
        # Move along the card rather than offering a stationary armor plate.
        # Two frequencies change acceleration without reading the match seed.
        candidate=(goal[0],goal[1]+.35*math.sin(ctx.time*3.7)+.15*math.sin(ctx.time*7.1))
        if point_in_polygon(candidate[0],candidate[1]+.21,card['polygon']):goal=candidate
    fields=_formation_hold(robot,goal,ctx,tolerance)
    if card and distance(robot,goal)<.25 and not leg_memory(robot,ctx.obs,ctx.memory).get('nav_jump'):
        # The receiver stays inside the narrow card while the gimbal remains
        # free to aim in world coordinates.
        fields['heading']=math.pi/2
    return fields
