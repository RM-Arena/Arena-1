
_transit_decide=decide

def decide(robot,ctx):
    fields=_transit_decide(robot,ctx)
    if robot['role']!='sentry' or not robot['alive'] or robot.get('weak') or robot.get('tipped'):
        return fields
    memory=leg_memory(robot,ctx.obs,ctx.memory)
    entry=(ctx.time<25. or memory.get('entry') or memory.get('entry_wait')) and not memory.get('entry_done')
    jumping=bool(memory.get('nav_jump') or memory.get('rim_hop') or memory.get('road_escape'))
    transit=entry or jumping or not robot.get('grounded',True)
    if transit and ctx.time >= (robot.get('posture_ready_at') or 0):
        fields.update(posture='move',posture_enhanced=False)
    return fields

def max_supply_point(robot,ctx):
    return max_local(ctx,(2.7,{3:12.45,4:13.25,7:14.05}[robot['slot']]))

# Preserve the forward sentry and the independent mobile infantry assignment.
ROLES.update(infantry=max_fighter,sentry=max_fighter)

_guarded_decide=decide

def decide(robot,ctx):
    fields=_guarded_decide(robot,ctx)
    if robot['role']!='sentry' or not robot['alive'] or robot.get('weak') or robot.get('tipped') or not robot.get('grounded',True):return fields
    if ctx.time<(robot.get('posture_ready_at') or 0):return fields
    memory=leg_memory(robot,ctx.obs,ctx.memory)
    transit=(ctx.time<25. or memory.get('entry') or memory.get('entry_wait')) and not memory.get('entry_done')
    if transit or memory.get('nav_jump') or memory.get('rim_hop') or memory.get('road_escape'):return fields
    spent=robot.get('posture_enhanced_time',(0.,0.,0.))[1]
    threats=[e for e in ctx.obs['enemies'] if e['alive'] and not e.get('weak') and not e.get('invulnerable')
        and (e['role'] in ('infantry','sentry') or e['role']=='heavy' and ctx.time-robot.get('last_damage_time',-99)<1.)
        and distance(e,(robot['x'],robot['y']))<5.]
    if spent<14.5 and threats and ('pitch' in fields or ctx.time-robot.get('last_damage_time',-99)<1.):
        fields.update(posture='defense',posture_enhanced=True)
    return fields

_alarm_context=Context
_alarm_hold=max_hold
_alarm_entry=highland_entry

class Context(_alarm_context):
    def __init__(self,obs,state):
        super().__init__(obs,state)
        base=self.obs['bases'][self.team]
        divers=[e for e in self.obs['enemies'] if e['alive'] and not e.get('invulnerable') and e['role'] in ('infantry','sentry','heavy')
            and local_point(self.team,(e['x'],e['y']))[0]<9.7 and distance(e,(base['x'],base['y']))<8.5]
        alarm=self.state.setdefault('base_alarm',{'until':-1.})
        trigger=len(divers)>=2 or any(e['role']=='sentry' for e in divers)
        if trigger or divers and self.time<alarm['until']:
            if self.time>=alarm['until']:alarm['began']=self.time
            alarm['until']=self.time+18.
        heavy=next((r for r in self.obs['robots'] if r['slot']==1),None)
        helper=next((r for r in self.obs['robots'] if r['slot']==alarm.get('slot')),None)
        reached=helper is not None and helper['id'] in self.obs['zones'].get(f'{self.team}_base',{}).get('occupants',[])
        safe=heavy is not None and heavy['alive'] and not heavy.get('weak') and heavy['hp']>=heavy['max_hp']*.8 and self.time-heavy.get('last_damage_time',-99)>6.2
        if len(divers)<=1 and reached and safe and self.time-alarm.get('began',self.time)>20.:
            alarm.update(until=self.time-1.,released_at=self.time)
        if len(divers)<=1 and 'released_at' in alarm and heavy is not None and heavy['alive'] and not heavy.get('weak') and heavy.get('last_damage_time',-99)<=alarm['released_at'] and self.controls(f'{self.team}_base'):
            alarm['until']=self.time-1.
        if self.time>=alarm['until']:alarm.pop('slot',None);return
        eligible=[r for r in self.obs['robots'] if r['alive'] and not r.get('weak') and r['slot'] in (3,4,7)
            and r['hp']>r['max_hp']*.4 and r['ammo']>0 and not self.state.get('max_recovery',{}).get(str(r['slot']))]
        old=next((r for r in eligible if r['slot']==alarm.get('slot')),None)
        if old is None and eligible:
            alarm['slot']=min(eligible,key=lambda r:{4:0,3:5,7:10}[r['slot']]+.2*distance(r,(base['x'],base['y'])))['slot']
        if alarm.get('slot')==4:self.state['base_cover']=True

def highland_entry(robot,ctx):
    alarm=ctx.state.get('base_alarm',{})
    if ctx.time>=25. and ctx.time<alarm.get('until',-1.) and robot['slot']==alarm.get('slot'):return None
    return _alarm_entry(robot,ctx)

def max_hold(robot,goal,ctx,tolerance=.18):
    alarm=ctx.state.get('base_alarm',{})
    if ctx.time>=25. and ctx.time<alarm.get('until',-1.) and robot['slot']==alarm.get('slot') and not robot.get('weak') and not ctx.state.get('max_recovery',{}).get(str(robot['slot'])):
        goal=max_local(ctx,(3.8,8.15))
        if robot['slot']==4:ctx.state['base_cover']=True
    return _alarm_hold(robot,goal,ctx,tolerance)

_escort_context=Context
_escort_hold=max_hold

class Context(_escort_context):
    def __init__(self,obs,state):
        previous=state.get('base_alarm',{}).get('slot')
        super().__init__(obs,state)
        alarm=self.state.get('base_alarm',{})
        base=self.obs['bases'][self.team]
        divers=[e for e in self.obs['enemies'] if e['alive'] and not e.get('invulnerable') and e['role'] in ('infantry','sentry','heavy')
            and local_point(self.team,(e['x'],e['y']))[0]<9.7 and distance(e,(base['x'],base['y']))<8.5]
        sentry=next((r for r in self.obs['robots'] if r['slot']==7),None)
        if len(divers)>=2:alarm['multi_until']=self.time+15.
        multiple=self.time<alarm.get('multi_until',-1.)
        if multiple:
            alarm['until']=max(alarm.get('until',-1.),alarm['multi_until'])
            guardian=next((r for r in self.obs['robots'] if r['slot']==4),None)
            if guardian is not None and guardian['alive'] and not guardian.get('weak') and guardian['hp']>guardian['max_hp']*.4 and guardian['ammo']>0 and not self.state.get('max_recovery',{}).get('4'):
                alarm['slot']=4;self.state['base_cover']=True
        if not multiple and self.time<alarm.get('until',-1.) and len(divers)==1 and divers[0]['role']=='sentry' and sentry is not None and sentry['alive'] and not sentry.get('weak') and sentry['hp']>sentry['max_hp']*.4 and sentry['ammo']>0 and not self.state.get('max_recovery',{}).get('7'):
            alarm['slot']=7
        if previous is not None and previous!=alarm.get('slot'):
            relieved=next((r for r in self.obs['robots'] if r['slot']==previous),None)
            if relieved is not None and relieved.get('grounded') and local_point(self.team,(relieved['x'],relieved['y']))[0]<8.4:
                memory=leg_memory(relieved,self.obs,self.memory)
                jump=memory.pop('nav_jump',None)
                if jump:self.memory.get('nav_locks',{}).pop(jump['lock'],None)
                for key in ('entry_done','entry','entry_wait','road_escape','rim_hop'):memory.pop(key,None)

def max_hold(robot,goal,ctx,tolerance=.18):
    alarm=ctx.state.get('base_alarm',{})
    if robot['slot']==7 and alarm.get('slot')==7 and ctx.time<alarm.get('until',-1.) and not robot.get('weak') and not ctx.state.get('max_recovery',{}).get('7'):
        base=ctx.obs['bases'][ctx.team]
        threats=[e for e in ctx.obs['enemies'] if e['alive'] and not e.get('invulnerable') and e['role']!='aerial' and distance(e,(base['x'],base['y']))<9.]
        goal=support_goal(robot,ctx,threats)
        # Call the pre-alarm hold once so the selected firing lane is retained.
        return _alarm_hold(robot,goal,ctx,tolerance)
    return _escort_hold(robot,goal,ctx,tolerance)
