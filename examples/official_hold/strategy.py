"""RMUC 2026 V1.0.0 baseline: purchases, respawn, engineer, air support."""
import math
from sdk import action, aim_at, aim_pitch, ballistic_reachable, can_fire, intercept, navigate, nearest_enemy, instant_revive_cost, resource_pickup_point, assembly_work_point

DEFENSIVE = True


def point_distance(robot, point):
    return math.hypot(robot['x']-point[0],robot['y']-point[1])


def act(obs, state):
    commands={};team=obs['team'];sign=1 if team=='red' else -1;enemy='blue' if sign==1 else 'red'
    coins=obs['teams'][team]['resources'];base=obs['bases'][team];enemy_base=obs['bases'][enemy];outpost=obs['outposts'][enemy]
    zone={z['id']:z for z in obs['arena']['zones']};home=(base['x']+sign*1.5,base['y'])
    for r in obs['robots']:
        slot=str(r['slot'])
        if slot not in obs['controlled_ids']:continue
        if r['role']=='aerial':
            lane=obs['arena']['flight_lanes'][team];goal=(lane['max_x']-1 if team=='red' else lane['min_x']+1,lane['center_y'])
            target=nearest_enemy(r,obs)
            if target:target=intercept(r,target)
            commands[slot]=action(navigate(r,goal,obs['arena']),aim_at(r,target) if target else None,
                                  can_fire(r) and target is not None,pitch=aim_pitch(r,target) if target else 0.0,
                                  support=True,altitude=1.9)
            continue
        if not r['alive']:
            commands[slot]=action(revive=coins>=instant_revive_cost(r,obs['time']) and obs['time']<300)
            continue
        if r['role']=='engineer':
            core=obs['assemblies'][team];completed=obs['teams'][team]['completed_difficulties']
            active=core['stage'] in ('moving','inserting','buffered')
            possible=[d for d in range(1,5) if obs['time']>=(d-1)*60 and (d==1 or d-1 in completed) and not (d==4 and (4 in completed or core['permanent_lock'] or obs['time']<core['retry_at']))]
            difficulty=core['difficulty'] if active else max(possible,default=1)
            needed=1 if difficulty<4 or core['inserted_units']==1 else 2
            if not active and r['carried_units']<needed:
                goal=resource_pickup_point(r,obs['arena'])
                commands[slot]=action(navigate(r,goal,obs['arena']) if point_distance(r,goal)>.08 else (0,0),pick_unit=True)
            else:
                goal=assembly_work_point(r,obs['arena'])
                commands[slot]=action(navigate(r,goal,obs['arena']) if point_distance(r,goal)>.06 else (0,0),brake=point_distance(r,goal)<=.06,
                    assembly=difficulty,assembly_insert=True,assembly_translate=True,
                    assembly_rotate=core['target_rotation'],assembly_confirm=True)
            continue
        if r['weak'] or r['hp']<r['max_hp']*.25:
            supply=zone[team+'_supply'];goal=(supply['x'],supply['y'])
        elif r['ammo']==0:
            goal=home
        elif DEFENSIVE and r['role']=='infantry':
            goal=(base['x']+sign*4,base['y']+(r['slot']%3-1)*1.2)
        else:
            structure=outpost if outpost['hp']>0 else enemy_base
            goal=(structure['x']-sign*(4 if r['role']=='hero' else 3),structure['y']+(r['slot']%3-1)*.7)
        target=nearest_enemy(r,obs)
        if target and ballistic_reachable(r,target):target=intercept(r,target)
        else:
            structure=outpost if outpost['hp']>0 else enemy_base
            target=dict(structure,kind='outpost' if outpost['hp']>0 else 'base')
            if not ballistic_reachable(r,target):target=None
        aim=aim_at(r,target) if target else None
        aligned=aim is not None and abs((aim-r['aim']+math.pi)%(math.tau)-math.pi)<.15
        operations={}
        if obs['tick']==0:operations['profile']='ranged' if r['role']=='hero' else {'chassis':r['chassis_profile'],'weapon':r['weapon_profile']}
        if r['ammo']<(2 if r['role']=='hero' else 20):
            amount=5 if r['role']=='hero' else 50
            operations['buy_ammo']={'amount':amount,'remote':False}
        fire=aligned and target is not None and can_fire(r)
        if r['role']=='infantry' and r['heat']+20>r['max_heat']:fire=False
        commands[slot]=action(navigate(r,goal,obs['arena']) if point_distance(r,goal)>.5 else (0,0),aim,fire,
                              pitch=aim_pitch(r,target) if target else 0.04,**operations)
    return commands,{'ticks':(state or {}).get('ticks',0)+1}
