"""Detailed chapter 4 assets. Loaded by build_assets.py with its mesh helpers."""
import random
import bmesh


def chapter4_materials():
    global FIELD, ROAD, KERB, RED_PAINT, BLUE_PAINT, WHITE_PAINT
    FIELD=mat('FieldBlack',(.025,.029,.032),.04,.96)
    ROAD=mat('HighlandAsphalt',(.17,.185,.19),.04,.88)
    KERB=mat('ProtectiveMetal',(.25,.27,.25),.48,.62)
    RED_PAINT=mat('RedFieldPaint',(.68,.065,.045),.04,.7,.15)
    BLUE_PAINT=mat('BlueFieldPaint',(.035,.15,.66),.04,.7,.15)
    WHITE_PAINT=mat('WhiteFieldPaint',(.7,.73,.71),0,.85)
    global SIDE
    SIDE=mat('ConcreteSide',(.30,.30,.28),.05,.9)
    # Repeatable asphalt texture, authored procedurally and embedded in the GLB.
    rng=random.Random(2026)
    texture=bpy.data.images.new('ArenaAsphalt',width=128,height=128)
    pixels=[]
    for _ in range(128**2):
        v=rng.uniform(.72,1.0);pixels.extend([v*.42,v*.445,v*.46,1])
    texture.pixels=pixels;texture.pack()
    tree=ROAD.node_tree
    image_node=tree.nodes.new('ShaderNodeTexImage');image_node.image=texture
    tree.links.new(image_node.outputs['Color'],tree.nodes.get('Principled BSDF').inputs['Base Color'])


def floor_z(y):
    return min(y,15-y)*math.tan(math.radians(1.5))


def c4_height(t,x,y):
    if t['kind']=='ramp':
        a,b=t['ramp_start'],t['ramp_end'];dx,dy=b[0]-a[0],b[1]-a[1]
        p=max(0,min(1,((x-a[0])*dx+(y-a[1])*dy)/(dx*dx+dy*dy)))
        return t.get('base_elevation',0)+(t['elevation']-t.get('base_elevation',0))*p
    if t['kind']=='bumps':
        phase=((x-t['x'])/t['bump_pitch'])%1
        return t['elevation']+t['bump_height']*(1-math.cos(math.tau*phase))/2
    if t.get('edge_ramp_m',0):
        p=t['polygon'];d=min(abs((x-a[0])*(b[1]-a[1])-(y-a[1])*(b[0]-a[0]))/math.dist(a,b) for a,b in zip(p,p[1:]+p[:1]))
        return t.get('base_elevation',0)+(t['elevation']-t.get('base_elevation',0))*min(1,d/t['edge_ramp_m'])
    return t['elevation']


def c4_inside(x,y,p):
    inside=False
    for a,b in zip(p,p[1:]+p[:1]):
        if (a[1]>y)!=(b[1]>y) and x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:inside=not inside
    return inside


def c4_ground(arena,x,y):
    return floor_z(y)+max([0]+[c4_height(t,x,y) for t in arena['terrain'] if c4_inside(x,y,t['polygon'])])


def c4_mesh(name,vertices,faces,material,parent):
    mesh=bpy.data.meshes.new(name);mesh.from_pydata(vertices,[],faces);mesh.update()
    obj=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(obj);finish(obj,name,material,parent)
    bm=bmesh.new();bm.from_mesh(mesh);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(mesh);bm.free()
    uv=mesh.uv_layers.new(name='FieldUV')
    for face in mesh.polygons:
        for index in face.loop_indices:
            v=mesh.vertices[mesh.loops[index].vertex_index].co;uv.data[index].uv=(v.x*.4,v.y*.4)
    return obj


def c4_prism(name,points,heights,material,parent,bottom=None):
    vertices=[(p[0]-14,7.5-p[1],z) for p,z in zip(points,heights)]
    faces=[tuple(reversed(range(len(points))))]
    if bottom is not None:
        n=len(points);vertices.extend([(p[0]-14,7.5-p[1],floor_z(p[1])+bottom) for p in points])
        faces.append(tuple(range(n,2*n)))
        faces.extend([(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)])
    return c4_mesh(name,vertices,faces,material,parent)


def c4_sides(name,points,heights,bottom,material,parent):
    """Vertical side faces of a terrain prism down to `bottom` above the tilted floor."""
    n=len(points);vertices=[(p[0]-14,7.5-p[1],z) for p,z in zip(points,heights)]+[(p[0]-14,7.5-p[1],floor_z(p[1])+bottom) for p in points]
    faces=[(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
    return c4_mesh(name,vertices,faces,material,parent)


def c4_stepped_ramp(arena,t,material,side,parent,step=.025):
    """The 23 deg trapezoid slope is built as fine stairs in the field (footage 10:35):
    bands parallel to the edge, each a riser step higher. Physics keeps the smooth ramp."""
    h0,h1=t.get('base_elevation',0),t['elevation'];count=max(2,round((h1-h0)/step))
    hi0,hi1,lo1,lo0=[Vector((*p,0)) for p in t['polygon']]
    for k in range(count):
        f0,f1=k/count,(k+1)/count
        band=[lo0+(hi0-lo0)*f0,lo1+(hi1-lo1)*f0,lo1+(hi1-lo1)*f1,lo0+(hi0-lo0)*f1]
        band=[[v.x,v.y] for v in band];z=h0+(h1-h0)*f1
        c4_prism('RibbedStep',band,[floor_z(y)+z for x,y in band],material,parent)
        c4_sides('RibbedRiser',band,[floor_z(y)+z for x,y in band],0,side,parent)


def c4_paint(arena,points,material,parent,width=.025,closed=False):
    vertices,faces=[],[]
    for a,b in zip(points,points[1:]+([points[0]] if closed else [])):
        dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
        if length<.001:continue
        ox,oy=-dy/length*width/2,dx/length*width/2
        poly=[[a[0]+ox,a[1]+oy],[b[0]+ox,b[1]+oy],[b[0]-ox,b[1]-oy],[a[0]-ox,a[1]-oy]]
        index=len(vertices)
        mx,my=(a[0]+b[0])/2,(a[1]+b[1])/2
        level=max(c4_ground(arena,mx+ox,my+oy),c4_ground(arena,mx-ox,my-oy))-floor_z(my)
        vertices.extend([(x-14,7.5-y,floor_z(y)+level+.008) for x,y in poly]);faces.append((index,index+3,index+2,index+1))
    if vertices:c4_mesh('CourtPaint',vertices,faces,material,parent)


def c4_text(arena,text,x,y,size,material,parent,angle=0):
    curve=bpy.data.curves.new('FieldMark','FONT');curve.body=text;curve.size=size;curve.align_x='CENTER';curve.align_y='CENTER';curve.extrude=.0005
    obj=bpy.data.objects.new('FieldMark',curve);bpy.context.collection.objects.link(obj)
    obj.location=(x-14,7.5-y,c4_ground(arena,x,y)+.009);obj.rotation_euler[2]=angle;obj.parent=parent;curve.materials.append(material)
    bpy.context.view_layer.objects.active=obj;obj.select_set(True);bpy.ops.object.convert(target='MESH');obj.select_set(False)


def c4_fence(parent):
    # Open steel mesh preserves sight lines and gives the full 2.4 m perimeter.
    vertices,faces=[],[]
    def rod(x,y,z,w,d,h):
        i=len(vertices)
        vertices.extend([(x+a*w/2,y+b*d/2,z+c*h/2) for a,b,c in [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]])
        faces.extend([tuple(i+k for k in f) for f in [(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]])
    for y in [-7.56,7.56]:
        for i in range(94):rod(-14+i*.3,y,1.2,.012,.015,2.4)
        for j in range(9):rod(0,y,j*.3,28,.015,.012)
        for i in range(15):rod(-14+i*2,y,1.2,.07,.1,2.4)
        rod(0,y,2.4,28,.065,.045);rod(0,y,.08,28,.13,.16)
    for x in [-14.06,14.06]:
        for i in range(51):rod(x,-7.5+i*.3,1.2,.015,.012,2.4)
        for j in range(9):rod(x,0,j*.3,.015,15,.012)
        for i in range(9):rod(x,-7.5+i*1.875,1.2,.1,.07,2.4)
        rod(x,0,2.4,.065,15,.045);rod(x,0,.08,.13,15,.16)
    c4_mesh('SteelMeshFence',vertices,faces,DARK,parent)



def c4_local_prism(name,points,depth,material,parent,axis='z',offset=0,bevel=0):
    """Closed prism from a 2D outline, extruded along a local axis ('x','y' or 'z')."""
    n=len(points);vertices=[]
    for h in (offset,offset+depth):
        for a,b in points:
            vertices.append({'z':(a,b,h),'x':(h,a,b),'y':(a,h,b)}[axis])
    faces=[tuple(reversed(range(n))),tuple(range(n,2*n))]+[(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
    obj=c4_mesh(name,vertices,faces,material,parent)
    if bevel:
        modifier=obj.modifiers.new('MachinedEdges','BEVEL');modifier.width=bevel;modifier.segments=2;modifier.limit_method='ANGLE'
        bpy.context.view_layer.objects.active=obj;bpy.ops.object.modifier_apply(modifier=modifier.name)
    return obj


def c4_ring(name,r_in,r_out,depth,material,parent,offset=0,segments=48,start=0,sweep=math.tau):
    """Annulus (or arc band) in the local YZ plane, extruded along +X from offset."""
    closed=sweep>=math.tau-1e-9;count=segments if closed else segments+1
    vertices=[];faces=[]
    for h in (offset,offset+depth):
        for r in (r_in,r_out):
            for i in range(count):
                a=start+sweep*i/segments;vertices.append((h,r*math.cos(a),r*math.sin(a)))
    m=count
    def v(layer,ring,i):return layer*2*m+ring*m+i%m
    for i in range(segments):
        j=i+1
        faces.append((v(1,0,i),v(1,1,i),v(1,1,j),v(1,0,j)))
        faces.append((v(0,0,j),v(0,1,j),v(0,1,i),v(0,0,i)))
        faces.append((v(0,1,i),v(0,1,j),v(1,1,j),v(1,1,i)))
        if r_in>0:faces.append((v(0,0,j),v(0,0,i),v(1,0,i),v(1,0,j)))
    if not closed:
        for i in (0,segments):
            faces.append((v(0,0,i),v(1,0,i),v(1,1,i),v(0,1,i)))
    return c4_mesh(name,vertices,faces,material,parent)


def c4_strip(name,points,width,depth,material,parent,offset=0,closed=False):
    """Flat lamp/paint strip following a YZ polyline, extruded along +X."""
    vertices=[];faces=[]
    pairs=list(zip(points,points[1:]+([points[0]] if closed else [])))
    for a,b in pairs:
        dy,dz=b[0]-a[0],b[1]-a[1];length=math.hypot(dy,dz)
        if length<1e-6:continue
        oy,oz=-dz/length*width/2,dy/length*width/2;i=len(vertices)
        quad=[(a[0]+oy,a[1]+oz),(b[0]+oy,b[1]+oz),(b[0]-oy,b[1]-oz),(a[0]-oy,a[1]-oz)]
        for h in (offset,offset+depth):vertices.extend((h,y,z) for y,z in quad)
        faces.extend([(i+3,i+2,i+1,i),(i+4,i+5,i+6,i+7),(i,i+1,i+5,i+4),(i+1,i+2,i+6,i+5),(i+2,i+3,i+7,i+6),(i+3,i,i+4,i+7)])
    return c4_mesh(name,vertices,faces,material,parent)


def c4_text_x(text,size,location,material,parent,depth=.002):
    """Text facing +X, used for small printed and lamp logos."""
    curve=bpy.data.curves.new('Logo','FONT');curve.body=text;curve.size=size;curve.align_x='CENTER';curve.align_y='CENTER';curve.extrude=depth
    obj=bpy.data.objects.new('Logo',curve);bpy.context.collection.objects.link(obj)
    obj.parent=parent;obj.location=location;obj.rotation_euler=(math.pi/2,0,math.pi/2);curve.materials.append(material)
    bpy.ops.object.select_all(action='DESELECT');bpy.context.view_layer.objects.active=obj;obj.select_set(True);bpy.ops.object.convert(target='MESH');obj.select_set(False)
    return obj


def energy_unit(name,parent,location=(0,0,0),rotation=(0,0,0),core=None):
    """Figure 4-37: 150 mm unit, Ø95 top cap, Ø80 base, six Ø5 rods round a Ø60 core."""
    unit=empty(name,parent);unit.location=location;unit.rotation_euler=rotation
    shell=globals().get('UNIT_SHELL') or KERB
    bpy.ops.mesh.primitive_cone_add(vertices=24,radius1=.040,radius2=.0425,depth=.025,location=(0,0,.0125))
    finish(bpy.context.object,'UnitBase',shell,unit,.003)
    cyl('UnitLowerCollar',.0455,.015,(0,0,.0325),shell,unit,vertices=24)
    cyl('UnitTopCap',.0475,.03,(0,0,.135),shell,unit,vertices=24)
    cyl('UnitUpperCollar',.0455,.012,(0,0,.114),shell,unit,vertices=24)
    cyl('UnitCore',.030,.068,(0,0,.074),core or WHITE,unit,vertices=20)
    for i in range(6):
        a=i*math.tau/6;cyl('UnitRod',.0025,.072,(.034*math.cos(a),.034*math.sin(a),.074),STEEL,unit,vertices=8)
    for i in range(4):
        a=i*math.tau/4+math.pi/4;box('UnitKey',(.006,.004,.012),(.047*math.cos(a),.047*math.sin(a),.135),DARK,unit,0).rotation_euler[2]=a
    return unit


def rune_gantry(arena,fixture,root):
    """Pedestal, post feet, posts, crossbeam and gearbox of figures 4-28/4-29.
    Local frame: +X is the shaft (blue side), +Y runs along the gantry, Z up from the plinth."""
    g=fixture;yaw=g['yaw']
    frame=empty('RuneGantry',root)
    frame.location=(0,0,floor_z(7.5)+g['plinth_top_m']);frame.rotation_euler[2]=-yaw
    # Blender maps field y to -Y, so the field u axis is local -Y; the gantry is symmetric.
    L,D,H=g['pedestal_half_length_m'],g['pedestal_half_depth_m'],g['pedestal_height_m']
    c=.07
    c4_local_prism('RunePedestal',[(-D,0),(D,0),(D,H-c),(D-c,H),(-D+c,H),(-D,H-c)],2*L,KERB,frame,'y',-L,.006)
    box('PedestalSkirt',(2*D+.04,2*L,.03),(0,0,.015),DARK,frame,.004)
    for sx in (-1,1):
        box('PedestalPanelSeam',(.004,2*L-.1,.16),(sx*(D+.001),0,.13),DARK,frame,0)
        for sy in (-.6,-.2,.2,.6):box('PedestalAccessPanel',(.003,.32,.12),(sx*(D+.002),sy*L,.14),STEEL,frame,.002)
    # Core stages: X and Y rails under each team's technology core travel (5.3.3 ranges).
    for team,sign in (('red',-1),('blue',1)):
        f=arena['assembly_frames'][team]
        # Frame origin sits on the pedestal face; +X_team = sign * local X; Y_team = sign * local -Y.
        for yy in (-.13,.29):
            p0=(sign*(D-.34),-sign*yy,H+.008);p1=(sign*(D-.02),-sign*yy,H+.008)
            beam('CoreRailX',p0,p1,.016,STEEL,frame)
        for xx in (-.34,-.02):
            beam('CoreRailY',(sign*(D+xx),sign*.15,H+.024),(sign*(D+xx),-sign*.31,H+.024),.014,ROBOT_GRAPHITE if 'ROBOT_GRAPHITE' in globals() else DARK,frame)
        box('CoreDrive',(.08,.10,.05),(sign*(D-.40),-sign*.08,H+.025),DARK,frame,.006)
        box('CoreCableTray',(.05,.5,.025),(sign*(D-.45),-sign*.05,H+.012),DARK,frame,.004)
    post=g['post_center_m'];size=g['post_size_m'];top=g['post_top_m'];hub=g['hub_height_m']
    fo,fd,fh=g['foot_outer_m'],g['foot_half_depth_m'],g['foot_height_m']
    for side in (-1,1):
        # Trapezoid foot: wide on the plinth, stepping in toward the post.
        foot=empty('PostFoot',frame);foot.location=(0,side*(L+fo)/2,0)
        half=(fo-L)/2
        c4_local_prism('PostFootBody',[(-half,0),(half,0),(half*.72,fh),(-half*.9,fh)] if side>0 else [(-half,0),(half,0),(half*.9,fh),(-half*.72,fh)],2*fd,KERB,foot,'x',-fd,.006)
        foot.rotation_euler[2]=0
        for bx in (-1,1):
            for by in (-1,1):cyl('AnchorBolt',.012,.02,(bx*(fd-.06),side*(L+fo)/2+by*(half-.06),.01),STEEL,frame,vertices=8)
        y=side*post
        box('PostBasePlate',(.26,.26,.02),(0,y,fh+.01),STEEL,frame,.004)
        box('GantryPost',(size,size,top-fh),(0,y,(top+fh)/2),DARK,frame,.01)
        for face in (-1,1):
            box('PostChannel',(.004,size*.42,top-fh-.3),(face*(size/2+.001),y,(top+fh)/2),ROBOT_GRAPHITE if 'ROBOT_GRAPHITE' in globals() else STEEL,frame,0)
            box('PostSideChannel',(size*.42,.004,top-fh-.3),(0,y+face*(size/2+.001),(top+fh)/2),ROBOT_GRAPHITE if 'ROBOT_GRAPHITE' in globals() else STEEL,frame,0)
        # Angled cap and inward bracket at the shaft height (figure 4-29).
        c4_local_prism('PostCap',[(-size/2,0),(size/2,0),(size/2,.05),(-size/2,.12)] if side<0 else [(-size/2,0),(size/2,0),(size/2,.12),(-size/2,.05)],size,DARK,frame,'x',-size/2).location=(0,y,top)
        inner=side*(post-size/2)
        c4_local_prism('BeamGusset',[(0,0),(-side*.22,0),(0,.22)] if side>0 else [(0,0),(-side*.22,0),(0,.22)],.03,DARK,frame,'x',-.015).location=(0,inner,hub+g['crossbeam_height_m']/2)
        c4_local_prism('BeamGussetLow',[(0,0),(-side*.18,0),(0,-.18)],.03,DARK,frame,'x',-.015).location=(0,inner,hub-g['crossbeam_height_m']/2)
        box('CableConduit',(.03,.03,hub-fh-.1),(-size/2-.03,y-side*.04,(hub+fh)/2),RUBBER,frame,.006)
    inner=post-size/2
    box('GantryCrossbeam',(g['crossbeam_depth_m'],2*inner,g['crossbeam_height_m']),(0,0,hub),DARK,frame,.008)
    for k in range(-4,5):
        if k:box('CrossbeamRib',(g['crossbeam_depth_m']+.012,.012,g['crossbeam_height_m']+.012),(0,k*inner/5,hub),STEEL,frame,.002)
    gx,gy,gz=g['gearbox_m']
    box('RuneGearbox',(gy,gx,gz),(0,0,hub),DARK,frame,.016)
    for sx in (-1,1):
        cyl('ShaftBearing',.07,.03,(sx*(gy/2+.015),0,hub),STEEL,frame,(0,math.pi/2,0),24)
        for k in range(6):
            a=k*math.tau/6;cyl('BearingBolt',.008,.01,(sx*(gy/2+.032),.05*math.cos(a),hub+.05*math.sin(a)),STEEL,frame,(0,math.pi/2,0),8)
    cyl('RuneMotor',.055,.16,(0,0,hub+gz/2+.08),STEEL,frame,vertices=24)
    for k in range(8):
        cyl('MotorFin',.062,.006,(0,0,hub+gz/2+.02+k*.018),DARK,frame,vertices=24)
    box('MotorDriver',(.10,.12,.05),(0,.16,hub+gz/2+.025),DARK,frame,.006)
    return frame


def dart_station(fixture,root,color):
    """Figure 4-13: dart launch station, closed. Grey frame with sloped sides, black lid
    with the R mark, team light strips on the front edges; it faces into the field (+X)."""
    x,y=fixture['point']
    local=empty('DartStation',root);local.location=(x-14,7.5-y,floor_z(y));local.rotation_euler[2]=-fixture['yaw']
    lid=mat('DartLidBlack',(.025,.027,.03),.3,.5)
    for side in (-1,1):
        c4_local_prism('DartSideFrame',[(-.52,0),(.52,0),(.40,1.05),(.05,1.32),(-.52,1.32)],.12,KERB,local,'y',side*.46-(.12 if side>0 else 0),.008)
        c4_strip('DartFrontLight',[(side*.40-.02,.12),(side*.40-.02,1.0)],.03,.006,color,local,offset=.52)
    box('DartBackWall',(.06,.80,1.32),(-.49,0,.66),KERB,local,.006)
    box('DartBase',(1.04,.80,.12),(0,0,.06),DARK,local,.008)
    # Closed lid: flat over the back, then down the sloped front of the roof (37.6 deg).
    box('DartLidTop',(.60,.80,.05),(-.23,0,1.345),lid,local,.01)
    logo=c4_text_x('R',.30,(0,0,0),WHITE,local);logo.location=(-.25,0,1.372);logo.rotation_euler=(0,0,math.pi/2)
    front=empty('DartLidFront',local);front.location=(.05,0,1.32);front.rotation_euler[1]=math.radians(37.6)
    box('DartLidPanel',(.46,.80,.05),(.22,0,.025),lid,front,.01)
    box('DartGate',(.02,.78,.86),(.50,0,.55),lid,local,.006)
    box('DartStatusLamp',(.02,.08,.03),(.51,0,1.0),color,local,.002)
    return local


def resource_station(fixture,root,color):
    """Figure 4-20/4-21: 1910 x 1530 x 1530 mm cabinet, open to the field (+Y)."""
    x,y=fixture['point']
    local=empty('ResourceStation',root);local.location=(x-14,7.5-y,floor_z(y));local.rotation_euler[2]=-fixture['yaw']
    depth=1.53;front=depth/2;back=-depth/2
    box('ResourceFloor',(1.91,depth,.05),(0,0,.025),DARK,local,.006)
    # Side walls: 300 mm vertical front, then a slant back to the roof line.
    profile=[(front,0),(front,.30),(front-.05,.30),(front-.62,1.53),(back,1.53),(back,0)]
    for side in (-1,1):
        c4_local_prism('ResourceSideWall',profile,.155,KERB,local,'x',.8 if side>0 else -.955,.008)
        # Red/blue status lamps follow the slanted front edge on both wall faces.
        for face in (.8-.004,.955) if side>0 else (-.955-.002,-.8-.002):
            c4_strip('ResourceStatusLamp',[(front-.10,.38),(front-.64,1.46)],.04,.006,color,local,offset=face)
        box('WallCapRail',(.17,depth-.6,.03),(side*.8775,back+(depth-.6)/2,1.53),STEEL,local,.004)
    box('ResourceBackWall',(1.6,.06,1.53),(0,back+.03,.765),KERB,local,.008)
    box('ResourceRoofBeam',(1.6,.12,.10),(0,back+.42,1.47),DARK,local,.008)
    # Front baffle: 300 mm high, 150 mm deep with its 50 mm top lip (figure 4-20 side view).
    c4_local_prism('ResourceBaffle',[(front-.15,0),(front,0),(front,.25),(front-.05,.30),(front-.15,.30)],1.6,KERB,local,'x',-.8,.006).rotation_euler[2]=0
    box('BaffleKick',(1.6,.012,.06),(0,front-.006,.04),DARK,local,.002)
    # Dispenser: a SCARA arm from the back column presents a six-unit carousel at 600 mm.
    box('DispenserCabinet',(.9,.45,.55),(0,back+.3,.30),DARK,local,.012)
    cyl('ScaraColumn',.06,1.0,(0,back+.32,.85),STEEL,local,vertices=24)
    box('ScaraShoulder',(.16,.16,.12),(0,back+.32,1.30),DARK,local,.012)
    beam('ScaraLink1',(0,back+.32,1.30),(.18,back+.70,1.30),.07,DARK,local)
    cyl('ScaraElbow',.055,.10,(.18,back+.70,1.30),STEEL,local,vertices=20)
    beam('ScaraLink2',(.18,back+.70,1.30),(0,.30,1.22),.06,DARK,local)
    beam('DispenserDrop',(0,.30,1.22),(0,.30,.72),.05,STEEL,local)
    hub=empty('UnitCarousel',local);hub.location=(0,.36,.60)
    cyl('CarouselHub',.06,.06,(0,0,0),DARK,hub,(math.pi/2,0,0),6)
    cyl('CarouselPlate',.17,.02,(0,-.04,0),STEEL,hub,(math.pi/2,0,0),6)
    for k in range(6):
        a=k*math.tau/6+math.pi/6
        energy_unit('DispenserUnit',hub,(.06*math.cos(a),0,.06*math.sin(a)),(0,math.pi/2-a,0))
        beam('UnitClampArm',(.03*math.cos(a),-.02,.03*math.sin(a)),(.13*math.cos(a),-.02,.13*math.sin(a)),.012,DARK,hub)
    available=empty('AvailableUnit_'+fixture['team'],local);energy_unit('ReadyUnit',available,(0,.515,.60),(0,math.pi/2,0))
    box('ScaraHeadCamera',(.05,.06,.04),(0,.30,1.28),GLASS,local,.004)
    return local


def chapter4_rune_face():
    """One lamp face of the energy mechanism: hub, five lamp arms and Ø300 targets.
    +X faces the team, arm 0 points up at zero rotor angle; lamps are per-arm meshes."""
    reset();root=empty('RuneFace');rotor=empty('RuneRotor',root)
    frame=mat('RuneFrameGraphite',(.035,.04,.045),.35,.55)
    face=mat('RuneTargetFace',(.06,.065,.07),.1,.8)
    groove=mat('RuneTargetRing',(.11,.115,.12),.2,.6)
    lamp=lambda n:mat(n,(.85,.15,.12),0,.4,2.5)
    lamps={k:lamp(k) for k in ('TeamRuneFrame','TeamRuneArrow','TeamRuneTarget','TeamRuneRing','TeamRuneLogo')}
    cyl('RuneShaftStub',.035,.20,(-.15,0,0),STEEL,rotor,(0,math.pi/2,0),24)
    hub=[(.13*math.cos(a),.13*math.sin(a)) for a in [k*math.tau/10+math.pi/10 for k in range(10)]]
    c4_local_prism('RuneHub',hub,.065,frame,rotor,'x',-.05,.006)
    c4_local_prism('RuneHubCap',[(.09*math.cos(a),.09*math.sin(a)) for a in [k*math.tau/10 for k in range(10)]],.012,groove,rotor,'x',.015)
    cyl('RuneLogoDisc',.053,.006,(.030,0,0),DARK,rotor,(0,math.pi/2,0),40)
    c4_text_x('R',.07,(.0335,0,-.002),lamps['TeamRuneLogo'],rotor)
    c4_ring('RuneHubLamp',.095,.103,.004,lamps['TeamRuneFrame'],rotor,.015,40)
    for k in range(10):
        a=k*math.tau/10;cyl('HubBolt',.006,.006,(.027,.112*math.cos(a),.112*math.sin(a)),STEEL,rotor,(0,math.pi/2,0),8)
    for i in range(5):
        arm=empty(f'RuneArm_{i}',rotor);arm.rotation_euler[0]=i*math.tau/5
        # Tapered rails from the hub to the target housing (figure 4-30: 60/136 mm).
        for side in (-1,1):
            inner=[(side*.040,.12),(side*.066,.53)];outer=[(side*.064,.12),(side*.090,.53)]
            c4_local_prism('ArmRail',[inner[0],inner[1],outer[1],outer[0]] if side>0 else [outer[0],outer[1],inner[1],inner[0]],.034,frame,arm,'x',-.022)
            c4_strip('ArmRailLamp',[(side*.052,.13),(side*.078,.52)],.009,.004,lamps['TeamRuneFrame'],arm,.012)
        c4_local_prism('ArmChannel',[(-.042,.12),(.042,.12),(.068,.53),(-.068,.53)],.012,face,arm,'x',-.016)
        for z,w in ((.26,.050),(.40,.060)):box('ArmTie',(.026,2*w+.02,.02),(-.004,0,z),frame,arm,.002)
        box('ArmRoot',(.05,.13,.05),(-.012,0,.115),frame,arm,.006)
        for k,z in enumerate((.19,.27,.35,.43)):
            chevron=empty(f'RuneArrow_{i}_{k}',arm)
            for side in (-1,1):beam('ArrowBar',(-.004,side*.022,z-.012),(-.004,0,z+.012),.007,lamps['TeamRuneArrow'],chevron)
        housing=[(-.186,.58),(-.186,.80),(-.15,.871),(.15,.871),(.186,.80),(.186,.58),(.12,.529),(-.12,.529)]
        c4_local_prism('TargetHousing',housing,.037,frame,arm,'x',-.025,.004)
        inset=[(y*.94,.70+(z-.70)*.94) for y,z in housing]
        c4_strip('HousingLamp',inset,.010,.004,lamps['TeamRuneFrame'],arm,.012,closed=True)
        target=empty(f'RuneTarget_{i}',arm);target.location=(0,0,.70)
        cyl('TargetPlate',.154,.010,(.017,0,0),face,target,(0,math.pi/2,0),48)
        for k in range(1,11):c4_ring('ScoreRing',.015*k-.0018,.015*k,.002,groove,target,.022,40)
        for r0,r1 in ((.020,.035),(.055,.075),(.135,.150)):c4_ring('HitMarker',r0,r1,.0025,lamps['TeamRuneTarget'],target,.0245,40)
        for k in range(4):
            a=k*math.pi/2;mid=.105
            spoke=box('HitMarkerSpoke',(.0025,.024,.06),(.0257,mid*math.cos(a),mid*math.sin(a)),lamps['TeamRuneTarget'],target,0);spoke.rotation_euler[0]=a-math.pi/2
        c4_ring('ActivatedRing',.140,.154,.0026,lamps['TeamRuneRing'],target,.0244,48)
        cyl('ActivatedDot',.012,.003,(.0258,0,0),lamps['TeamRuneRing'],target,(0,math.pi/2,0),16)
    export('rune-ch4v2')


def chapter4_tech_core():
    """Technology core and its 6-axis mount in the assembly frame of 5.3.3
    (origin on the pedestal face, +X toward the engineer, Z up). Animated nodes:
    CoreCarriage (x, y), CoreLift (z), CoreYaw (theta), CorePitch (phi), CoreRoll (alpha)."""
    reset();root=empty('TechCore')
    shell=mat('CoreShell',(.30,.31,.29),.25,.55)
    lamp=mat('TeamCoreLamp',(.85,.15,.12),0,.4,2.5)
    carriage=empty('CoreCarriage',root);carriage.location=(0,0,.30)
    box('CarriagePlate',(.15,.15,.02),(0,0,.01),STEEL,carriage,.004)
    for sx in (-1,1):
        for sy in (-1,1):box('CarriageBlock',(.035,.03,.018),(sx*.05,sy*.06,-.002),DARK,carriage,.003)
    box('OuterColumn',(.075,.075,.23),(0,0,.135),DARK,carriage,.008)
    box('ColumnCollar',(.09,.09,.02),(0,0,.25),STEEL,carriage,.003)
    lift=empty('CoreLift',carriage);lift.location=(0,0,.30)
    box('InnerColumn',(.052,.052,.42),(0,0,-.21),STEEL,lift,.004)
    cyl('YawBearing',.055,.025,(0,0,.0125),DARK,lift,vertices=24)
    yaw=empty('CoreYaw',lift);yaw.location=(0,0,.025)
    box('ForkBase',(.06,.20,.02),(0,0,.01),DARK,yaw,.004)
    for side in (-1,1):
        c4_local_prism('ForkCheek',[(-.03,0),(.03,0),(.022,.09),(-.022,.09)],.014,DARK,yaw,'y',side*.093-.007)
        cyl('PitchMotor',.032,.024,(0,side*.112,.075),STEEL,yaw,(math.pi/2,0,0),20)
    pitch=empty('CorePitch',yaw);pitch.location=(0,0,.075)
    roll=empty('CoreRoll',pitch)
    # Head: entry face at +X 0.10 from the pitch/roll centre; bore Ø95 with a 35 mm slot (figure 5-7).
    # The unit slides toward local -Y (the viewer's +Z), matching the engine's slide axis.
    c4_local_prism('CoreHead',[(-.155,-.08),(.085,-.08),(.085,.08),(-.155,.08)],.17,shell,roll,'x',-.10,.012)
    cyl('RollDrive',.045,.05,(-.115,0,0),DARK,roll,(0,math.pi/2,0),24)
    cyl('EntryBore',.0475,.004,(.0705,0,0),DARK,roll,(0,math.pi/2,0),32)
    box('EntrySlot',(.004,.135,.035),(.0705,-.0675,0),DARK,roll,0)
    c4_ring('EntryLamp',.052,.060,.003,lamp,roll,.0705,40)
    for side in (-1,1):box('HeadSideLamp',(.12,.003,.012),(0,.035,side*.0815),lamp,roll,0)
    box('HeadLabel',(.002,.05,.02),(.0705,.05,.055),WHITE,roll,0)
    energy_unit('CoreUnit',roll,(.07,0,0),(0,-math.pi/2,0))
    export('tech-core-ch4v2')


def chapter4_arena(arena):
    reset();chapter4_materials();root=empty('ArenaChapter4')
    box('Substructure',(28.25,15.25,.2),(0,0,-.14),DARK,root,.02)
    # Split at the centreline, so the tilted floor is continuous rather than a bowed box.
    for a,b in [(0,7.5),(7.5,15)]:
        pts=[[0,a],[28,a],[28,b],[0,b]];c4_prism('TiltedField',pts,[floor_z(p[1]) for p in pts],FIELD,root,-.08)
    for t in arena['terrain']:
        pts=t['polygon'];material=KERB if t['kind']=='helipad' or 'pedestal' in t['id'] or '_fly_rail_' in t['id'] else ROAD
        if t['kind']=='bumps':
            # Smooth humps (figure 4-34), sixteen facets per 240 mm pitch.
            for i in range(round(t['w']/t['bump_pitch'])*16):
                x=t['x']+i*t['bump_pitch']/16;xn=x+t['bump_pitch']/16
                p=[[x,t['y']],[xn,t['y']],[xn,t['y']+t['h']],[x,t['y']+t['h']]]
                c4_prism('RoadRidge',p,[floor_z(y)+c4_height(t,xx,y) for xx,y in p],ROAD,root,t['elevation'])
        elif t.get('edge_ramp_m',0):
            cx=sum(p[0] for p in pts)/len(pts);cy=sum(p[1] for p in pts)/len(pts)
            apothem=min(abs((cx-a[0])*(b[1]-a[1])-(cy-a[1])*(b[0]-a[0]))/math.dist(a,b) for a,b in zip(pts,pts[1:]+pts[:1]))
            scale=max(.02,1-t['edge_ramp_m']/apothem)
            inner=[[cx+(x-cx)*scale,cy+(y-cy)*scale] for x,y in pts]
            c4_prism(t['id']+'Top',inner,[floor_z(y)+t['elevation'] for x,y in inner],material,root)
            for i in range(len(pts)):
                p=[pts[i],pts[(i+1)%len(pts)],inner[(i+1)%len(pts)],inner[i]]
                z=[floor_z(y)+(t.get('base_elevation',0) if j<2 else t['elevation']) for j,(x,y) in enumerate(p)]
                c4_prism(t['id']+'Slope',p,z,material,root)
        elif t['kind']=='ramp' and t['id'].endswith('_trapezoid_23'):
            c4_stepped_ramp(arena,t,ROAD,SIDE,root)
        else:
            heights=[floor_z(y)+c4_height(t,x,y) for x,y in pts]
            c4_prism(t['id'],pts,heights,material,root)
            c4_sides(t['id']+'Side',pts,heights,0,SIDE if material is ROAD else material,root)
    for w in arena['obstacles']:
        if w['id'].startswith('rune_'):continue  # modelled in detail by rune_gantry
        obj=box(w['id'],(w['w'],w['h'],w['height']),(w['x']+w['w']/2-14,7.5-w['y']-w['h']/2,w['bottom']+w['height']/2),KERB,root,.01)
        obj.rotation_euler[2]=-w['rotation']
    c4_fence(root)
    # Floor markings and LED paths traced from the field plan (figure 4-59).
    traced=json.loads((SOURCE/'field_paint.json').read_text())
    for key,material,width in (('white',WHITE_PAINT,.035),('red',RED_PAINT,.04),('blue',BLUE_PAINT,.04)):
        for line in traced[key]:c4_paint(arena,line,material,root,width)
    # Crossing-point glyphs at the simulated zone centres: step for road/highland, -v- for tunnels, ramp for fly.
    glyphs={'road':[[[-.08,-.035],[0,-.035],[0,.035],[.08,.035]]],'highland':[[[-.08,-.035],[0,-.035],[0,.035],[.08,.035]]],
            'tunnel':[[[-.13,0],[-.06,0]],[[-.04,.04],[0,-.03],[.04,.04]],[[.06,0],[.13,0]]],
            'fly':[[[-.09,-.035],[.09,-.035],[.09,.04],[-.09,-.035]]]}
    for z in arena['zones']:
        if z['kind'] not in glyphs:continue
        flip=-1 if (z.get('group') or z['id']).startswith('blue') else 1
        for stroke in glyphs[z['kind']]:
            c4_paint(arena,[[z['x']+flip*u,z['y']-flip*v] for u,v in stroke],WHITE_PAINT,root,.028)
    for fixture in arena['field_geometry']['fixtures']:
        kind=fixture['kind'];team=fixture['team'];x,y=fixture['point']
        color=RED_PAINT if team=='red' else BLUE_PAINT
        if kind=='resource':
            resource_station(fixture,root,color)
        elif kind=='charger':
            # The fixture point is the wireless transmitter; the official DC supply
            # cabinet stands behind it against the wall.
            z=floor_z(y);sign=1 if team=='red' else -1;cx=x-sign*.59
            box('ChargerCabinet',(.7,.94,.25),(cx-14,7.5-y,z+.125),KERB,root,.035)
            box('CableCover',(.2,.62,.03),(cx-14,7.5-y,z+.268),STEEL,root,.006)
            # Added wireless TX, separate from the official DC supply cabinet.
            # Its 480x480x180 mm envelope and 100x100 mm coupling face meet S73/S79.
            box('WirelessTransmitter',(.48,.48,.18),(x-14,7.5-y,z+.09),DARK,root,.012)
            box('WirelessTxCoil',(.005,.1,.1),(x-14+sign*.243,7.5-y,z+.16),DARK,root,.002)
            box('TxWhiteStatus',(.005,.005,.005),(x-14+sign*.244,7.5-y+.09,z+.16),WHITE_PAINT,root,.001)
        elif kind=='helipad':
            z=floor_z(y)+.9;p=[[x+dx,y+dy] for dx,dy in [(-.74,-.94),(.74,-.94),(.94,-.74),(.94,.74),(.74,.94),(-.74,.94),(-.94,.74),(-.94,-.74)]]
            c4_paint(arena,p,color,root,.027,True);c4_text(arena,'H',x,y,.6,WHITE_PAINT,root)
            for xx in [-1.08,1.08]:box('HelipadRim',(.07,2.2,.059),(x-14+xx,7.5-y,z+.0295),DARK,root,.008)
        elif kind=='rune_gantry':
            rune_gantry(arena,fixture,root)
        elif kind=='dart_station':
            dart_station(fixture,root,color)
    for team in ['red','blue']:
        sign=1 if team=='red' else -1
        c4_text(arena,'R',4.32 if sign==1 else 23.68,3.70 if sign==1 else 11.30,.7,WHITE_PAINT,root)
        c4_text(arena,'ROBOMASTER',5.2 if sign==1 else 22.8,.47 if sign==1 else 14.53,.36,WHITE_PAINT,root,0 if sign==1 else math.pi)
        y=1.85 if sign==1 else 13.15
        beam('AircraftSafetyWire',(-14 if sign==1 else 14,7.5-y,3.9),(0,7.5-y,3.9),.008,STEEL,root)
        for xx in [-14,0]:box('WireStop',(.05,.08,.08),(xx*sign,7.5-y,3.9),AMBER,root,.003)
    export(Path(arena['asset']).stem)


def chapter4_energy_unit():
    reset();root=empty('EnergyUnit');energy_unit('CarriedEnergyUnit',root,(0,0,0))
    export('energy-unit-ch4')


def c4_frustum(name,bottom,top,z0,z1,material,parent,bevel=0):
    """Closed solid between two horizontal outlines (same vertex count, counter-clockwise)."""
    n=len(bottom);vertices=[(x,y,z0) for x,y in bottom]+[(x,y,z1) for x,y in top]
    faces=[tuple(reversed(range(n))),tuple(range(n,2*n))]+[(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
    obj=c4_mesh(name,vertices,faces,material,parent)
    if bevel:
        modifier=obj.modifiers.new('MachinedEdges','BEVEL');modifier.width=bevel;modifier.segments=2;modifier.limit_method='ANGLE'
        bpy.context.view_layer.objects.active=obj;bpy.ops.object.modifier_apply(modifier=modifier.name)
    return obj


def c4_panel(name,quad,thickness,material,parent):
    """Thin plate from four points (counter-clockwise seen from outside), thickened inward."""
    a,b,c,d=[Vector(p) for p in quad];normal=(b-a).cross(d-a).normalized()
    inner=[p-normal*thickness for p in (a,b,c,d)]
    vertices=[tuple(p) for p in (a,b,c,d)]+[tuple(p) for p in inner]
    faces=[(0,1,2,3),(7,6,5,4),(0,4,5,1),(1,5,6,2),(2,6,7,3),(3,7,4,0)]
    return c4_mesh(name,vertices,faces,material,parent)


def base_outline(apothem_face,reach,scale=1.0):
    """Chamfered-triangle hexagon of the base: armour faces at k*120 deg with half-width
    `reach`; the corners between them are the fixed pillar faces."""
    points=[]
    for k in range(3):
        a=k*math.tau/3;c,s_=math.cos(a),math.sin(a)
        for t in (-reach,reach):points.append(((apothem_face*c-t*s_)*scale,(apothem_face*s_+t*c)*scale))
    return points


def chapter4_base():
    """Figures 4-9/4-10/4-11 and match footage. Closed: a hexagonal truncated pyramid; three
    armour faces are pairs of half-shells meeting at a lit slit, three corner faces are fixed
    pillars with light strips. Open: each half-shell swings out about its corner hinge
    (nodes BaseShell_<face>_<side>, extras swing=+-1), exposing the core and the large armour
    modules 287 mm above the pedestal. The dart-detection module tops it, tilted 27.5 deg."""
    reset();root=empty('Base')
    geometry=CONFIG['simulation_assumptions']['structure_geometry']
    shell=mat('TeamPrimaryShell',(.06,.065,.075),.35,.45)
    graphite=mat('BaseGraphite',(.035,.038,.045),.4,.5)
    panel=mat('BaseInnerPanel',(.12,.125,.135),.3,.55)
    green=mat('DartGuideGreen',(.2,1.,.25),0,.3,6)
    R,H,TOP=.43,.86,.155  # face apothem at the foot, shell top height, apothem at the top
    # Foot plinth and skirt.
    c4_frustum('BaseFoot',base_outline(R+.06,.29),base_outline(R+.045,.285),0,.07,graphite,root,.006)
    c4_frustum('BaseSkirt',base_outline(R+.02,.275),base_outline(R-.01,.26),.07,.12,shell,root,.004)
    # Core: tapered body inside the shells, its faces carrying the lit column and the large armour.
    core_bottom=base_outline(.30,.17);core_top=base_outline(.11,.07)
    c4_frustum('BaseCore',core_bottom,core_top,.12,H+.02,graphite,root,.004)
    for k in range(3):
        a=k*math.tau/3;n=Vector((math.cos(a),math.sin(a),0));t=Vector((-math.sin(a),math.cos(a),0))
        # Lit column seen through the slit (red/blue light in footage) running up the core face.
        core_r=lambda z:.30-.19*(z-.12)/(H+.02-.12)
        lo=n*(core_r(.20)+.003)+Vector((0,0,.20));hi=n*(core_r(H-.04)+.003)+Vector((0,0,H-.04))
        for w,mat_,off in ((.05,GLOW,.004),(.09,panel,.0)):
            c4_panel('CoreLight' if mat_ is GLOW else 'CoreLightBezel',[lo-t*w/2+n*off,lo+t*w/2+n*off,hi+t*w/2*.6+n*off,hi-t*w/2*.6+n*off],.01,mat_,root)
        # Large armour module (figure 4-11 [1]) on the core face, tilted 15 deg.
        mount=empty('LowerArmor_'+str(k),root);mount.location=(.317*n.x,.317*n.y,geometry['base_lower_center_above_pedestal_m'])
        mount.rotation_euler=(0,-math.radians(15),a)
        box('LargeArmorFrame',(.04,.27,.165),(-.006,0,0),graphite,mount,.006)
        box('LargeArmorFace',(.01,.23,.125),(.016,0,0),panel,mount,.003)
        for side in (-1,1):box('ArmorLight',(.012,.012,.09),(.018,side*.122,0),GLOW,mount,.002)
        box('WeakSpot',(.003,.010,.010),(.022,0,0),WHITE,mount)
        # Fixed corner pillar face between armour faces k and k+1, with edge light strips.
        b=a+math.tau/6;m=Vector((math.cos(b),math.sin(b),0));u=Vector((-math.sin(b),math.cos(b),0))
        # Top hexagon closes with the shells' top corners (face apothem .155, half-width .0955).
        foot_r,top_r,half_foot,half_top=.444,.16,.235,.085
        quad=[m*foot_r-u*half_foot+Vector((0,0,.12)),m*foot_r+u*half_foot+Vector((0,0,.12)),m*top_r+u*half_top+Vector((0,0,H)),m*top_r-u*half_top+Vector((0,0,H))]
        c4_panel('CornerPillar',quad,.05,shell,root)
        for side in (-1,1):
            e0=m*(foot_r+.004)+u*side*(half_foot-.035)+Vector((0,0,.16));e1=m*(top_r+.004)+u*side*(half_top-.02)+Vector((0,0,H-.06))
            d=(e1-e0).normalized();w=u*.013
            c4_panel('CornerLight',[e0-w,e0+w,e1+w,e1-w] if side>0 else [e0+w,e0-w,e1-w,e1+w],.006,GLOW,root)
        logo=c4_text_x('R',.11,(0,0,0),WHITE,root);logo.name='CornerLogo_'+str(k)
        logo.location=tuple(m*(foot_r-.038)+Vector((0,0,.24)));logo.rotation_euler=(math.pi/2-math.radians(20),0,b+math.pi/2)
        # Two half-shells per armour face, hinged at the corner ends.
        for side_index,side in enumerate((-1,1)):
            hinge=empty(f'BaseShell_{k}_{side_index}',root);hinge['swing']=side
            foot=n*R+t*side*.265;hinge.location=(foot.x,foot.y,.08);hinge.rotation_euler[2]=a
            # In the hinge frame: +x out of the face, +y along the face; the shell runs back toward the slit.
            slit,top_reach,top_slit=.022,.0955,.012
            local=[Vector((0,0,0)),Vector((0,-side*(.265-slit),0)),Vector((TOP-R,-side*(.265-top_slit),H-.08)),Vector((TOP-R,-side*(.265-top_reach),H-.08))]
            quad=local if side<0 else [local[1],local[0],local[3],local[2]]
            c4_panel('ShellPanel',quad,.03,shell,hinge)
            # Faceted inner rib and the shell's edge light along its outer corner edge.
            e0=local[0]+Vector((.004,-side*.018,.06));e1=local[3]+Vector((.004,side*.018,-.05))
            w=Vector((0,.011,0))
            c4_panel('ShellLight',[e0-w,e0+w,e1+w,e1-w] if side<0 else [e0+w,e0-w,e1-w,e1+w],.005,GLOW,hinge)
            g0=local[1]*.55+local[0]*.45+Vector((.003,0,.05));g1=local[2]*.55+local[3]*.45+Vector((.003,0,-.08))
            c4_panel('ShellGroove',[g0-w*.4,g0+w*.4,g1+w*.4,g1-w*.4] if side<0 else [g0+w*.4,g0-w*.4,g1-w*.4,g1+w*.4],.004,graphite,hinge)
    # Neck, top armour (42 mm only) and the dart-detection module tilted 27.5 deg.
    cyl('BaseNeck',.075,.20,(0,0,H+.09),graphite,root,vertices=6)
    for k in range(3):
        a=k*math.tau/3
        top=empty('TopArmor_'+str(k),root);top.location=(.095*math.cos(a),.095*math.sin(a),geometry['base_top_center_above_pedestal_m']);top.rotation_euler[2]=a
        box('SmallArmor',(.012,.135,.125),(0,0,0),panel,top,.004)
        for side in (-1,1):box('SmallArmorLight',(.012,.008,.07),(.004,side*.072,0),GLOW,top,.001)
    dart=empty('DartModule',root);dart.location=(0,0,1.12);dart.rotation_euler=(0,math.radians(27.5),0)
    box('DartBar',(.11,.98,.07),(0,0,0),graphite,dart,.008)
    for side in (-1,1):
        box('DartBarCap',(.12,.06,.09),(0,side*.46,.005),shell,dart,.006)
        box('DartBarLight',(.004,.32,.012),(.057,side*.24,.01),GLOW,dart,.001)
    box('DartHousing',(.14,.20,.13),(0,0,.0),shell,dart,.008)
    cyl('DartGuideLight',.0275,.012,(.075,0,-.01),green,dart,(0,math.pi/2,0),24)
    box('DartSensor',(.006,.08,.03),(.073,0,.045),GLASS,dart,.002)
    export('base-ch4')


def chapter4_outpost():
    """Figure 4-32. A tapered black tower on a 50 mm pedestal; the front carries the light strip
    (571-1110 mm). The rotating collar (ArmorRotor) holds three armour modules on arms at
    1116/1216/1316 mm: engine face k sits at Blender angle -k*120 deg (glTF mirrors Y).
    The dart-detection housing with its green guide light tops the tower at 1446-1578 mm."""
    reset();root=empty('Outpost');rotor=empty('ArmorRotor',root)
    geometry=CONFIG['simulation_assumptions']['structure_geometry']
    shell=mat('TeamPrimaryShell',(.06,.065,.075),.35,.45)
    graphite=mat('OutpostGraphite',(.035,.038,.045),.4,.5)
    panel=mat('OutpostArmorPanel',(.12,.125,.135),.3,.55)
    green=mat('DartGuideGreen',(.2,1.,.25),0,.3,6)
    ring=[(.33*math.cos(a),.33*math.sin(a)) for a in [k*math.tau/8+math.tau/16 for k in range(8)]]
    c4_frustum('OutpostPedestal',ring,[(x*.96,y*.96) for x,y in ring],0,.05,KERB,root,.006)
    # Regular hexagons with a flat face toward +x (engine face 0), given by apothem.
    hexa=lambda apothem:[(apothem/math.cos(math.pi/6)*math.cos(a),apothem/math.cos(math.pi/6)*math.sin(a)) for a in [math.pi/6+k*math.tau/6 for k in range(6)]]
    c4_frustum('OutpostSkirt',hexa(.19),hexa(.17),.05,.57,graphite,root,.006)
    c4_frustum('OutpostTower',hexa(.15),hexa(.10),.57,1.44,shell,root,.006)
    tower=lambda z:.15-.05*(z-.57)/(1.44-.57)
    # Front light strip and its bezel (engine face 0 points along +x at zero rotation).
    for w,material,off in ((.05,graphite,.002),(.024,GLOW,.006)):
        lo=Vector((tower(.571)+off,0,.571));hi=Vector((tower(1.11)+off,0,1.11))
        c4_panel('TowerLight' if material is GLOW else 'TowerLightBezel',[lo+Vector((0,-w/2,0)),lo+Vector((0,w/2,0)),hi+Vector((0,w/2,0)),hi+Vector((0,-w/2,0))],.012,material,root)
    box('SkirtPanel',(.012,.16,.3),(.182,0,.3),panel,root,.004)
    c4_text_x('R',.08,(.19,0,.40),WHITE,root)
    # Rotating collar with three staggered armour modules.
    cyl('RotorCollar',.155,.30,(0,0,1.215),graphite,rotor,vertices=24)
    for z in (1.075,1.355):cyl('RotorBand',.158,.012,(0,0,z),STEEL,rotor,vertices=24)
    for k,z in enumerate(geometry['outpost_middle_center_m']):
        a=-k*math.tau/3;c,s_=math.cos(a),math.sin(a)
        beam('RotorArm',(.15*c,.15*s_,z),(.245*c,.245*s_,z),.04,graphite,rotor)
        module=empty(f'OutpostArmor_{k}',rotor);module.location=(.2765*c,.2765*s_,z);module.rotation_euler[2]=a
        box('ArmorFrame',(.035,.21,.16),(-.008,0,0),graphite,module,.006)
        box('ArmorPanel',(.012,.17,.125),(.012,0,0),panel,module,.003)
        for side in (-1,1):box('ArmorLight',(.012,.012,.09),(.014,side*.098,0),GLOW,module,.002)
        box('WeakSpot',(.003,.010,.010),(.019,0,0),WHITE,module)
    # Dart-detection housing on top: small 42 mm armour on three sides, green guide light in front.
    box('TopHousing',(.21,.21,.135),(0,0,1.51),shell,root,.01)
    box('TopCap',(.17,.17,.03),(0,0,1.593),graphite,root,.006)
    for k in range(3):
        a=-k*math.tau/3
        top=empty(f'OutpostTopArmor_{k}',root);top.location=(.095*math.cos(a)*1.11,.095*math.sin(a)*1.11,geometry['outpost_top_center_m']);top.rotation_euler[2]=a
        box('SmallArmor',(.01,.12,.1),(0,0,0),panel,top,.003)
    cyl('DartGuideLight',.0275,.012,(.112,0,1.446),green,root,(0,math.pi/2,0),24)
    export('outpost-ch4')
