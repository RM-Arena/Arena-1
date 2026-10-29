"""Track public target motion and account for the first gimbal update before firing."""
_motion_context=Context
_motion_solution=firing_solution
_motion_weapon=weapon


class Context(_motion_context):
    def zone(self,team,kind):
        # The card is large; its nominal center is beside the workbench.
        # This interior point clears both fixtures and the receiver margin.
        if kind=='supply':return local_point(team,(2.5,12.4))
        return super().zone(team,kind)

    def __init__(self,obs,state):
        history=state.setdefault('motion_history',{})
        enemies=[];now=obs['time']
        for enemy in obs['enemies']:
            e=dict(enemy);old=history.get(e['id']);accel=(0.,0.)
            if old and 0.<now-old['time']<.4 and e['alive'] and old['alive']:
                dt=now-old['time']
                raw=((e['vx']-old['vx'])/dt,(e['vy']-old['vy'])/dt)
                length=math.hypot(*raw);scale=min(1.,6./max(.01,length))
                accel=tuple(.65*value*scale+.35*previous for value,previous in zip(raw,old['accel']))
            e['_accel']=accel
            history[e['id']]={'time':now,'vx':e['vx'],'vy':e['vy'],'alive':e['alive'],'accel':accel}
            enemies.append(e)
        for key in list(history):
            if now-history[key]['time']>3.:del history[key]
        super().__init__(dict(obs,enemies=enemies),state)


def firing_solution(robot,target):
    if '_accel' not in target:return _motion_solution(robot,target)
    lead=distance(robot,(target['x'],target['y']))/(muzzle_speed(robot)*.88)+.025
    proxy=dict(target)
    q=target.get('quaternion')
    omega=target.get('angular_velocity',(0.,0.,0.))[2]
    if q:
        angle=max(-.7,min(.7,omega*lead))/2;c,s=math.cos(angle),math.sin(angle)
        x,y,z,w=q
        proxy['quaternion']=(c*x-s*y,s*x+c*y,c*z+s*w,c*w-s*z)
    point=_aim_target(robot,proxy)
    ax,ay=target['_accel']
    proxy.update(x=point[0]+.5*ax*lead*lead,y=point[1]+.5*ay*lead*lead,aim_z=point[2])
    return _motion_solution(robot,proxy)


def weapon(robot,ctx,reach=9.,structures=False,drones_too=False):
    fields=_motion_weapon(robot,ctx,reach,structures,drones_too)
    if fields.get('fire') or 'aim' not in fields or 'pitch' not in fields:return fields
    if not can_fire(robot) or math.sqrt(sum(v*v for v in robot.get('angular_velocity',(0.,0.,0.))))>.4:
        return fields
    design=ctx.obs['robot_models'].get(str(robot.get('model_slot')), {})
    yaw_step=design.get('turret_yaw_rate_rad_s',6.5)/120
    pitch_step=design.get('turret_pitch_rate_rad_s',2.5)/120
    yaw,pitch=barrel_angles(robot)
    margin=100 if robot['role']=='heavy' else 20
    fields['fire']=abs(wrap(fields['aim']-yaw))<yaw_step+.004 \
        and abs(fields['pitch']-pitch)<pitch_step+.004 and robot['heat']+margin<=robot['max_heat']
    return fields
