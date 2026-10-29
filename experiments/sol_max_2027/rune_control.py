import math


def rune_rotate(point,seconds,rune,arena,team):
    if '_decision_time' in rune:
        now=rune['_decision_time'];seconds=math.ceil((now+seconds-1e-9)*20)/20-now
    angle=arena.get('axis_yaw',math.pi/4);nx,ny=math.cos(angle),math.sin(angle)
    sign=-1. if team=='red' else 1.
    center=(arena['x']+sign*arena.get('face_offset_m',.35)*nx,arena['y']+sign*arena.get('face_offset_m',.35)*ny,arena['z'])
    u=-(point[0]-center[0])*ny+(point[1]-center[1])*nx;v=point[2]-center[2]
    delta=(rune.get('angular_velocity') or 0.)*seconds+.5*(rune.get('angular_acceleration') or 0.)*seconds*seconds
    a,b=u*math.cos(delta)-v*math.sin(delta),u*math.sin(delta)+v*math.cos(delta)
    return center[0]-ny*a,center[1]+nx*a,center[2]+b


def rune_plane_flight(robot,yaw,pitch,arena,team):
    angle=arena.get('axis_yaw',math.pi/4);nx,ny=math.cos(angle),math.sin(angle)
    sign=-1. if team=='red' else 1.
    center=(arena['x']+sign*arena.get('face_offset_m',.35)*nx,arena['y']+sign*arena.get('face_offset_m',.35)*ny,arena['z'])
    direction=(math.cos(yaw)*math.cos(pitch),math.sin(yaw)*math.cos(pitch),math.sin(pitch))
    pivot=_rotate(robot.get('quaternion',(0,0,0,1)),(0,0,robot.get('muzzle_height_m',.47)))
    origin=[robot[k]+pivot[i]+robot.get('muzzle_reach_m',.22)*direction[i] for i,k in enumerate(('x','y','z'))]
    velocity=[muzzle_speed(robot)*direction[i]+robot.get(k,0.) for i,k in enumerate(('vx','vy','vz'))]
    elapsed=0.;dt=1/120;drag=.5*1.225*.47*math.pi*.0084**2/.0032
    for _ in range(240):
        speed=math.sqrt(sum(v*v for v in velocity));accel=[-drag*speed*v for v in velocity];accel[2]-=9.81
        end=[o+v*dt+.5*a*dt*dt for o,v,a in zip(origin,velocity,accel)]
        before=(origin[0]-center[0])*nx+(origin[1]-center[1])*ny
        after=(end[0]-center[0])*nx+(end[1]-center[1])*ny
        if before*after<=0:
            fraction=before/(before-after)
            return elapsed+dt*fraction,tuple(o+(e-o)*fraction for o,e in zip(origin,end))
        origin=end;velocity=[v+a*dt for v,a in zip(velocity,accel)];elapsed+=dt
    return None


def rune_solution(robot,target,rune,arena,team,delay):
    point=(target['x'],target['y'],target['z']);flight=math.dist((robot['x'],robot['y'],robot['z']),point)/muzzle_speed(robot)
    for _ in range(5):
        predicted=rune_rotate(point,flight+delay,rune,arena,team)
        proxy={'x':predicted[0],'y':predicted[1],'aim_z':predicted[2],'kind':'rune_target'}
        solution=_motion_solution(robot,proxy)
        if solution is None:return None
        yaw,pitch=solution
        q=robot.get('quaternion',(0,0,0,1));local=_rotate((-q[0],-q[1],-q[2],q[3]),(math.cos(yaw)*math.cos(pitch),math.sin(yaw)*math.cos(pitch),math.sin(pitch)))
        if not -.255<math.atan2(local[2],math.hypot(local[0],local[1]))<.78:return None
        impact=rune_plane_flight(robot,yaw,pitch,arena,team)
        if impact is None:return None
        flight=impact[0]
    return yaw,pitch,flight


def rune_trial_fields(robot,ctx):
    state=ctx.state.setdefault('rune_trial',{})
    rune=dict(ctx.obs.get('runes',{}).get(ctx.team,{}),_decision_time=ctx.time)
    arena=ctx.arena['rune'];targets=rune.get('targets') or []
    fields={'aim':math.atan2(arena['y']-robot['y'],arena['x']-robot['x']),'pitch':.6,'fire':False}
    if ctx.time<180:return fields
    if rune.get('status') not in ('activating','active'):
        fields['rune_start']=True;state.clear();return fields
    if rune.get('status')=='active':return fields
    if ctx.time<state.get('wait_until',-1.):
        fields.update(aim=state.get('last_aim',fields['aim']),pitch=state.get('last_pitch',fields['pitch']));return fields
    lit=[t for t in targets if t.get('lit')]
    if not lit:return fields
    solutions=[]
    for target in lit:
        solution=rune_solution(robot,target,rune,arena,ctx.team,7/120)
        if solution is not None:solutions.append((target,solution))
    if not solutions:return fields
    target,solution=next(((t,s) for t,s in solutions if t['arm']==state.get('arm')),min(solutions,key=lambda ts:abs(ts[1][1]-barrel_angles(robot)[1])))
    yaw,pitch,flight=solution
    design=ctx.obs['robot_models'][str(robot['model_slot'])];rate=design['turret_yaw_rate_rad_s'];offset=rate*.045
    choices=[]
    for sign in (-1,1):
        first_yaw=wrap(yaw+sign*(offset-rate/120))
        impact=rune_plane_flight(robot,first_yaw,pitch,arena,ctx.team)
        if impact is None:continue
        predicted=[rune_rotate((t['x'],t['y'],t['z']),impact[0]+1/120,rune,arena,ctx.team) for t in targets]
        clearance=min(math.dist(impact[1],point) for point in predicted)
        choices.append((clearance,sign))
    if not choices:return fields
    clearances={sign:distance for distance,sign in choices};best=max(choices)
    old_clear=clearances.get(state.get('sign'),-1.)
    if state.get('arm')!=target['arm'] or old_clear<.4 or old_clear<best[0]-.15:
        state.update(arm=target['arm'],sign=best[1])
    sign=state['sign'];actual_yaw,actual_pitch=barrel_angles(robot)
    prepared=abs(wrap(actual_yaw-wrap(yaw+sign*offset)))<.025 and abs(actual_pitch-pitch)<.025
    reserve=40 if not rune.get('pair_deadline') else 20
    if prepared and can_fire(robot) and robot['heat']+reserve<=robot['max_heat']:
        fields.update(aim=yaw,pitch=pitch,fire=True)
        state.update(wait_until=ctx.time+7/120+flight+.06,last_aim=yaw,last_pitch=pitch)
        state['arm']=None
        return fields
    future=rune_solution(robot,target,rune,arena,ctx.team,19/120)
    if future is not None:fields.update(aim=wrap(future[0]+sign*offset),pitch=future[1])
    return fields
