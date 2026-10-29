"""Public-geometry routing for serial legs; embedded by the Sol Max builder."""
import heapq
from sdk import ARENAS_BY_SEASON, _terrain_surface


class SerialRoadmap:
    def __init__(self, arena, team):
        self.arena, self.team = arena, team
        margin = .29
        self.boxes = []
        walls = [w for w in arena['obstacles'] if 'roof' not in w.get('id', '') or '_tunnel_roof' in w['id']]
        walls += [w for w in arena['forbidden'] if w['kind'] in ('base', 'dart_station', 'highway') or w.get('owner') not in (None, team)]
        self.circles=[(x,y,.62) for x,y in arena['outposts'].values()]
        walls += [dict(x=t['x'],y=t['y'],w=t['w'],h=t['h']) for t in arena['terrain'] if t['kind']=='bumps']
        for w in walls:
            angle = w.get('rotation', 0)
            self.boxes.append((w['x']+w['w']/2,w['y']+w['h']/2,
                w['w']/2+margin,w['h']/2+margin,math.cos(angle),math.sin(angle)))
        self.tiles = {}
        for t in arena['terrain']:
            for x in range(math.floor(t['x']),math.ceil(t['x']+t['w'])+1):
                for y in range(math.floor(t['y']),math.ceil(t['y']+t['h'])+1):
                    self.tiles.setdefault((x,y),[]).append(t)
        # Floor corridors, end ramps and both sides of the base body. No node
        # lies on the road humps or under a tunnel roof.
        red = [(1.1,7.5),(1.1,10.0),(2.9,10.0),(3.0,5.5),(3.0,10.4),(3.8,8.15),
            (4.4,10.0),(4.5,11.5),(4.5,13.5),(5.0,5.4),(7.9,5.9),(7.95,9.25),
            (8.0,7.5),(8.3,10.0),(8.3,11.5),(8.3,13.55),(10.8,13.55),(12.0,13.5),
            (12.0,12.2),(11.8,10.0),(11.4,10.55),(10.8,9.25),(11.5,9.7),(11.5,7.5),
            (11.8,5.3),(12.0,5.0),(16.2,3.0),(16.2,1.0),(19.7,1.0),(19.7,3.4),
            (20.0,4.85),(23.7,4.85),(26.9,4.4),(27.0,7.5)]
        self.nodes = list(dict.fromkeys(red+[(28-x,15-y) for x,y in red]))
        self.edges = [[] for _ in self.nodes]
        for i,a in enumerate(self.nodes):
            for j,b in enumerate(self.nodes):
                length=math.dist(a,b)
                if i!=j and length<7 and self.clear(a,b):
                    self.edges[i].append((j,length))
        self.special={}
        for a,b,kind in [((8.,7.5),(11.5,7.5),'highland'),
                         ((11.5,7.5),(8.,7.5),'highland'),
                         ((8.3,11.5),(8.3,13.55),'road'),
                         ((8.3,13.55),(8.3,11.5),'road')]:
            for start,end in ((a,b),((28-a[0],15-a[1]),(28-b[0],15-b[1]))):
                for point in (start,end):
                    if point in self.nodes:continue
                    n=len(self.nodes);self.nodes.append(point);self.edges.append([])
                    for old,other in enumerate(self.nodes[:-1]):
                        length=math.dist(point,other)
                        if length>=7:continue
                        if self.clear(point,other):self.edges[n].append((old,length))
                        if self.clear(other,point):self.edges[old].append((n,length))
                i,j=self.nodes.index(start),self.nodes.index(end)
                self.edges[i].append((j,math.dist(start,end)+1.8));self.special[i,j]=kind
        self.reverse=[[] for _ in self.nodes]
        for i,edges in enumerate(self.edges):
            for j,d in edges:self.reverse[j].append((i,d))
        self.costs = {}

    def height(self, x, y):
        h=0.
        for t in self.tiles.get((math.floor(x),math.floor(y)),[]):
            if t['x']<=x<=t['x']+t['w'] and t['y']<=y<=t['y']+t['h'] and point_in_polygon(x,y,t['polygon']):
                h=max(h,_terrain_surface(t,x,y))
        return h+min(y,15-y)*math.tan(math.radians(self.arena.get('floor_slope_deg',0)))

    def clear(self, a, b, escape=False):
        dx,dy=b[0]-a[0],b[1]-a[1]
        length2=dx*dx+dy*dy
        for x,y,radius in self.circles:
            if escape and math.dist(a,(x,y))<radius and (a[0]-x)*dx+(a[1]-y)*dy>=0:continue
            u=max(0.,min(1.,((x-a[0])*dx+(y-a[1])*dy)/max(1e-9,length2)))
            if math.hypot(a[0]+dx*u-x,a[1]+dy*u-y)<radius:return False
        for cx,cy,hw,hh,c,s in self.boxes:
            ax,ay=(a[0]-cx)*c+(a[1]-cy)*s,-(a[0]-cx)*s+(a[1]-cy)*c
            vx,vy=dx*c+dy*s,-dx*s+dy*c
            if escape and abs(ax)<hw and abs(ay)<hh:
                horizontal=abs(ax)-hw>=abs(ay)-hh
                outward=ax*vx>=0 if horizontal else ay*vy>=0
                if outward and max(abs(ax+vx)-hw,abs(ay+vy)-hh)>max(abs(ax)-hw,abs(ay)-hh)+.03:
                    continue
            lo,hi=0.,1.
            for p,v,half in ((ax,vx,hw),(ay,vy,hh)):
                if abs(v)<1e-9:
                    if not -half<p<half:lo=2.;break
                else:
                    low,high=sorted(((-half-p)/v,(half-p)/v));lo,hi=max(lo,low),min(hi,high)
            if lo<hi and hi>0 and lo<1:return False
        count=max(1,math.ceil(math.hypot(dx,dy)/.08))
        length=math.hypot(dx,dy)
        side=(-dy/max(1e-9,length)*.25,dx/max(1e-9,length)*.25)
        offsets=((0.,0.),side,(-side[0],-side[1]))
        previous=[self.height(a[0]+ox,a[1]+oy) for ox,oy in offsets]
        for i in range(1,count+1):
            h=[self.height(a[0]+dx*i/count+ox,a[1]+dy*i/count+oy) for ox,oy in offsets]
            spread_limit=.45 if escape and i<=4 else .17
            if any(n-p>.075 or p-n>(.45 if escape else .15) for n,p in zip(h,previous)) or max(h)-min(h)>spread_limit:return False
            previous=h
        return True

    def waypoint(self, start, goal, banned=()):
        if self.clear(start,goal,True):return goal
        blocked=set(banned)
        key=(tuple(round(v,3) for v in goal),tuple(sorted(blocked)))
        if key not in self.costs:
            costs={i:math.dist(p,goal) for i,p in enumerate(self.nodes) if self.clear(p,goal,True)}
            queue=[(d,i) for i,d in costs.items()];heapq.heapify(queue)
            while queue:
                d,i=heapq.heappop(queue)
                if d!=costs[i]:continue
                for j,edge in self.reverse[i]:
                    if (j,i) in self.special and f'{self.nodes[j]}:{self.nodes[i]}' in blocked:continue
                    if d+edge<costs.get(j,float('inf')):
                        costs[j]=d+edge;heapq.heappush(queue,(d+edge,j))
            if len(self.costs)>64:self.costs.clear()
            self.costs[key]=costs
        distances=self.costs[key]
        for (i,j),kind in self.special.items():
            if f'{self.nodes[i]}:{self.nodes[j]}' in blocked:continue
            if i in distances and j in distances and math.dist(start,self.nodes[i])<1.:
                edge=next(v for k,v in self.edges[i] if k==j)
                if distances[j]+edge<=distances[i]+.02:
                    return ('jump',self.nodes[i],self.nodes[j],kind)
        choices=sorted((math.dist(start,self.nodes[i])+v,i) for i,v in distances.items()
            if math.dist(start,self.nodes[i])>.32)
        for _,i in choices:
            if self.clear(start,self.nodes[i],True):return self.nodes[i]
        return None


_SERIAL_ROADMAPS = {team:SerialRoadmap(ARENAS_BY_SEASON['2027'],team) for team in ('red','blue')}
_original_serial_drive = drive
_opening_entry = highland_entry
_proven_homeward = max_homeward


def highland_entry(robot,ctx):
    if ctx.time<25:return _opening_entry(robot,ctx)
    memory=leg_memory(robot,ctx.obs,ctx.memory)
    x,_=local_point(ctx.team,(robot['x'],robot['y']))
    anchor=next((r for r in ctx.obs['robots'] if r['slot']==1),None)
    covering=robot['slot']==4 and (ctx.state.get('base_cover') or not ctx.controls(f'{ctx.team}_base')
        or anchor is None or not anchor['alive'] or anchor.get('weak') or anchor['hp']<anchor['max_hp']*.5 or ctx.state.get('guard_recover'))
    if robot.get('weak') or memory.get('entry_done') or covering:
        memory.pop('entry_wait',None)
        return None
    if not memory.get('entry') and x>=8.4:return None
    queue=ctx.state.setdefault('sortie_queue',{'pending':{},'since':ctx.time})
    queue['pending'][str(robot['slot'])]=ctx.time
    eligible=[r for r in ctx.obs['robots'] if r['alive'] and not r.get('weak') and r['role'] in ('infantry','sentry')
        and ctx.time-queue['pending'].get(str(r['slot']),-99)<.4]
    owner=next((r for r in eligible if r['slot']==queue.get('owner')),None)
    if owner is None and ctx.time-queue['since']>=.15:
        owner=min(eligible,key=lambda r:distance(r,max_local(ctx,(7.95,9.15))),default=None)
        if owner is not None:queue.update(owner=owner['slot'],owner_since=ctx.time)
    memory['entry_wait']=True
    if owner is None or owner['slot']!=robot['slot']:
        return {'move':(0,0),'leg_height':.245,'brake':True}
    if ctx.time-queue.get('owner_since',ctx.time)>40.:
        memory['entry_done']=True;memory.pop('entry_wait',None)
        queue['pending'].pop(str(robot['slot']),None);queue.pop('owner',None)
        return None
    if memory.get('sortie_ticket')!=queue.get('owner_since'):
        sx,sy=local_point(ctx.team,(robot['x'],robot['y']))
        memory.update(sortie_ticket=queue.get('owner_since'),sortie_from_supply=sx<4.2 and sy>10.5)
    if not memory.get('entry') and not memory.get('sortie_from_supply'):
        staging=max_local(ctx,(7.95,9.15))
        if distance(robot,staging)>.22:return drive(robot,staging,ctx.obs,ctx.memory,tolerance=.15)
        memory['entry']={'phase':1,'since':ctx.time,'began':ctx.time,'row':9.15}
    fields=_opening_entry(robot,ctx)
    if fields is None:
        queue['pending'].pop(str(robot['slot']),None);queue.pop('owner',None)
        memory.pop('entry_wait',None)
    return fields


def max_homeward(robot,goal,ctx):
    return max_hold(robot,goal,ctx)


def serial_escape(robot, obs, memory):
    """Latch an axial escape until the complete chassis has cleared a hump band."""
    m=leg_memory(robot,obs,memory)
    active=m.get('road_escape')
    if active:
        t=active['band'];x,y=robot['x'],robot['y']
        if not(t[0]-.55<x<t[2]+.55 and t[1]-.55<y<t[3]+.55) or obs['time']-active['began']>6.:
            m.pop('road_escape',None)
        else:
            return {'move':active['move'],'heading':active['heading'],'leg_height':.245,'brake':True,'power':200}
    escape=road_exit(robot,obs)
    if escape is None:return None
    band=next(t for t in obs['arena']['terrain'] if t['kind']=='bumps'
        and t['x']-.3<robot['x']<t['x']+t['w']+.3 and t['y']-.3<robot['y']<t['y']+t['h']+.3)
    m['road_escape']={'band':[band['x'],band['y'],band['x']+band['w'],band['y']+band['h']],
        'began':obs['time'],'move':escape['move'],'heading':escape['heading']}
    return escape


def drive(robot, goal, obs, memory, tolerance=.25):
    if not serial_leg(robot,obs):return _original_serial_drive(robot,goal,obs,memory,tolerance)
    if goal is None or distance(robot,goal)<tolerance:return {'move':(0,0),'brake':True,'leg_height':.245}
    escape=serial_escape(robot,obs,memory)
    if escape is not None:return escape
    start=(robot['x'],robot['y']);graph=_SERIAL_ROADMAPS[robot['team']]
    m=leg_memory(robot,obs,memory)
    locks=memory.setdefault('nav_locks',{})
    if m.get('nav_jump'):
        jump=m['nav_jump']
        end=jump['end']
        dx,dy=end[0]-jump['start'][0],end[1]-jump['start'][1]
        progress=((start[0]-jump['start'][0])*dx+(start[1]-jump['start'][1])*dy)/(dx*dx+dy*dy)
        rising=graph.height(*end)>graph.height(*jump['start'])+.1
        complete=(.82 if rising else .72) if jump['kind']=='highland' else .92
        if jump['kind']=='road' and progress>.83 and obs['time']-jump['began']<12.:
            jump.setdefault('landing',obs['time'])
            if obs['time']-jump['landing']<.7 or not robot.get('grounded') or math.hypot(robot['vx'],robot['vy'])>.2:
                return {'move':(0,0),'heading':jump.get('heading',robot['heading']),'leg_height':.245,'brake':True}
            progress=complete+1.
        if progress>complete or obs['time']-jump['began']>12.:
            if progress<=complete:m.setdefault('banned_jumps',{})[jump['lock']]=obs['time']+30.
            locks.pop(jump['lock'],None)
            m.pop('nav_jump',None)
        else:
            locks[jump['lock']]={'slot':robot['slot'],'until':obs['time']+3.}
            course=math.atan2(dy,dx)
            heading=jump.setdefault('heading',min((course,wrap(course+math.pi)),key=lambda h:abs(wrap(h-robot['heading']))))
            if jump['phase']==-1:
                fields=pointed_move(robot,jump['prep'],1.6)
                fields.update(leg_height=.245,brake=True)
                if distance(robot,jump['prep'])<.18:
                    jump.update(phase=0,settled=obs['time'])
                return fields
            if jump['phase']==0:
                if abs(wrap(heading-robot['heading']))<.12 and obs['time']-jump.get('settled',jump['began'])>.7:
                    jump['phase']=1
                return {'move':(0,0),'heading':heading,'leg_height':.12,'brake':True}
            fields=pointed_move(robot,end,2.2)
            fields.update(heading=heading,leg_height=.12,brake=True,power=180)
            rising=graph.height(*end)>graph.height(*jump['start'])+.1
            takeoff=(.13 if rising else .23) if jump['kind']=='highland' else (.35 if rising else .15)
            if progress>takeoff and robot.get('grounded') and obs['time']-m['last_jump']>1.1 and (jump['kind']!='road' or not jump.get('launched')):
                fields['jump']=1.;m['last_jump']=obs['time'];jump['launched']=True
            return fields
    banned=m.setdefault('banned_jumps',{})
    for key in list(banned):
        if banned[key]<=obs['time']:del banned[key]
    blocked=set(banned)
    local_goal=local_point(robot['team'],goal)
    if obs['time']>=25 or local_goal[0]<9.2:
        # The fast opening is a controlled jump from a known pose. Later
        # sorties use end ramps instead of repeatedly attacking the tall rim.
        blocked.update(f'{graph.nodes[i]}:{graph.nodes[j]}' for (i,j),kind in graph.special.items() if kind=='highland')
    waypoint=graph.waypoint(start,goal,blocked)
    if waypoint is not None and waypoint[0]=='jump':
        _,a,b,kind=waypoint
        lock=f'{a}:{b}'
        held=locks.get(lock,{})
        if held.get('slot') not in (None,robot['slot']) and held.get('until',0)>obs['time']:
            return {'move':(0,0),'leg_height':.245,'brake':True}
        owner='red' if (a[0] if a[0]<9. else b[0])<14 else 'blue'
        offset={3:-.6,4:.6,7:0.}.get(robot['slot'],0.)*(1 if owner=='red' else -1)
        if kind=='highland':a=(a[0],a[1]+offset);b=(b[0],b[1]+offset)
        descending=graph.height(*a)>graph.height(*b)+.1
        length=math.dist(a,b)
        prep=(a[0]-(b[0]-a[0])/length*.65,a[1]-(b[1]-a[1])/length*.65) if descending and kind=='highland' else a
        locks[lock]={'slot':robot['slot'],'until':obs['time']+3.}
        m['nav_jump']={'start':a,'end':b,'prep':prep,'kind':kind,'phase':-1,'began':obs['time'],'lock':lock}
        fields=pointed_move(robot,prep,1.6);fields.update(leg_height=.245,brake=True);return fields
    if waypoint is None:
        # A step up to the road has no continuous ramp from this side. The
        # controller uses the same bounded crouch/run-up as the highland entry.
        return _original_serial_drive(robot,goal,obs,memory,tolerance)
    fields=pointed_move(robot,waypoint,2.5)
    fields.update(leg_height=.245,brake=True)
    if math.hypot(robot['vx'],robot['vy'])<.4 and math.hypot(*fields['move'])>.2:fields['power']=180
    return fields


_route_drive=drive


def drive(robot,goal,obs,memory,tolerance=.25):
    """A bounded axial backoff also recovers a chassis already touching a rim."""
    if not serial_leg(robot,obs):
        fields=_route_drive(robot,goal,obs,memory,tolerance)
        design=obs['robot_models'].get(str(robot.get('model_slot')), {})
        if design.get('chassis_type')=='swerve':fields.setdefault('heading',robot['heading'])
        return fields
    m=memory.setdefault('nav_stall',{}).setdefault(str(robot['slot']),{'trail':[]})
    if obs['time']<m.get('until',-1):
        return {'move':m['move'],'heading':m['heading'],'leg_height':.245,'brake':True,'power':200}
    fields=_route_drive(robot,goal,obs,memory,tolerance)
    if goal is None or distance(robot,goal)<.6:
        m['trail']=[];return fields
    trail=m['trail'];trail.append((obs['time'],robot['x'],robot['y'],robot['heading']))
    while trail and obs['time']-trail[0][0]>2.5:trail.pop(0)
    if trail and obs['time']-trail[0][0]>2.3 and distance(robot,trail[0][1:3])<.10 and abs(wrap(robot['heading']-trail[0][3]))<.12:
        h=robot['heading'];graph=_SERIAL_ROADMAPS[robot['team']];start=(robot['x'],robot['y'])
        move=fields.get('move',(0,0));dot=move[0]*math.cos(h)+move[1]*math.sin(h)
        preferred=-1 if dot>=0 else 1
        def escape_score(sign):
            end=(start[0]+sign*.9*math.cos(h),start[1]+sign*.9*math.sin(h))
            bounded=.3<end[0]<27.7 and .3<end[1]<14.7
            reverse_bonus=.5*(sign==preferred) if abs(dot)>.12 else 0.
            return 4.*(bounded and graph.clear(start,end,True))+reverse_bonus+.2*(math.dist(start,goal)-math.dist(end,goal))
        sign=max((-1,1),key=escape_score);pace=1.4/robot['speed_reference_mps']
        m.update(move=(sign*pace*math.cos(h),sign*pace*math.sin(h)),heading=h,until=obs['time']+.65,trail=[])
        jump=leg_memory(robot,obs,memory).pop('nav_jump',None)
        if jump:
            memory.get('nav_locks',{}).pop(jump['lock'],None)
            leg_memory(robot,obs,memory).setdefault('banned_jumps',{})[jump['lock']]=obs['time']+20.
        return {'move':m['move'],'heading':h,'leg_height':.245,'brake':True,'power':200}
    return fields


# A bounded crouch and hop frees a healthy chassis straddling a tall rim.
_unwedge_parent=drive

def drive(robot,goal,obs,memory,tolerance=.25):
    if not serial_leg(robot,obs) or robot.get('weak') or goal is None:return _unwedge_parent(robot,goal,obs,memory,tolerance)
    m=leg_memory(robot,obs,memory);now=obs['time'];jump=m.get('rim_hop')
    g=_SERIAL_ROADMAPS[robot['team']]
    if jump and now-jump['since']>2.7:m.pop('rim_hop',None);jump=None
    if not jump:
        fields=_unwedge_parent(robot,goal,obs,memory,tolerance)
        stall=memory.get('nav_stall',{}).get(str(robot['slot']),{})
        heights=[g.height(robot['x']+dx,robot['y']+dy) for dx,dy in ((0,0),(.3,0),(-.3,0),(0,.3),(0,-.3))]
        # Road ramps have their own jump state. This escape is only for a
        # chassis touching a central-highland kerb, including its diagonal
        # end sections, where an axial backoff may not clear the edge.
        near_side=False
        for wall in obs['arena']['obstacles']:
            if not wall['id'].startswith('central_') or 'kerb' not in wall['id']:continue
            angle=wall.get('rotation',0);c,q=math.cos(angle),math.sin(angle)
            dx,dy=robot['x']-wall['x']-wall['w']/2,robot['y']-wall['y']-wall['h']/2
            ax,ay=dx*c+dy*q,-dx*q+dy*c
            if math.hypot(max(0.,abs(ax)-wall['w']/2),max(0.,abs(ay)-wall['h']/2))<.45:
                near_side=True;break
        # A hull resting on an end ramp can be grounded while both wheel probes carry
        # no load. Axial backoffs then have no traction; crouch and hop to put the wheels
        # back down, using the same bounded recovery as a kerb.
        unloaded = (robot.get('grounded') and .4 < robot.get('upright',1.) < .8
            and sum(robot.get('wheel_loads_n',(1.,))) < 1.)
        if stall.get('until',0)>now and now-m.get('rim_hop_last',-99)>20 and (unloaded or near_side and max(heights)-min(heights)>.18):
            m['rim_hop']=jump={'since':now,'goal':goal};m['rim_hop_last']=now
        else:return fields
    fields=pointed_move(robot,jump['goal'],2.2)
    fields.update(leg_height=.12,brake=True,power=200)
    if now-jump['since']<.7:fields['move']=(0,0)
    elif robot.get('grounded') and now-m['last_jump']>1.1:
        fields['jump']=1.;m['last_jump']=now
    return fields
