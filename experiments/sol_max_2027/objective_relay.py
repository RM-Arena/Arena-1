
_relay_context=Context
_relay_hold=max_hold

class Context(_relay_context):
    def __init__(self,obs,state):
        super().__init__(obs,state)
        relay=self.state.setdefault('objective_relay',{})
        flex=next((r for r in self.obs['robots'] if r['slot']==3),None)
        guard=next((r for r in self.obs['robots'] if r['slot']==4),None)
        sentry=next((r for r in self.obs['robots'] if r['slot']==7),None)
        covered=flex is not None and flex['alive'] and not flex.get('weak') and flex['hp']>flex['max_hp']*.6 and on_outpost_card(flex,self.enemy,self)
        available=sentry is not None and sentry['alive'] and not sentry.get('weak') and not self.state.get('max_recovery',{}).get('7')
        if not self.controls(f'{self.team}_outpost') and self.controls(f'{self.enemy}_outpost') and covered and available:
            relay['home_sentry']=True
        relieved=self.controls(f'{self.team}_outpost') and guard is not None and guard['alive'] and not guard.get('weak') and guard['hp']>guard['max_hp']*.6 and on_outpost_card(guard,self.team,self) and not self.state.get('base_cover') and not self.state.get('max_recovery',{}).get('4')
        if relieved:relay['home_sentry']=False

def max_hold(robot,goal,ctx,tolerance=.18):
    if ctx.state.get('objective_relay',{}).get('home_sentry') and robot['alive'] and not robot.get('weak') and not ctx.state.get('max_recovery',{}).get(str(robot['slot'])):
        if robot['slot']==7:goal=max_local(ctx,(10.8,7.7))
        elif robot['slot']==3 and goal is not None and any(z['kind']=='central' and point_in_polygon(goal[0],goal[1],z['polygon']) for z in ctx.arena['zones']):
            goal=outpost_card_spot(ctx,ctx.enemy)
    return _relay_hold(robot,goal,ctx,tolerance)
