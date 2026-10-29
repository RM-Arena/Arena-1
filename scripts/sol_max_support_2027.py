"""Use the free infantry to intercept base divers before the anchor is depleted."""
_support_parent=ROLES['infantry']


def support_goal(robot,ctx,threats):
    points=[max_local(ctx,p) for p in ((3.8,8.15),(3.85,6.95),(2.4,9.),(2.4,6.),(1.05,6.4),(1.05,8.6))]
    previous=ctx.state.setdefault('base_support_goal',{})
    if ctx.time<previous.get('until',-1):return previous['point']
    def score(p):
        proxy=dict(robot,x=p[0],y=p[1],z=robot.get('z',0)+terrain_height(ctx.arena,*p)-terrain_height(ctx.arena,robot['x'],robot['y']))
        shots=sum(max_shot_clear(proxy,e,ctx) and distance(e,p)>1.3 for e in threats)
        crowd=sum(max(0.,.9-distance(r,p)) for r in ctx.obs['robots'] if r['id']!=robot['id'] and r['alive'] and r['role']!='aerial')
        close=sum(max(0.,1.3-distance(e,p)) for e in threats)
        return -3*shots+close*2+crowd+distance(robot,p)*.04
    point=min(points,key=score) if threats else points[0]
    previous.update(point=point,until=ctx.time+2.)
    return point


def support_fighter(robot,ctx):
    if robot['slot']!=3:return _support_parent(robot,ctx)
    base=ctx.obs['bases'][ctx.team]
    threats=[e for e in ctx.obs['enemies'] if e['alive'] and not e.get('invulnerable')
        and e.get('role')!='aerial' and distance(e,(base['x'],base['y']))<7.]
    heavy_robot=next((r for r in ctx.obs['robots'] if r['role']=='heavy'),None)
    active=ctx.enemy in ctx.positions.get(f'{ctx.team}_base',{}).get('active',[])
    hurt=heavy_robot is not None and heavy_robot['hp']<heavy_robot['max_hp']*.8 \
        and ctx.time-heavy_robot.get('last_damage_time',-99)<3.
    # A protected, healthy anchor already denies the base clock. Do not pull
    # the mobile infantry off the outpost solely because a diver is nearby.
    unsafe=heavy_robot is None or not heavy_robot['alive'] or heavy_robot.get('weak') \
        or heavy_robot['hp']<heavy_robot['max_hp']*.7 or not ctx.controls(f'{ctx.team}_base')
    if hurt or unsafe and (threats or active):ctx.state['base_threat_until']=ctx.time+15.
    wanted=ctx.time<ctx.state.get('base_threat_until',-1)
    front=front_threats(ctx)
    lost_home=not ctx.controls(f'{ctx.team}_outpost')
    if lost_home or len(front)>=2 and any(e['role']=='sentry' for e in front):
        ctx.state['front_reinforce_until']=ctx.time+6.
    reinforce=ctx.time<ctx.state.get('front_reinforce_until',-1)
    if ctx.controls(f'{ctx.enemy}_base') and robot['id'] in ctx.obs['zones'].get(f'{ctx.enemy}_base',{}).get('occupants',[]):
        reinforce=False
    base_critical=not ctx.controls(f'{ctx.team}_base') or heavy_robot is not None and heavy_robot['hp']<heavy_robot['max_hp']*.6
    if not (wanted or reinforce) or robot.get('weak') or robot['hp']<robot['max_hp']*.24 \
            or ctx.state.get('max_recovery',{}).get(str(robot['slot'])):
        return _support_parent(robot,ctx)
    fields=max_logistics(robot,ctx)
    if ctx.obs['tick']==0:fields['profile']={'chassis':'hp','weapon':'cooling'}
    goal=outpost_card_spot(ctx,ctx.team) if reinforce and not base_critical else support_goal(robot,ctx,threats)
    fields.update(max_hold(robot,goal,ctx))
    fields.update(weapon(robot,ctx,reach=9.,structures=False,drones_too=False))
    ctx.state.get('max_routes',{}).pop(str(robot['slot']),None)
    return fields


ROLES['infantry']=support_fighter


_front_parent=ROLES['sentry']


def front_threats(ctx):
    center=ctx.zone(ctx.team,'central')
    return [e for e in ctx.obs['enemies'] if e['alive'] and e.get('role')!='aerial'
        and e['hp']>e['max_hp']*.25 and local_point(ctx.team,(e['x'],e['y']))[0]>8.5
        and distance(e,center)<4.]


def front_response(robot,ctx):
    threats=front_threats(ctx)
    pressure=len(threats)>=2 and any(e['role']=='sentry' for e in threats)
    if pressure or not ctx.controls(f'{ctx.team}_outpost'):
        ctx.state['front_guard_until']=ctx.time+6.;ctx.state['home_sentry']=True
    guardian=next((r for r in ctx.obs['robots'] if r['slot']==4),None)
    relieved=guardian is not None and guardian['alive'] and not guardian.get('weak') \
        and guardian['hp']>guardian['max_hp']*.6 \
        and not ctx.state.get('base_cover') and not ctx.state.get('max_recovery',{}).get('4') \
        and on_outpost_card(guardian,ctx.team,ctx)
    if ctx.time>=ctx.state.get('front_guard_until',-1) and relieved:
        ctx.state['home_sentry']=False
    ration_due=int(ctx.time//60)>robot.get('supply_grants_taken',0)
    needs_recovery=robot['hp']<robot['max_hp']*.24 or robot['ammo']<20 and ration_due and relieved
    if not ctx.state.get('home_sentry') or robot.get('weak') or needs_recovery \
            or ctx.state.get('max_recovery',{}).get(str(robot['slot'])):
        return _front_parent(robot,ctx)
    if ctx.time<25 and not leg_memory(robot,ctx.obs,ctx.memory).get('entry_done'):
        return _front_parent(robot,ctx)
    fields=max_logistics(robot,ctx)
    fields.update(max_hold(robot,max_local(ctx,(10.8,6.)),ctx))
    fields.update(weapon(robot,ctx,reach=10.,structures=False,drones_too=False))
    fighting=any(e['alive'] and not e.get('invulnerable') and distance(e,(robot['x'],robot['y']))<9 for e in ctx.obs['enemies'])
    wanted='attack' if fighting and robot['hp']>robot['max_hp']*.45 else 'defense'
    if ctx.time>=(robot.get('posture_ready_at') or 0):
        fields.update(posture=wanted,posture_enhanced=wanted=='defense' and robot['hp']<robot['max_hp']*.45
            and ctx.time-robot.get('last_damage_time',-99)<2.)
    return fields


ROLES['sentry']=front_response
