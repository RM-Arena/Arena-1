"""Run with Blender --background --python assets/blender/build_assets.py.

All models are authored here and exported to GLB; map collision geometry comes
from the same config embedded in Rust. Units are meters. Robot forward is +X.
"""
import bpy
import json
import math
from pathlib import Path
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "frontend/public/assets"
SOURCE = ROOT / "assets/blender"
OUT.mkdir(parents=True, exist_ok=True)
CONFIG = json.loads((ROOT / "config/rules.json").read_text())


def reset():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def mat(name, color, metal=0.0, rough=.5, emission=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Metallic"].default_value = metal
    bsdf.inputs["Roughness"].default_value = rough
    if emission:
        bsdf.inputs["Emission Color"].default_value = (*color, 1)
        bsdf.inputs["Emission Strength"].default_value = emission
    return m


STEEL = mat("BrushedTitanium", (.38,.46,.51), .8, .32)
DARK = mat("GraphiteArmor", (.055,.075,.09), .55, .38)
RUBBER = mat("TireRubber", (.025,.03,.035), .0, .85)
PRIMARY = mat("TeamPrimary", (.45,.65,.8), .45, .32)
WHITE = mat("CeramicPanels", (.72,.78,.77), .3, .36)
AMBER = mat("WarningAmber", (.95,.52,.13), .4, .45)
GLOW = mat("TeamGlow", (.35,.7,.95), .2, .22, 2)
GLASS = mat("SensorGlass", (.12,.4,.5), .7, .15, .5)


def finish(obj, name, material, parent=None, bevel=0):
    obj.name = name
    obj.data.materials.append(material)
    if parent:
        obj.parent = parent
    if bevel:
        modifier = obj.modifiers.new("MachinedEdges", "BEVEL")
        modifier.width = bevel
        modifier.segments = 2
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.modifier_apply(modifier=modifier.name)
    for p in obj.data.polygons:
        p.use_smooth = len(p.vertices) <= 4 and name.startswith(("Wheel", "Barrel", "Hub", "Bolt"))
    return obj


def box(name, size, pos, material, parent=None, bevel=.025):
    bpy.ops.mesh.primitive_cube_add(size=1, location=pos)
    o = bpy.context.object
    o.dimensions = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return finish(o,name,material,parent,bevel)


def cyl(name, radius, depth, pos, material, parent=None, rotation=(0,0,0), vertices=20):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=pos, rotation=rotation)
    return finish(bpy.context.object,name,material,parent,.008)


def empty(name, parent=None):
    o = bpy.data.objects.new(name,None)
    bpy.context.collection.objects.link(o)
    o.parent=parent
    return o


def beam(name,a,b,width,material,parent=None):
    direction=Vector(b)-Vector(a)
    o=box(name,(width,width,direction.length),tuple((Vector(a)+Vector(b))/2),material,parent,.01)
    o.rotation_euler=direction.to_track_quat('Z','Y').to_euler()
    return o


def export(name):
    # Merge static pieces per parent/material, preserving articulated nodes.
    groups={}
    for obj in list(bpy.context.scene.objects):
        if obj.type=='MESH' and len(obj.data.materials)==1:
            groups.setdefault((obj.parent,obj.data.materials[0].name),[]).append(obj)
    for (parent,material_name),objects in groups.items():
        if len(objects)<2:continue
        bpy.ops.object.select_all(action='DESELECT')
        for obj in objects:obj.select_set(True)
        bpy.context.view_layer.objects.active=objects[0]
        bpy.ops.object.join()
        bpy.context.object.name=(parent.name if parent else 'Asset')+'_'+material_name
    # Keep editable native sources as well as the runtime binary glTF assets.
    bpy.ops.wm.save_as_mainfile(filepath=str(SOURCE / (name+".blend")))
    bpy.ops.export_scene.gltf(filepath=str(OUT / (name+".glb")), export_format='GLB',
                              export_yup=True, export_apply=True, export_cameras=False,
                              export_lights=False, export_animations=False, export_extras=True)
    print("EXPORTED",name,flush=True)


def robot(role):
    if role=='aerial':
        return drone()
    reset()
    root=empty("Robot");body=empty("Chassis",root)
    length=1.15 if role=='hero' else 1.08
    box("LowerFrame",(length,.78,.18),(0,0,.28),DARK,body)
    box("ArmorHull",(length*.93,.75,.22),(0,0,.43),PRIMARY,body,.055)
    box("TopPlate",(.76,.63,.05),(-.03,0,.565),WHITE,body)
    box("FrontBumper",(.09,.9,.13),(length/2,0,.22),STEEL,body)
    box("RearPowerPack",(.25,.62,.25),(-.39,0,.56),DARK,body)
    for y in [-.31,.31]:
        box("SideArmor",(.76,.06,.16),(0,y,.5),STEEL,body)
        box("TeamLight",(.48,.035,.035),(.05,y*1.16,.51),GLOW,body,.006)
    for x in [-.34,.34]:
        for y in [-.47,.47]:
            wheel=empty(f"Wheel_{x}_{y}",body)
            wheel.location=(x,y,.2)
            cyl("WheelTire",.195,.14,(0,0,0),RUBBER,wheel,(math.pi/2,0,0),24)
            cyl("Hub",.105,.16,(0,0,0),STEEL,wheel,(math.pi/2,0,0),16)
            cyl("HubCore",.052,.175,(0,0,0),PRIMARY,wheel,(math.pi/2,0,0),12)
    for x in [-.42,.42]:
        for y in [-.3,.3]:cyl("Bolt",.023,.02,(x,y,.57),STEEL,body,vertices=8)
    turret=empty("Turret",body)
    pitch=empty("GunPitch",turret)
    pitch.location=(0,0,.78)
    cyl("TurretBearing",.235,.07,(0,0,.61),STEEL,turret)
    box("TurretHousing",(.4,.4,.22),(-.08,0,.76),PRIMARY,turret,.035)
    box("SensorPanel",(.06,.28,.06),(.15,0,.86),GLASS,turret,.005)
    if role=='engineer':
        box("EngineeringDeck",(.42,.44,.14),(.2,0,.67),AMBER,turret)
        beam("LiftArm",(.15,0,.72),(.62,0,1.12),.07,STEEL,turret)
        beam("UpperArm",(.62,0,1.12),(.87,0,.82),.06,AMBER,turret)
        for y in [-.1,.1]:beam("Gripper",(.87,0,.82),(.93,y,.7),.03,STEEL,turret)
    else:
        ys=[-.105,.105] if role=='sentry' else [0]
        for y in ys:
            radius=.085 if role=='hero' else .045
            cyl("Barrel",radius,.6,(.42,y,0),STEEL,pitch,(0,math.pi/2,0))
            cyl("MuzzleBrake",radius*1.28,.085,(.72,y,0),DARK,pitch,(0,math.pi/2,0))
        box("AmmoContainer",(.22,.42,.2),(-.29,0,.79),DARK,turret)
    if role=='hero':
        box("HeavyPlate",(.7,.58,.075),(-.05,0,.92),WHITE,turret)
        for y in [-.3,.3]:box("ArmorSkirt",(.65,.07,.24),(-.14,y,.76),PRIMARY,turret)
    if role=='sentry':
        beam("Antenna",(-.35,.23,.6),(-.35,.23,1.28),.025,DARK,body)
        cyl("Radar",.18,.07,(-.35,.23,1.28),WHITE,body)
    if role=='scout':
        body.scale=(.85,.85,.8)
        box("ScoutNose",(.3,.55,.12),(.5,0,.46),WHITE,body)
        for y in [-.22,.22]:cyl("Thruster",.055,.18,(-.58,y,.38),GLOW,body,(0,math.pi/2,0))
    root.scale=(.68,.68,.68)
    export('robot-'+role)


def drone():
    reset();root=empty("Robot");body=empty("Chassis",root)
    box("FlightBody",(.38,.3,.17),(0,0,.2),PRIMARY,body,.03)
    box("Battery",(.28,.22,.08),(0,0,.33),DARK,body)
    for i,(x,y) in enumerate([(-.36,-.36),(-.36,.36),(.36,-.36),(.36,.36)]):
        beam("MotorArm",(0,0,.25),(x,y,.25),.045,STEEL,body)
        cyl("Motor",.07,.1,(x,y,.27),DARK,body)
        rotor=empty('Rotor_'+str(i),body);rotor.location=(x,y,.34)
        box("Propeller",(.39,.04,.013),(0,0,0),DARK,rotor,.006)
        box("Propeller",(.04,.39,.013),(0,0,0),DARK,rotor,.006)
        for side in [-1,1]:beam('RotorGuard',(x+side*.23,y-.23,.34),(x+side*.23,y+.23,.34),.01,STEEL,body)
    for y in [-.16,.16]:beam("LandingLeg",(-.12,y,0),(.12,y,0),.023,DARK,body)
    turret=empty('Turret',body);pitch=empty('GunPitch',turret);pitch.location=(0,0,.25)
    cyl('Barrel',.025,.4,(.24,0,0),STEEL,pitch,(0,math.pi/2,0))
    box('Camera',(.06,.06,.05),(.18,0,.17),GLASS,turret)
    export('robot-aerial')


def base():
    reset();root=empty("Base")
    cyl('BasePedestal',.94,.2,(0,0,.1),DARK,root,vertices=6)
    cyl('ArmorTower',.49,.65,(0,0,.56),PRIMARY,root,vertices=6)
    for i in range(3):
        a=i*math.tau/3
        plate=box('ArmorPlate',(.18,.05,.13),(.42*math.cos(a),.42*math.sin(a),.6),WHITE,root,.006);plate.rotation_euler[2]=a-math.pi/2
    cyl('TopSensor',.09,.12,(0,0,1.05),GLOW,root,vertices=12)
    beam('CrownSupport',(0,0,.85),(0,0,1.15),.06,STEEL,root)
    export('base')


def outpost():
    reset();root=empty('Outpost');rotor=empty('ArmorRotor',root)
    cyl('Pedestal',.3,.3,(0,0,.15),DARK,root)
    cyl('Shaft',.08,.8,(0,0,.6),STEEL,root)
    for i in range(3):
        a=i*math.tau/3
        plate=box('ArmorPlate',(.16,.055,.14),(.28*math.cos(a),.28*math.sin(a),.8),PRIMARY,rotor,.008);plate.rotation_euler[2]=a-math.pi/2
        beam('Arm',(0,0,.8),(.28*math.cos(a),.28*math.sin(a),.8),.035,STEEL,rotor)
    cyl('Sensor',.045,.1,(0,0,1.05),GLOW,root)
    export('outpost')


def arena(name,arena):
    reset();root=empty("Arena")
    concrete=mat("WorkshopConcrete",(.075,.105,.12),.16,.82)
    floor=box("CompetitionFloor",(arena['width'],arena['height'],.2),(0,0,-.13),concrete,root,0)
    box("Foundation",(arena['width']+1,arena['height']+1,.5),(0,0,-.5),DARK,root,.12)
    for x in range(-int(arena['width']/2),int(arena['width']/2)+1,2):box("GridLine",(.012,arena['height'],.006),(x,0,-.026),STEEL,root,0)
    for y in range(-int(arena['height']/2),int(arena['height']/2)+1,2):box("GridLine",(arena['width'],.012,.006),(0,y,-.026),STEEL,root,0)
    for wall in arena['obstacles']:
        x,y=wall['x']+wall['w']/2-arena['width']/2,arena['height']/2-wall['y']-wall['h']/2
        box("CoverCollider",(wall['w'],wall['h'],wall['height']),(x,y,wall['height']/2),DARK,root,.055)
        box("CoverTop",(wall['w']+.05,wall['h']+.05,.06),(x,y,wall['height']+.03),STEEL,root,.015)
        for d in [-1,1]:
            box("WarningStrip",(wall['w']*.7,.06,.04),(x,y+d*wall['h']/2,wall['height']+.075),AMBER,root,.005)
        for z in [.3,.75,1.2]:
            if z<wall['height']:box("Reinforcement",(wall['w']+.08,wall['h']+.08,.05),(x,y,z),STEEL,root,.01)
    for t in arena['terrain']:
        x,y=t['x']+t['w']/2-arena['width']/2,arena['height']/2-t['y']-t['h']/2
        if t['kind']=='platform':
            box("RaisedDeck",(t['w'],t['h'],t['elevation']),(x,y,t['elevation']/2-.01),DARK,root,.03)
            box("DeckSurface",(t['w'],t['h'],.04),(x,y,t['elevation']-.02),STEEL,root,0)
            for xx in [-t['w']/2,t['w']/2]:box("DeckMarker",(.055,t['h'],.015),(x+xx,y,t['elevation']+.009),AMBER,root,0)
        elif t['kind']=='ramp':
            x0,x1=t['x']-arena['width']/2,t['x']+t['w']-arena['width']/2;y0,y1=arena['height']/2-t['y'],arena['height']/2-t['y']-t['h']
            z0,z1=(0,t['elevation']) if t['direction']>0 else (t['elevation'],0)
            mesh=bpy.data.meshes.new('RampMesh');mesh.from_pydata([(x0,y0,z0),(x1,y0,z1),(x1,y1,z1),(x0,y1,z0),(x0,y0,-.02),(x1,y0,-.02),(x1,y1,-.02),(x0,y1,-.02)],[],[(0,1,2,3),(4,7,6,5),(0,4,5,1),(1,5,6,2),(2,6,7,3),(3,7,4,0)])
            obj=bpy.data.objects.new('AccessRamp',mesh);bpy.context.collection.objects.link(obj);finish(obj,'AccessRamp',STEEL,root)
            for i in range(1,10):
                xx=x0+(x1-x0)*i/10;zz=z0+(z1-z0)*i/10
                bar=box("RampGrip",(.06,t['h']*.93,.02),(xx,y,zz+.013),DARK,root,0);bar.rotation_euler[1]=-math.atan2(z1-z0,x1-x0)
        else:
            box("TractionZone",(t['w'],t['h'],.02),(x,y,-.012),DARK,root,0)
            for i in range(10):box("TractionGrate",(t['w'],.05,.015),(x,y-t['h']/2+t['h']*i/10,.001),STEEL,root,0)
    for y in [-arena['height']/2-.1,arena['height']/2+.1]:
        box('SafetyFence',(arena['width'],.12,2.4),(0,y,1.2),DARK,root)
        for x in range(-int(arena['width']/2),int(arena['width']/2)+1,2):box('FencePost',(.08,.16,2.4),(x,y,1.2),STEEL,root)
    for x in [-arena['width']/2-.1,arena['width']/2+.1]:box('LowEndBarrier',(.12,arena['height'],.4),(x,0,.2),DARK,root)
    for team,pos in arena['pads'].items():
        x,y=pos[0]-arena['width']/2,arena['height']/2-pos[1]
        box('Helipad',(1.2,1.2,.035),(x,y,.018),STEEL,root)
        box('PadH',(.08,.8,.008),(x,y,.04),WHITE,root,0)
        for xx in [-.25,.25]:box('PadH',(.08,.8,.008),(x+xx,y,.04),WHITE,root,0)
    # Supply stations, energy units and technology core proxies remain outside
    # weapon armor; they are semantic interactions rather than destructible props.
    for zone in arena['zones']:
        x,y=zone['x']-arena['width']/2,arena['height']/2-zone['y']
        if zone['kind']=='resource':
            for xx in [-.1,.1]:cyl('EnergyUnit',.0475,.15,(x+xx,y,.075),AMBER,root,vertices=12)
        if zone['kind']=='assembly':
            box('TechnologyCore',(.3,.3,.25),(x,y,.8),STEEL,root)
            box('CoreOpening',(.15,.025,.15),(x-.16,y,.8),GLOW,root)
    # The floor is tilted 1.5 degrees from the centerline toward each long edge.
    # Transform the substrate and field fixtures consistently with engine datum.
    for obj in list(bpy.context.scene.objects):
        if obj.type=='MESH' and obj.parent==root:
            for vertex in obj.data.vertices:
                world=obj.matrix_world@vertex.co
                world.z+=(arena['height']/2-abs(world.y))*math.tan(math.radians(arena['floor_slope_deg']))
                vertex.co=obj.matrix_world.inverted()@world
    export('map-'+name)


exec((SOURCE/'chapter4.py').read_text(),globals())
exec((SOURCE/'robot_specs.py').read_text(),globals())
exec((SOURCE/'season2027.py').read_text(),globals())
# RMUC_ASSETS=legacy,robots,structures,map limits a development rebuild; default builds all.
# RMUC_ASSETS=season2027 (or robots2027 / map2027) builds only the RMUC 2027 assets.
import os
PARTS=set(filter(None,os.environ.get('RMUC_ASSETS','legacy,robots,structures,map').split(',')))
chapter4_materials()
if PARTS&{'season2027','robots2027','map2027'}:season2027_assets()
if 'legacy' in PARTS:
    for role in CONFIG['specs']:robot(role)
if 'robots' in PARTS:spec_robots()
if 'structures' in PARTS:
    chapter4_base()
    chapter4_outpost()
    chapter4_rune_face()
    chapter4_tech_core()
if 'structures' in PARTS or 'units' in PARTS:
    chapter4_energy_unit()
if 'map' in PARTS:
    for name,data in CONFIG['maps'].items():
        if data.get('season')=='2027':chapter4_2027_arena(data)
        elif data.get('layout_revision'):chapter4_arena(data)
        else:arena(name,data)
manifest={'author':'RMUC Arena procedural Blender source','units':'meters','forward':'+X','format':'glTF 2.0 GLB','assets':sorted(p.name for p in OUT.glob('*.glb'))}
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2))
