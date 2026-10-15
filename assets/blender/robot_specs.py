"""Six construction-manual robots, driven by the shared SI design file.

Referee modules follow the published outlines (armor 135x125 / 230x127, A-type
brackets, 285x85 light bar, 76x63 main control, muzzle speed modules); the rest
is a plausible RoboMaster build: mecanum modules with 12 rollers and M3508
gearmotors, GM6020 gimbal axes, friction-wheel launchers, a five-bar
wheel-legged chassis and a lift/boom/three-axis-wrist engineer arm.
Animated nodes are listed in assets/README.md and driven by the viewer.
"""


def spec_materials():
    global ROBOT_MATTE, ROBOT_ALUMINUM, ROBOT_PANEL, STATUS_WHITE, CARBON, ALLOY, MOTOR, MOTOR_CAP, REF_GRAY, LENS, TYRE, SPRING, ORANGE
    ROBOT_MATTE=mat('RobotMatteGraphite',(.045,.055,.064),.1,.85)
    ROBOT_ALUMINUM=mat('RobotMatteAluminum',(.24,.28,.30),.25,.8)
    ROBOT_PANEL=mat('TeamPrimaryShell',(.20,.27,.32),.1,.84)
    STATUS_WHITE=mat('StatusWhite',(.8,.8,.74),0,.8,.4)
    CARBON=mat('CarbonPlate',(.028,.03,.034),.2,.55)
    ALLOY=mat('MachinedAlloy',(.42,.45,.47),.75,.38)
    MOTOR=mat('MotorHousing',(.10,.105,.11),.6,.42)
    MOTOR_CAP=mat('MotorCapSilver',(.55,.57,.58),.85,.3)
    REF_GRAY=mat('RefereeModuleGray',(.16,.17,.18),.15,.7)
    LENS=mat('CameraLens',(.03,.05,.07),.9,.08,.2)
    TYRE=mat('PolyurethaneRoller',(.035,.035,.038),0,.9)
    SPRING=mat('SpringSteelOrange',(.75,.32,.06),.6,.4)
    ORANGE=mat('WarningOrange',(.85,.38,.06),.2,.55)


def rod(name,a,b,radius,material,parent,vertices=12):
    direction=Vector(b)-Vector(a)
    o=cyl(name,radius,direction.length,tuple((Vector(a)+Vector(b))/2),material,parent,vertices=vertices)
    o.rotation_euler=direction.to_track_quat('Z','Y').to_euler()
    return o


def bar(name,a,b,width,depth,material,parent,bevel=.002):
    """Rectangular section member between two points (width across, depth up)."""
    direction=Vector(b)-Vector(a)
    o=box(name,(width,depth,direction.length),tuple((Vector(a)+Vector(b))/2),material,parent,bevel)
    o.rotation_euler=direction.to_track_quat('Z','Y').to_euler()
    return o


def m3508(name,location,axis,parent,scale=1.0):
    """M3508 gearmotor: Ø42 motor can, Ø36 planetary head and output hub along an axis."""
    v=Vector(axis).normalized();c=Vector(location)
    rod(name+'Can',c,c+v*.052*scale,.021*scale,MOTOR,parent,20)
    rod(name+'Gearbox',c+v*.052*scale,c+v*.072*scale,.018*scale,MOTOR_CAP,parent,20)
    rod(name+'Cap',c-v*.004*scale,c,.0175*scale,MOTOR_CAP,parent,20)
    rod(name+'Lead',c+Vector((0,0,.018*scale)),c+Vector((0,0,.018*scale))-v*.03*scale,.003,ROBOT_MATTE,parent,6)


def gm6020(name,location,axis,parent):
    """GM6020 gimbal motor: Ø66 x 30 mm pancake with a bolt ring."""
    v=Vector(axis).normalized();c=Vector(location)
    rod(name+'Stator',c-v*.015,c+v*.015,.033,MOTOR,parent,28)
    rod(name+'Rotor',c+v*.015,c+v*.021,.026,MOTOR_CAP,parent,28)
    rod(name+'Ring',c-v*.017,c-v*.015,.030,MOTOR_CAP,parent,28)


def mecanum_wheel(wheel,radius,width,hand,motor_side):
    """Mecanum wheel in the local XZ plane (axle along Y): two plates, 12 rollers at 45 deg."""
    for y in (-width/2+.004,width/2-.004):
        cyl('WheelSidePlate',radius*.78,.005,(0,y,0),ALLOY,wheel,(math.pi/2,0,0),28)
        for k in range(6):
            a=k*math.tau/6+math.pi/6
            cyl('PlateLightening',radius*.13,.0055,(radius*.48*math.cos(a),y,radius*.48*math.sin(a)),ROBOT_MATTE,wheel,(math.pi/2,0,0),10)
    cyl('WheelHub',radius*.28,width*.92,(0,0,0),MOTOR,wheel,(math.pi/2,0,0),18)
    cyl('WheelHubCap',radius*.17,width*.98,(0,0,0),ALLOY,wheel,(math.pi/2,0,0),12)
    count=12;rr=radius*.2;axle=Vector((0,hand,0))
    for k in range(count):
        a=k*math.tau/count
        centre=Vector((radius*.8*math.sin(a),0,radius*.8*math.cos(a)))
        tangent=Vector((math.cos(a),0,-math.sin(a)))
        direction=(tangent*math.cos(math.pi/4)+axle*math.sin(math.pi/4)).normalized()
        bpy.ops.mesh.primitive_uv_sphere_add(segments=10,ring_count=6,radius=1,location=centre)
        roller=bpy.context.object;roller.scale=(rr,rr,width*.58)
        roller.rotation_euler=direction.to_track_quat('Z','Y').to_euler()
        bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
        finish(roller,'MecanumRoller',TYRE,wheel)
        rod('RollerPin',centre-direction*width*.60,centre+direction*width*.60,.0025,ALLOY,wheel,6)


def armor_module(slot,mount,width,height,parent_name='ArmorPlate'):
    """Official armor module on an A-type support: plate tilted so its normal is
    75 deg from down. `mount` sits at the support foot, +X facing out."""
    plate=empty(parent_name,mount);plate.rotation_euler[1]=-math.radians(15)
    for y in (-.0475,.0475):
        # A-type support truss (figure 3-15): back post, slanted face rail, two braces.
        # Behind the plate, which leans back 15 deg toward its top edge.
        bar('ArmorSupportPost',(-.062,y,-.072),(-.062,y,.030),.012,.008,ROBOT_ALUMINUM,mount)
        bar('ArmorSupportFace',(-.004,y,-.066),(-.036,y,.052),.012,.008,ROBOT_ALUMINUM,mount)
        bar('ArmorSupportBrace',(-.062,y,-.058),(-.016,y,.010),.010,.006,ROBOT_ALUMINUM,mount)
        bar('ArmorSupportTop',(-.062,y,.030),(-.032,y,.046),.010,.006,ROBOT_ALUMINUM,mount)
        bar('ArmorSupportFoot',(-.068,y,-.072),(.006,y,-.072),.014,.008,ROBOT_ALUMINUM,mount)
    w,h=width,height
    c4_local_prism('ArmorModuleBody',[(-w/2-.017,-h/2-.006),(w/2+.017,-h/2-.006),(w/2+.017,h/2-.004),(w/2+.009,h/2+.006),(-w/2-.009,h/2+.006),(-w/2-.017,h/2-.004)],.016,ROBOT_MATTE,plate,'x',-.008,.0025)
    # The front surface is also the simulator's damage plane.
    face_offset=CONFIG['robot_designs'][str(slot)]['armor_hit_face_offset_m']
    box('ArmorHitFace',(.003,w*.96,h*.92),(face_offset-.0015,0,0),REF_GRAY,plate,.002)
    box('ArmorSticker',(.002,w*.62 if w<.2 else w*.72,h*.62),(.0115,0,0),WHITE,plate,.003)
    for y in (-w/2-.011,w/2+.011):
        box('OfficialArmorLamp',(.006,.008,h*.56),(.009,y,0),GLOW,plate,.002)
    for y in (-w*.42,w*.42):
        for z in (-h*.40,h*.40):cyl('ArmorM4',.0035,.003,(.0115,y,z),ROBOT_ALUMINUM,plate,(0,math.pi/2,0),8)
    for y in (-w*.3,w*.3):box('ArmorTopTab',(.012,.012,.008),(-.004,y,h/2+.008),ROBOT_ALUMINUM,plate,.002)
    curve=bpy.data.curves.new('ArmorID','FONT');curve.body=str(slot);curve.size=.05;curve.align_x='CENTER';curve.align_y='CENTER';curve.extrude=.0006
    anchor=empty('ArmorNumber',plate);anchor.location=(.0128,0,0);anchor.rotation_euler=(math.pi/2,0,math.pi/2)
    label=bpy.data.objects.new('ArmorDigit',curve);bpy.context.collection.objects.link(label)
    label.parent=anchor;curve.materials.append(ROBOT_MATTE)
    bpy.context.view_layer.objects.active=label;bpy.ops.object.select_all(action='DESELECT');label.select_set(True);bpy.ops.object.convert(target='MESH')
    beam('ProtectedCableLoom',(-.06,0,-.05),(-.09,0,-.06),.008,ROBOT_MATTE,mount)
    return plate


def light_bar(name,location,yaw,parent,legs=.045):
    """285 x 85 mm light bar module (figure 3-11) on its two fixing brackets."""
    local=empty(name,parent);local.location=location;local.rotation_euler[2]=yaw
    box('LightBarHousing',(.022,.285,.026),(0,0,legs+.013),ROBOT_MATTE,local,.004)
    box('LightBarMain',(.004,.24,.008),(.012,0,legs+.012),GLOW,local,.001)
    for y in (-.13,.13):
        box('LightBarAux',(.016,.022,.006),(0,y,legs+.028),GLOW,local,.001)
        box('LightBarEndCap',(.026,.016,.03),(0,y*1.07,legs+.013),ROBOT_MATTE,local,.004)
    for y in (-.05,.05):
        c4_local_prism('LightBarBracket',[(-.012,0),(.012,0),(.008,legs),(-.008,legs)],.004,ROBOT_ALUMINUM,local,'y',y-.002)
    return local


def referee_box(name,size,location,parent,material=None,screen=False):
    o=box(name,size,location,material or REF_GRAY,parent,.003)
    if screen:box(name+'Screen',(size[0]*.45,size[1]*.55,.002),(location[0]+size[0]*.12,location[1],location[2]+size[2]/2+.001),LENS,parent,0)
    return o


def vtm_camera(name,location,parent,yaw=0):
    """Video transmission module (sender) with lens and two antennas."""
    local=empty(name,parent);local.location=location;local.rotation_euler[2]=yaw
    box('VtmBody',(.05,.045,.034),(0,0,.017),REF_GRAY,local,.004)
    cyl('VtmLensBarrel',.012,.018,(.032,0,.018),ROBOT_MATTE,local,(0,math.pi/2,0),16)
    cyl('VtmLens',.008,.002,(.042,0,.018),LENS,local,(0,math.pi/2,0),16)
    for y in (-.016,.016):rod('VtmAntenna',(-.02,y,.034),(-.07,y*1.6,.05),.0028,ROBOT_MATTE,local,6)
    return local


def speed_module(name,reach,calibre,parent):
    """Muzzle speed module through which the barrel fires (17 or 42 mm)."""
    size=(.047,.056,.040) if calibre==17 else (.062,.078,.064)
    box(name,size,(reach-size[0]/2,0,0),REF_GRAY,parent,.004)
    box(name+'Window',(.002,size[1]*.4,size[2]*.35),(reach+.0005,0,0),ROBOT_MATTE,parent,0)


def bumper(length,width,z,parent,radius=.009):
    """Rounded protective rail around the chassis (S151/S152)."""
    hl,hw,c=length/2,width/2,.05
    corners=[(hl-c,hw),(hl,hw-c),(hl,-hw+c),(hl-c,-hw),(-hl+c,-hw),(-hl,-hw+c),(-hl,hw-c),(-hl+c,hw)]
    for a,b in zip(corners,corners[1:]+corners[:1]):rod('BumperRail',(a[0],a[1],z),(b[0],b[1],z),radius,ROBOT_ALUMINUM,parent,8)
    for x,y in [(hl,0),(-hl,0),(0,hw),(0,-hw)]:
        rod('BumperStandoff',(x*.92,y*.92,z),(x,y,z),.006,ROBOT_ALUMINUM,parent,8)


def battery(name,location,parent,yaw=0):
    local=empty(name,parent);local.location=location;local.rotation_euler[2]=yaw
    box('BatteryCradle',(.19,.10,.012),(0,0,.006),ROBOT_ALUMINUM,local,.003)
    box('BatteryPack',(.17,.075,.052),(0,0,.038),ROBOT_MATTE,local,.008)
    box('BatteryLabel',(.08,.0015,.02),(0,.0378,.04),REF_GRAY,local,0)
    for k in range(4):box('BatteryGauge',(.006,.0015,.004),(.05+k*.009,.0378,.052),STATUS_WHITE,local,0)
    return local


def verify_robot_envelope(slot,d):
    def dimensions(exclude_mast=False):
        points=[]
        bpy.context.view_layer.update()
        for obj in bpy.context.scene.objects:
            if obj.type!='MESH' or exclude_mast and obj.name.startswith(('RigidSafetyMast','SafetyHookRing')):continue
            points.extend(obj.matrix_world@Vector(v) for v in obj.bound_box)
        return [max(p[i] for p in points)-min(p[i] for p in points) for i in range(3)]
    limit=CONFIG['official']['construction']['envelope'][d['role']]
    legged=d.get('chassis_type')=='wheel_legged'
    if legged:pose_legs(d,d['leg_min_m'])
    stowed=dimensions(d['role']=='aerial')
    if not all(a<=b+.002 for a,b in zip(stowed,limit['stowed_m'])):
        extents=[]
        for obj in bpy.context.scene.objects:
            if obj.type=='MESH':
                pts=[obj.matrix_world@Vector(v) for v in obj.bound_box]
                extents.append((obj.name,[round(min(p[i] for p in pts),3) for i in range(3)],[round(max(p[i] for p in pts),3) for i in range(3)]))
        for axis in range(3):
            print('AXIS',axis,sorted(extents,key=lambda e:e[1][axis])[:3],sorted(extents,key=lambda e:-e[2][axis])[:3])
    assert all(a<=b+.002 for a,b in zip(stowed,limit['stowed_m'])),f'{slot} stowed mesh exceeds specification: {stowed}'
    turret=bpy.data.objects.get('Turret');pitch=bpy.data.objects.get('GunPitch');maximum=stowed[:]
    poses=[(d['leg_min_m'],0),(d['leg_max_m'],0)] if legged else [None]
    if legged and d.get('leg_type')=='serial':
        # Self-righting swings tucked or nominal legs a full turn about the hips.
        poses+=[(length,k*math.pi/4) for length in (d['leg_min_m'],d['leg_nominal_m']) for k in range(1,8)]
    for legs in poses:
        if legs:pose_legs(d,*legs)
        if turret and pitch:
            for yaw in range(0,360,15):
                for elevation in [-15,0,45]:
                    turret.rotation_euler[2]=math.radians(yaw);pitch.rotation_euler[1]=-math.radians(elevation)
                    size=dimensions(d['role']=='aerial');maximum=[max(a,b) for a,b in zip(maximum,size)]
            turret.rotation_euler[2]=0;pitch.rotation_euler[1]=0
    if legged:pose_legs(d,d['leg_nominal_m'])
    if d['role']=='engineer':
        arm=d['arm'];lim=arm['limits']
        for slew in [lim[0][0],-math.pi/2,0,math.pi/2,lim[0][1]]:
            for lift in lim[1]:
                for pitch_q in [lim[4][0],0,lim[4][1]]:
                    pose_arm(arm,[slew,lift,lim[2][1],0,pitch_q,0,1])
                    if d.get('arm_count')==2:pose_arm(d['arm2'],[-slew,lift,d['arm2']['limits'][2][1],0,pitch_q,0,1],'Aux_')
                    size=dimensions();maximum=[max(a,b) for a,b in zip(maximum,size)]
        pose_arm(arm,arm['stowed'])
        if d.get('arm_count')==2:pose_arm(d['arm2'],d['arm2']['stowed'],'Aux_')
    assert all(a<=b+.002 for a,b in zip(maximum,limit['extended_m'])),f'{slot} articulated envelope exceeds specification: {maximum}'
    envelope={'slot':slot,'stowed_mesh_m':stowed,'articulated_mesh_max_m':maximum,'stowed_limit_m':limit['stowed_m'],'extended_limit_m':limit['extended_m'],'bare_mass_kg':d['bare_mass_kg'],'referee_mass_kg':d['referee_mass_kg'],'mast_excluded':d['role']=='aerial'}
    if d.get('transform_allowed'):
        pose_transform(d,1)
        folded=[0,0,0];top=0.0
        for yaw in range(0,360,15):
            for elevation in [-8,0,8]:
                turret.rotation_euler[2]=math.radians(yaw);pitch.rotation_euler[1]=-math.radians(elevation)
                folded=[max(a,b) for a,b in zip(folded,dimensions())]
                top=max(top,max((o.matrix_world@Vector(v)).z for o in bpy.context.scene.objects if o.type=='MESH' for v in o.bound_box))
        assert top<=d['folded_height_m']+.002,f'{slot} folded mesh exceeds tunnel height: {top}'
        envelope.update(folded_mesh_max_m=folded,folded_top_m=top,folded_height_limit_m=d['folded_height_m'])
        pose_transform(d,0);turret.rotation_euler[2]=0;pitch.rotation_euler[1]=0
    (OUT/f'robot-{slot}-envelope.json').write_text(json.dumps(envelope,indent=2))


def chassis_modules(slot,d,body,deck,length,width):
    """Referee electronics placed as the manual recommends: main control behind
    an armor's upper edge, power module and supercap inside the frame."""
    referee_box('JudgeMainControl',(.063,.076,.014),(-length*.30,0,deck+.012),body,REF_GRAY,True)
    referee_box('PowerManagement',(.09,.062,.026),(-length*.08,-width*.2,deck+.018),body)
    for k in range(3):cyl('PowerPort',.005,.012,(-length*.08-.03+k*.03,-width*.2-.033,deck+.02),ALLOY,body,(math.pi/2,0,0),10)
    referee_box('PositioningModule',(.045,.045,.016),(length*.08,width*.2,deck+.01),body)
    cyl('PositioningPuck',.016,.008,(length*.08,width*.2,deck+.022),STATUS_WHITE,body,vertices=16)
    referee_box('FieldInteractionModule',(.07,.05,.008),(length*.1,0,.072),body,ROBOT_MATTE)
    if d['supercap_nominal_j']:
        local=empty('SuperCapModule',body);local.location=(length*.12,-width*.18,deck)
        box('SuperCapBoard',(.11,.075,.006),(0,0,.004),ROBOT_MATTE,local,.002)
        for k in range(5):cyl('SuperCapCell',.011,.06,(-.04+k*.02,0,.02),MOTOR_CAP,local,(math.pi/2,0,0),12)
        # Wireless charging receiver coil behind the front bumper (coil_offset_m).
        box('WirelessRxFace',(.006,.1,.1),(length/2-.012,0,.16),ROBOT_MATTE,body,.003)


def mecanum_chassis(slot,d,body,well=False):
    length,width,height=d['chassis_size_m'];radius=d['wheel_radius_m'];ww=d['wheel_width_m']
    # The base plate sits at the design's ground clearance; the deck keeps its height.
    lift=d.get('ground_clearance_m',.035)+d['suspension_static_compression_m']-.053
    hl,hw=length/2,width/2;deck=.065+lift+height
    # Carbon base plate with wheel cut-outs and an aluminium box frame.
    notch=radius+.012
    base=[(hl-.03,-hw+.06),(hl-.03,hw-.06),(d['wheelbase_m']/2-notch*1.1,hw-.06),(d['wheelbase_m']/2-notch*1.1,hw-.02),(-d['wheelbase_m']/2+notch*1.1,hw-.02),(-d['wheelbase_m']/2+notch*1.1,hw-.06),(-hl+.03,hw-.06),(-hl+.03,-hw+.06),(-d['wheelbase_m']/2+notch*1.1,-hw+.06),(-d['wheelbase_m']/2+notch*1.1,-hw+.02),(d['wheelbase_m']/2-notch*1.1,-hw+.02),(d['wheelbase_m']/2-notch*1.1,-hw+.06)]
    c4_local_prism('ChassisBasePlate',base,.006,CARBON,body,'z',.066+lift,.002)
    for y in (-hw*.62,hw*.62):
        box('ChassisRail',(length*.82,.02,.03),(0,y,.084+lift),ROBOT_ALUMINUM,body,.002)
    for x in (-hl*.78,hl*.78,0):
        box('ChassisCrossmember',(.02,width*.62,.02),(x,0,.079+lift),ROBOT_ALUMINUM,body,.002)
    if not well:
        c4_local_prism('ChassisTopDeck',[(hl*.62,-hw*.55),(hl*.62,hw*.55),(-hl*.7,hw*.55),(-hl*.7,-hw*.55)],.005,CARBON,body,'z',deck-.005,.002)
        for x in (-hl*.55,hl*.45):
            for y in (-hw*.45,hw*.45):box('DeckStandoff',(.012,.012,deck-.095-lift),(x,y,(deck+.095+lift)/2),ROBOT_ALUMINUM,body,.001)
    else:
        for y in (-1,1):c4_local_prism('ChassisSideDeck',[(hl*.62,y*hw*.55),(hl*.62,y*hw*.22),(-hl*.7,y*hw*.22),(-hl*.7,y*hw*.55)] if y>0 else [(hl*.62,y*hw*.22),(hl*.62,y*hw*.55),(-hl*.7,y*hw*.55),(-hl*.7,y*hw*.22)],.005,CARBON,body,'z',deck-.005,.002)
    for i,(sx,sy) in enumerate([(-1,-1),(-1,1),(1,-1),(1,1)]):
        x=sx*d['wheelbase_m']/2;y=sy*d['track_m']/2
        module=body
        if d['chassis_type']=='swerve':
            module=empty('SteerModule_'+str(i),body);module.location=(x,y,radius)
            cyl('SteerBearing',.035,.022,(0,0,.05),ALLOY,module,vertices=20)
            box('SteerServo',(.065,.05,.04),(0,0,.045),MOTOR,module,.004)
        wheel=empty('Wheel_'+str(i),module);wheel.location=(0,0,0) if module!=body else (x,y,radius)
        if d['chassis_type']=='swerve':
            cyl('SwerveTyre',radius,ww,(0,0,0),TYRE,wheel,(math.pi/2,0,0),28)
            cyl('SwerveHub',radius*.68,ww*1.05,(0,0,0),ALLOY,wheel,(math.pi/2,0,0),20)
        else:
            if d['chassis_type']=='omni':wheel.rotation_euler[2]=-sx*sy*math.pi/4
            mecanum_wheel(wheel,radius,ww,0 if d['chassis_type']=='omni' else 1 if sx*sy>0 else -1,-sy)
        # Trailing suspension arm, coil-over damper and the M3508 on the inboard side.
        inner=y-sy*(ww/2+.004)
        m3508('DriveMotor',(x,inner,radius),(0,-sy,0),body)
        pivot=(x-sx*.11,y-sy*(ww/2+.03),.105+lift)
        bar('SuspensionArm',pivot,(x,inner-sy*.03,radius+.01),.024,.016,ROBOT_ALUMINUM,body)
        top=(x-sx*.06,y-sy*(ww/2+.05),deck-.01)
        rod('DamperBody',(x-sx*.03,inner-sy*.04,radius+.02),top,.009,MOTOR,body,10)
        bottom=Vector((x-sx*.03,inner-sy*.04,radius+.02));tv=Vector(top);step=(tv-bottom)/8
        for k in range(8):
            ring=rod('DamperSpring',bottom+step*k,bottom+step*k+step*.35,.016,SPRING,body,12)
    bumper(length+.03,width+.03,.105+lift,body)
    for face in range(4):
        angle=face*math.pi/2;distance=(length if face%2==0 else width)/2-d['armor_inset_m']+d['armor_mount_offset_m']
        mount=empty('ArmorMount_'+str(face),body)
        mount.location=(distance*math.cos(angle),distance*math.sin(angle),d['armor_center_z_m']);mount.rotation_euler[2]=angle
        armor_module(slot,mount,d['armor_width_m'],d['armor_height_m'])
    chassis_modules(slot,d,body,deck,length,width)
    battery('Battery',(-hl*.45,0,deck),body)
    return deck


def gimbal(slot,d,carrier,deck,yaw_height=None):
    """Yaw motor on the chassis, yaw frame with cheeks, pitch axis at the muzzle
    height and a friction-wheel launcher with its speed module."""
    muzzle=d['muzzle_z_m'];reach=d['muzzle_reach_m'];hero=d['role']=='hero'
    base=yaw_height if yaw_height is not None else deck
    gm6020('YawMotor',(0,0,base+.016),(0,0,1),carrier)
    turret=empty('Turret',carrier)
    pitch=empty('GunPitch',turret);pitch.location=(0,0,muzzle)
    plate_z=base+.04
    c4_local_prism('YawPlate',[(.08,-.09),(.08,.09),(-.12,.09),(-.15,.06),(-.15,-.06),(-.12,-.09)],.006,CARBON,turret,'z',plate_z,.002)
    cyl('SlipRing',.022,.03,(0,0,plate_z+.02),ALLOY,turret,vertices=16)
    cheek=.125 if hero else .085
    for side in (-1,1):
        # Cheek plate with lightening pockets from the yaw plate to the pitch axis.
        c4_local_prism('GimbalCheek',[(-.05,0),(.05,0),(.035,muzzle-plate_z+.03),(-.035,muzzle-plate_z+.03)],.006,CARBON,turret,'y',side*cheek-.003).location=(0,0,plate_z)
        for z in (.35,.7):cyl('CheekPocket',.012,.0065,(0,side*cheek,plate_z+(muzzle-plate_z)*z),ROBOT_MATTE,turret,(math.pi/2,0,0),10)
        cyl('PitchBearing',.016,.012,(0,side*(cheek+.008),muzzle),ALLOY,turret,(math.pi/2,0,0),16)
    gm6020('PitchMotor',(0,-(cheek+.03),muzzle),(0,1,0),turret)
    # Launcher on the pitch axis.
    bore=.0235 if hero else .0115
    rod('BarrelTube',(.06,0,0),(reach-.05,0,0),bore+(.004 if hero else .003),ALLOY,pitch,24)
    speed_module('MuzzleSpeedModule',reach,42 if hero else 17,pitch)
    wheel_r=.042 if hero else .03
    for side in (-1,1):
        y=side*(bore+wheel_r+.002)
        cyl('FrictionWheel',wheel_r,.026 if hero else .018,(.02,y,0),TYRE,pitch,vertices=24)
        cyl('FrictionHub',wheel_r*.55,(.028 if hero else .02),(.02,y,0),ALLOY,pitch,vertices=16)
        m3508('FrictionMotor',(.02,y,-(.018 if hero else .012)),(0,0,-1),pitch,.85 if hero else .7)
    box('LauncherFrame',(.11,2*(bore+2*wheel_r)+.03,.008),(.02,0,(.02 if hero else .014)),ROBOT_ALUMINUM,pitch,.002)
    box('LauncherFrameLow',(.11,2*(bore+2*wheel_r)+.03,.008),(.02,0,-(.03 if hero else .022)),ROBOT_ALUMINUM,pitch,.002)
    # Feeder (dial) behind the barrel and the camera above it.
    cyl('FeederDial',.045 if hero else .034,.022,(-.06,0,.02),ROBOT_MATTE,pitch,vertices=24)
    m3508('FeederMotor',(-.06,0,.031),(0,0,1),pitch,.55)
    box('VisionCamera',(.034,.03,.03),(.035,0,.05 if hero else .045),ROBOT_MATTE,pitch,.003)
    cyl('VisionLens',.0105,.026,(.065,0,.05 if hero else .045),ROBOT_MATTE,pitch,(0,math.pi/2,0),16)
    cyl('VisionGlass',.008,.002,(.079,0,.05 if hero else .045),LENS,pitch,(0,math.pi/2,0),16)
    # Magazine on the yaw frame feeding the dial through a short chute.
    chamber=.15 if slot==4 else .18 if hero else .12
    mag=empty('Magazine',turret);mag.location=(-.11,0,muzzle+.01)
    box('MagazineBox',(chamber*.9,chamber,chamber*.6),(0,0,0),ROBOT_PANEL,mag,.008)
    box('MagazineLid',(chamber*.92,chamber*1.02,.008),(0,0,chamber*.3+.004),ROBOT_MATTE,mag,.003)
    rod('FeedChute',(-.11+chamber*.3,0,muzzle-.01),(-.06,0,muzzle+.03),.016,ROBOT_MATTE,turret,12)
    vtm_camera('VideoTransmitter',(-.11,chamber/2+.03,muzzle-.025),turret)
    light_bar('LightBar',(-.11-chamber*.45-.02,0,muzzle-.06),0,turret,.03)
    beam('ProtectedCableLoom',(-.05,0,plate_z+.03),(0,0,muzzle-.04),.008,ROBOT_MATTE,turret)
    return turret,pitch


def spec_ground_robot(slot,d):
    reset();root=empty('Robot');body=empty('Chassis',root)
    if d.get("base_model",slot)==7 or d.get("transform_allowed"):
        deck=mecanum_chassis(d.get("base_model",slot),d,body,well=True)
        # Lifting gimbal: two linear guides; GunElevator drops 265 mm when crouched.
        if d.get('transform_allowed'):
            for k,y in enumerate((-.07,.07)):
                box('FixedLiftGuide',(.027,.027,.12),(0,y,.13),ROBOT_ALUMINUM,body,.002)
                mast=empty(f'FoldMast_{k}',body);mast.location=(0,y,.25)
                box('TelescopingRail',(.018,.018,.30),(0,0,0),ALLOY,mast,.002)
                mast['rest_height_m']=.30;mast['base_z_m']=.10;mast['folded_height_m']=.08
            screw=empty('FoldMast_Screw',body);screw.location=(-.04,0,.25)
            box('TelescopingScrew',(.01,.01,.30),(0,0,0),MOTOR_CAP,screw,0)
            screw['rest_height_m']=.30;screw['base_z_m']=.10;screw['folded_height_m']=.08
        else:
            for y in (-.07,.07):
                box('LiftGuide',(.022,.022,d['muzzle_z_m']-.03),(0,y,(d['muzzle_z_m']-.03)/2+.07),ROBOT_ALUMINUM,body,.002)
            box('LiftScrew',(.01,.01,d['muzzle_z_m']-.05),(-.04,0,(d['muzzle_z_m']-.05)/2+.075),MOTOR_CAP,body,0)
        m3508('LiftMotor',(-.04,0,.075),(0,0,-1),body,.7)
        lift=empty('GunElevator',body)
        box('LiftCarriage',(.05,.18,.03),(0,0,d['muzzle_z_m']-.12),ROBOT_ALUMINUM,lift,.003)
        gimbal(d.get("base_model",slot),d,lift,deck,d['muzzle_z_m']-.105)
    else:
        deck=mecanum_chassis(d.get("base_model",slot),d,body)
        lift=empty('GunElevator',body)
        gimbal(d.get("base_model",slot),d,lift,deck)
    verify_robot_envelope(slot,d)
    flatten_static(body)
    export(Path(d['asset']).stem)


def pose_transform(d,progress):
    bpy.data.objects['GunElevator'].location[2]=-(d['muzzle_z_m']-d['folded_muzzle_z_m'])*progress
    for obj in bpy.context.scene.objects:
        if obj.name.startswith('FoldMast_'):
            height=obj['rest_height_m']+(obj['folded_height_m']-obj['rest_height_m'])*progress
            obj.scale[2]=height/obj['rest_height_m'];obj.location[2]=obj['base_z_m']+height/2


def flatten_static(body):
    """Rigid sub-assemblies (armor, modules) join the chassis so the GLB batches them."""
    keep=('Wheel_','SteerModule_','FoldMast_','ArmorNumber','Aux_','Turret','GunPitch','GunElevator','Arm','Gripper','CarriedUnit','Leg','Rotor_','Magazine')
    for obj in list(bpy.context.scene.objects):
        if obj.type!='MESH':continue
        parent=obj.parent
        if parent and parent!=body and not parent.name.startswith(keep) and parent.name not in ('Robot','Chassis'):
            # Re-parent to the closest animated ancestor (or the chassis).
            target=parent
            while target and target!=body and not target.name.startswith(keep):target=target.parent
            matrix=obj.matrix_world.copy();obj.parent=target or body;obj.matrix_world=matrix


def bounded_arm_pose(arm,q):
    q=list(q)
    if 'workspace_half_m' in arm:
        half=arm['workspace_half_m'];yaw=q[0]+q[3];tool=arm['tool_length_m'];maximum=arm['limits'][2][1]
        for k,c in enumerate((math.cos(q[0]),math.sin(q[0]))):
            offset=(math.cos(yaw) if k==0 else math.sin(yaw))*math.cos(q[4])*tool
            if abs(c)>1e-8:maximum=min(maximum,((half if c>0 else -half)-arm['base_m'][k]-offset)/c)
        q[2]=min(q[2],max(maximum,arm['limits'][2][0]))
    return q


def pose_arm(arm,q,prefix=""):
    q=bounded_arm_pose(arm,q)
    slew=bpy.data.objects[prefix+'ArmSlew'];lift=bpy.data.objects[prefix+'ArmLift'];stage=bpy.data.objects[prefix+'ArmMastStage']
    reach=bpy.data.objects[prefix+'ArmReach'];wyaw=bpy.data.objects[prefix+'ArmWristYaw'];wpitch=bpy.data.objects[prefix+'ArmWristPitch'];roll=bpy.data.objects[prefix+'ArmWristRoll']
    slew.rotation_euler[2]=q[0];lift.location[2]=arm['shoulder_rest_z_m']-arm['base_m'][2]+q[1];stage.location[2]=q[1]/2
    reach.location[0]=q[2];wyaw.rotation_euler[2]=q[3];wpitch.rotation_euler[1]=q[4];roll.rotation_euler[0]=q[5]
    for k,side in enumerate((-1,1)):
        bpy.data.objects[prefix+f'GripperJaw_{k}'].location[1]=side*(.018+q[6]*arm['jaw_travel_m'])


def engineer_arm(d,body,prefix="",key="arm"):
    before=set(bpy.data.objects)
    """Lift/boom/three-axis wrist on a slewing base. Joint frames follow
    physics::arm_points exactly: slew about Z at base_m, shoulder at
    shoulder_rest_z + lift, wrist at +reach along the boom, tool 150 mm."""
    arm=d[key];base_z=arm['base_m'][2];rest=arm['shoulder_rest_z_m']-base_z
    slew=empty('ArmSlew',body);slew.location=tuple(arm['base_m'])
    cyl('SlewBearing',.08,.02,(0,0,-.006),ALLOY,slew,vertices=28)
    box('SlewDriveMotor',(.05,.05,.04),(-.09,0,.0),MOTOR,slew,.004)
    for y in (-.045,.045):
        box('MastOuterRail',(.03,.022,.32),(0,y,.16),ROBOT_ALUMINUM,slew,.002)
    box('MastHead',(.05,.12,.02),(0,0,.33),ROBOT_ALUMINUM,slew,.003)
    box('MastFoot',(.08,.14,.02),(0,0,.01),ROBOT_ALUMINUM,slew,.003)
    rod('LiftBelt',(-.022,0,.02),(-.022,0,.32),.004,ROBOT_MATTE,slew,6)
    m3508('LiftMotor',(-.04,0,.035),(-1,0,0),slew,.75)
    stage=empty('ArmMastStage',slew)
    for y in (-.03,.03):box('MastInnerRail',(.022,.016,.30),(.0,y,.20),ALLOY,stage,.002)
    lift=empty('ArmLift',slew);lift.location=(0,0,rest)
    box('LiftCarriage',(.07,.13,.06),(0,0,0),ROBOT_ALUMINUM,lift,.004)
    box('BoomOuter',(.32,.05,.05),(.04,0,0),ROBOT_PANEL,lift,.004)
    box('BoomTail',(.06,.07,.06),(-arm['boom_tail_m']+.03,0,0),MOTOR,lift,.004)
    m3508('ReachMotor',(-.09,0,.03),(1,0,0),lift,.6)
    rod('BoomCableChain',(-.08,0,.035),(.16,0,.035),.008,ROBOT_MATTE,lift,8)
    reach=empty('ArmReach',lift);reach.location=(arm['stowed'][2],0,0)
    box('BoomInner',(.30,.036,.036),(-.15,0,0),ALLOY,reach,.003)
    box('WristBlock',(.05,.05,.05),(-.015,0,0),ROBOT_MATTE,reach,.004)
    wyaw=empty('ArmWristYaw',reach)
    cyl('WristYawMotor',.024,.024,(0,0,.032),MOTOR,wyaw,vertices=18)
    wpitch=empty('ArmWristPitch',wyaw)
    for y in (-.032,.032):box('WristYoke',(.05,.008,.05),(.015,y,0),ROBOT_ALUMINUM,wpitch,.002)
    cyl('WristPitchMotor',.022,.018,(0,-.047,0),MOTOR,wpitch,(math.pi/2,0,0),18)
    roll=empty('ArmWristRoll',wpitch)
    cyl('WristRollMotor',.021,.03,(.035,0,0),MOTOR_CAP,roll,(0,math.pi/2,0),18)
    box('GripperPalm',(.03,.075,.04),(.062,0,0),ROBOT_MATTE,roll,.004)
    cyl('SuctionCup',.017,.03,(.09,0,0),ROBOT_MATTE,roll,(0,math.pi/2,0),16)
    cyl('SuctionLip',.02,.006,(.108,0,0),TYRE,roll,(0,math.pi/2,0),16)
    for k,side in enumerate((-1,1)):
        jaw=empty(f'GripperJaw_{k}',roll);jaw.location=(0,side*.018,0)
        box('JawGuide',(.024,.01,.012),(.066,0,0),ALLOY,jaw,.002)
        c4_local_prism('JawFinger',[(.075,-.018),(.15,-.012),(.15,.012),(.075,.018)],.008,ROBOT_ALUMINUM,jaw,'y',-.004)
        box('JawPad',(.05,.003,.022),(.122,-side*.006,0),TYRE,jaw,.001)
    vtm_camera('ArmCamera',(-.01,.085,.22),slew,0)
    if prefix:
        for obj in set(bpy.data.objects)-before:obj.name=prefix+(obj.name.rsplit('.',1)[0] if obj.name.rsplit('.',1)[-1].isdigit() else obj.name)
    pose_arm(arm,arm['stowed'],prefix)


def spec_engineer(d):
    reset();root=empty('Robot');body=empty('Chassis',root)
    deck=mecanum_chassis(2,d,body)
    engineer_arm(d,body)
    if d.get("arm_count")==2:engineer_arm(d,body,"Aux_","arm2")
    # Two energy-unit cradles aft of the mast.
    for i,y in enumerate((-.07,.07)):
        box('UnitCradle',(.10,.10,.012),(-.17,y,deck+.006),ROBOT_ALUMINUM,body,.003)
        for k in range(3):
            a=k*math.tau/3;rod('UnitCradlePost',(-.17+.05*math.cos(a),y+.05*math.sin(a),deck),(-.17+.05*math.cos(a),y+.05*math.sin(a),deck+.06),.004,ROBOT_ALUMINUM,body,6)
        unit=empty('CarriedUnit_'+str(i),body);unit.location=(-.17,y,deck+.012)
        energy_unit('CarriedEnergyUnit',unit)
    light_bar('LightBar',(.15,0,deck),0,body,.035)
    verify_robot_envelope(d['slot'],d)
    flatten_static(body)
    export(Path(d['asset']).stem)


def leg_points(d,length):
    """Five-bar leg geometry (side view, robot X/Z): two hip motors and the axle."""
    hip=d['hip_height_m']
    return (.075,hip+.07),(-.075,hip+.07),(0,hip-length)


def leg_ik(pivot,target,a,b,outward):
    dx,dz=target[0]-pivot[0],target[1]-pivot[1];dist=max(1e-6,math.hypot(dx,dz))
    cos_a=max(-1,min(1,(a*a+dist*dist-b*b)/(2*a*dist)));base=math.atan2(dz,dx)
    knee_angle=base+outward*math.acos(cos_a)
    return (pivot[0]+a*math.cos(knee_angle),pivot[1]+a*math.sin(knee_angle))


def link_angle(p,q):
    """Rotation about +Y that turns a link built along -Z to point from p to q."""
    return math.atan2(-(q[0]-p[0]),-(q[1]-p[1]))


def serial_leg_points(d,length,swing=0.0):
    """Serial leg (side view, robot X/Z): hip joint, knee and wheel axle. The knee trails
    the hip-axle line; `swing` turns the whole leg about the hip (the engine's hip angle)."""
    hip=d['hip_height_m'];a,b=d['leg_upper_m'],d['leg_lower_m']
    length=max(abs(a-b)+.002,min(a+b-.002,length))
    bend=math.acos(max(-1,min(1,(a*a+length*length-b*b)/(2*a*length))))
    knee=(-a*math.sin(swing+bend),hip-a*math.cos(swing+bend))
    return (0,hip),knee,(-length*math.sin(swing),hip-length*math.cos(swing))


def pose_legs(d,length,swing=0.0):
    if d.get('leg_type')=='serial':
        hip,knee,axle=serial_leg_points(d,length,swing)
        for side,suffix in ((0,'R'),(1,'L')):
            thigh=bpy.data.objects[f'Leg{suffix}_Thigh'];shank=bpy.data.objects[f'Leg{suffix}_Shank']
            au=link_angle(hip,knee);al=link_angle(knee,axle)
            thigh.rotation_euler[1]=au;shank.rotation_euler[1]=al-au
            wheel=bpy.data.objects[f'Wheel_{side}'];wheel.location[0]=axle[0];wheel.location[2]=axle[1]
        return
    front,rear,axle=leg_points(d,length)
    for side,suffix in ((0,'R'),(1,'L')):
        for pivot,label,out in ((front,'F',1),(rear,'B',-1)):
            knee=leg_ik(pivot,axle,LEG_UPPER,LEG_LOWER,out if label=='F' else -1)
            upper=bpy.data.objects[f'Leg{suffix}{label}_Upper'];lower=bpy.data.objects[f'Leg{suffix}{label}_Lower']
            au=link_angle(pivot,knee);al=link_angle(knee,axle)
            upper.rotation_euler[1]=au;lower.rotation_euler[1]=al-au
        bpy.data.objects[f'Wheel_{side}'].location[2]=axle[1]


LEG_UPPER=.15
LEG_LOWER=.29


def hub_wheel(d,parent,name,location):
    r=d['wheel_radius_m'];wheel=empty(name,parent);wheel.location=location
    cyl('Tyre',r,d['wheel_width_m'],(0,0,0),RUBBER,wheel,(math.pi/2,0,0),36)
    cyl('TyreTread',r*1.005,d['wheel_width_m']*.6,(0,0,0),TYRE,wheel,(math.pi/2,0,0),36)
    cyl('HubMotor',r*.62,d['wheel_width_m']*1.06,(0,0,0),MOTOR,wheel,(math.pi/2,0,0),28)
    cyl('HubCap',r*.35,d['wheel_width_m']*1.12,(0,0,0),MOTOR_CAP,wheel,(math.pi/2,0,0),20)
    for k in range(6):
        a=k*math.tau/6;box('HubSpoke',(.008,d['wheel_width_m']*1.08,r*.3),(r*.45*math.cos(a),0,r*.45*math.sin(a)),ALLOY,wheel,.001).rotation_euler[1]=-a
    return wheel


def serial_legs(d,body,hw,track):
    """I-L serial legs per side: a joint motor on the hip axle (no end stops), the thigh
    with the knee belt drive, the shank and the hub wheel outboard of the leg. Nodes
    Leg{R,L}_Thigh (at the hip) and Leg{R,L}_Shank (at the knee) carry the animation."""
    hip=d['hip_height_m'];a,b=LEG_UPPER,LEG_LOWER;width=d['wheel_width_m']
    for side,suffix,wheel_index in ((-1,'R',0),(1,'L',1)):
        inner=hw+.004;plane=track-width/2-.012
        box('HipMountPlate',(.15,.008,.11),(0,side*(hw+.002),hip),ROBOT_ALUMINUM,body,.003)
        for x in (-.06,.06):box('HipMountRib',(.012,.012,.10),(x,side*(hw-.006),hip),ROBOT_ALUMINUM,body,.002)
        # Hip joint actuator: stator housing, output flange and the coaxial knee motor inboard.
        rod('HipJointStator',(0,side*inner,hip),(0,side*(inner+.024),hip),.047,MOTOR,body,32)
        rod('HipJointRing',(0,side*(inner+.024),hip),(0,side*(inner+.028),hip),.042,MOTOR_CAP,body,32)
        for k in range(8):
            t=k*math.tau/8;rod('HipJointBolt',(.036*math.cos(t),side*(inner+.028),hip+.036*math.sin(t)),(.036*math.cos(t),side*(inner+.031),hip+.036*math.sin(t)),.004,ALLOY,body,6)
        rod('KneeDriveMotor',(0,side*(hw-.05),hip),(0,side*(hw-.004),hip),.034,MOTOR,body,24)
        thigh=empty(f'Leg{suffix}_Thigh',body);thigh.location=(0,side*(plane-.01),hip)
        rod('HipOutputFlange',(0,-side*.006,0),(0,side*.002,0),.032,ALLOY,thigh,24)
        for y in (-.005,.005):bar('ThighPlate',(0,y,.012),(0,y,-a-.012),.04,.004,ROBOT_ALUMINUM,thigh)
        bar('KneeBeltCover',(0,side*.009,-.01),(0,side*.009,-a+.01),.03,.006,CARBON,thigh)
        rod('HipPulley',(0,-.006,0),(0,.006,0),.026,ALLOY,thigh,20)
        rod('KneePulley',(0,-.006,-a),(0,.006,-a),.02,ALLOY,thigh,20)
        shank=empty(f'Leg{suffix}_Shank',thigh);shank.location=(0,side*.014,-a)
        rod('KneeJointCap',(0,-side*.004,0),(0,side*.008,0),.022,MOTOR_CAP,shank,20)
        bar('ShankTube',(0,0,.01),(0,0,-b+.03),.028,.012,CARBON,shank)
        bar('ShankFork',(0,0,-b+.045),(0,0,-b),.04,.012,ROBOT_ALUMINUM,shank)
        rod('AxleBoss',(0,-side*.006,-b),(0,side*.012,-b),.018,ALLOY,shank,16)
        hub_wheel(d,body,f'Wheel_{wheel_index}',(0,side*track,hip-d['leg_nominal_m']))


def spec_wheel_legged(d):
    """W3: balancing two-wheel-legged infantry. Body at the hip axle, five-bar
    legs per side (Leg{R,L}{F,B}_Upper/_Lower), hub-motor wheels Wheel_0 (right)
    and Wheel_1 (left) whose height follows the leg length."""
    global LEG_UPPER,LEG_LOWER
    LEG_UPPER=d.get('leg_upper_m',.15);LEG_LOWER=d.get('leg_lower_m',.29)
    reset();root=empty('Robot');body=empty('Chassis',root);serial=d.get('leg_type')=='serial'
    # Leg geometry travels in glTF extras so the viewer solves the same linkage.
    root['leg_geometry']=json.dumps({'type':'serial','hip_height_m':d['hip_height_m'],'upper_m':LEG_UPPER,'lower_m':LEG_LOWER} if serial else
        {'hip_height_m':d['hip_height_m'],'upper_m':LEG_UPPER,'lower_m':LEG_LOWER,'pivot_x_m':.075,'pivot_above_hip_m':.07})
    length,width,height=d['chassis_size_m'];hip=d['hip_height_m'];r=d['wheel_radius_m'];hl,hw=length/2,width/2
    c4_local_prism('BodyBottomPlate',[(hl-.03,-hw),(hl,-hw+.03),(hl,hw-.03),(hl-.03,hw),(-hl+.03,hw),(-hl,hw-.03),(-hl,-hw+.03),(-hl+.03,-hw)],.006,CARBON,body,'z',hip-height/2,.002)
    c4_local_prism('BodyTopPlate',[(hl*.8,-hw*.9),(hl*.8,hw*.9),(-hl*.85,hw*.9),(-hl*.85,-hw*.9)],.005,CARBON,body,'z',hip+height/2-.005,.002)
    for y in (-hw+.012,hw-.012):box('BodySideFrame',(length*.9,.012,height-.012),(0,y,hip),ROBOT_ALUMINUM,body,.002)
    for x in (-hl*.7,hl*.7):box('BodyBulkhead',(.012,width*.9,height-.012),(x,0,hip),ROBOT_ALUMINUM,body,.002)
    box('ImuController',(.06,.05,.02),(0,0,hip-.02),ROBOT_MATTE,body,.003)
    for face in range(4):
        angle=face*math.pi/2;distance=(length if face%2==0 else width)/2-d['armor_inset_m']+d['armor_mount_offset_m']
        mount=empty('ArmorMount_'+str(face),body)
        z=d.get('armor_side_center_z_m',d['armor_center_z_m']) if face%2 else d['armor_center_z_m']
        mount.location=(distance*math.cos(angle),distance*math.sin(angle),z);mount.rotation_euler[2]=angle
        armor_module(1 if d["role"]=="hero" else 3,mount,d['armor_width_m'],d['armor_height_m'])
        if face%2 and z<hip-height/2:
            # Side plates hang below the body on two drop brackets, clear of the hip joints.
            for x in (-.05,.05):bar('ArmorDropBracket',(x,mount.location[1]*.93,hip-height/2+.004),(x,mount.location[1]*.93,z+.03),.016,.006,ROBOT_ALUMINUM,body)
    track=d['track_m']/2
    if serial:serial_legs(d,body,hw,track)
    # Legs: two hip motors per side drive a five-bar linkage to the wheel axle.
    for side,suffix,wheel_index in (() if serial else ((-1,'R',0),(1,'L',1))):
        y=side*(track+.012)
        front,rear,axle=leg_points(d,d['leg_nominal_m'])
        for pivot,label in ((front,'F'),(rear,'B')):
            gm6020('HipMotor',(pivot[0],side*(hw+.02),pivot[1]),(0,side,0),body)
            upper=empty(f'Leg{suffix}{label}_Upper',body);upper.location=(pivot[0],y,pivot[1])
            bar('ThighLink',(0,0,.008),(0,0,-LEG_UPPER-.008),.022,.012,ROBOT_ALUMINUM,upper)
            lower=empty(f'Leg{suffix}{label}_Lower',upper);lower.location=(0,0,-LEG_UPPER)
            cyl('KneePin',.011,.03,(0,0,0),ALLOY,lower,(math.pi/2,0,0),12)
            bar('ShinLink',(0,side*.006,0),(0,side*.006,-LEG_LOWER),.018,.01,CARBON if label=='F' else ROBOT_ALUMINUM,lower)
        box('LegMountPlate',(.24,.008,.07),(0,side*(hw+.002),hip+.06),ROBOT_ALUMINUM,body,.002)
        wheel=empty(f'Wheel_{wheel_index}',body);wheel.location=(0,side*track,axle[1])
        cyl('Tyre',r,d['wheel_width_m'],(0,0,0),RUBBER,wheel,(math.pi/2,0,0),36)
        cyl('TyreTread',r*1.005,d['wheel_width_m']*.6,(0,0,0),TYRE,wheel,(math.pi/2,0,0),36)
        cyl('HubMotor',r*.62,d['wheel_width_m']*1.06,(0,0,0),MOTOR,wheel,(math.pi/2,0,0),28)
        cyl('HubCap',r*.35,d['wheel_width_m']*1.12,(0,0,0),MOTOR_CAP,wheel,(math.pi/2,0,0),20)
        for k in range(6):
            a=k*math.tau/6;box('HubSpoke',(.008,d['wheel_width_m']*1.08,r*.3),(r*.45*math.cos(a),0,r*.45*math.sin(a)),ALLOY,wheel,.001).rotation_euler[1]=-a
    # Front skid bumper protects the armor when the body pitches.
    bumper(length+.03,width-.02,hip-height/2+.01,body,.008)
    referee_box('JudgeMainControl',(.063,.076,.014),(-hl*.45,0,hip+height/2+.007),body,REF_GRAY,True)
    referee_box('PowerManagement',(.09,.062,.026),(-hl*.2,-hw*.4,hip-.03),body)
    referee_box('PositioningModule',(.045,.045,.016),(hl*.35,hw*.45,hip+height/2+.008),body)
    referee_box('FieldInteractionModule',(.07,.05,.008),(0,0,hip-height/2-.005),body,ROBOT_MATTE)
    local=empty('SuperCapModule',body);local.location=(hl*.2,-hw*.35,hip-.045)
    for k in range(5):cyl('SuperCapCell',.011,.06,(-.04+k*.02,0,0),MOTOR_CAP,local,(math.pi/2,0,0),12)
    box('WirelessRxBracket',(.02,.08,.12),(hl-.01,0,.21),ROBOT_ALUMINUM,body,.003)
    box('WirelessRxFace',(.006,.1,.1),(hl+.003,0,.16),ROBOT_MATTE,body,.003)
    battery('Battery',(-hl*.2,hw*.2,hip-.035),body)
    lift=empty('GunElevator',body)
    gimbal(1 if d["role"]=="hero" else 3,d,lift,hip+height/2)
    pose_legs(d,d['leg_nominal_m'])
    verify_robot_envelope(d['slot'],d)
    pose_legs(d,d['leg_nominal_m'])
    flatten_static(body)
    export(Path(d['asset']).stem)


def mesh_guard(name,x,y,z,radius,height,parent):
    # Both caps and the cylindrical wall are closed by a 25 mm mesh.
    vertices,faces=[],[]
    def wire(a,b,thickness=.0018):
        v=Vector(b)-Vector(a)
        axis=v.normalized();side=axis.cross(Vector((0,0,1)))
        if side.length<.01:side=Vector((1,0,0))
        side.normalize();up=axis.cross(side);i=len(vertices)
        for point in [Vector(a),Vector(b)]:
            for s,t in [(-1,-1),(1,-1),(1,1),(-1,1)]:vertices.append(tuple(point+(side*s+up*t)*thickness/2))
        faces.extend([tuple(i+j for j in f) for f in [(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]])
    for zz in [z-height/2,z+height/2]:
        for i in range(-math.floor(radius/.025),math.floor(radius/.025)+1):
            offset=i*.025;span=math.sqrt(radius*radius-offset*offset)
            wire((x-span,y+offset,zz),(x+span,y+offset,zz));wire((x+offset,y-span,zz),(x+offset,y+span,zz))
    count=math.ceil(math.tau*radius/.025)
    for i in range(count):
        a=i*math.tau/count
        wire((x+radius*math.cos(a),y+radius*math.sin(a),z-height/2),(x+radius*math.cos(a),y+radius*math.sin(a),z+height/2),.003)
    for j in range(8):
        zz=z-height/2+j*height/7
        for i in range(count):
            a=i*math.tau/count;b=(i+1)*math.tau/count
            wire((x+radius*math.cos(a),y+radius*math.sin(a),zz),(x+radius*math.cos(b),y+radius*math.sin(b),zz),.0025)
    c4_mesh(name,vertices,faces,ROBOT_MATTE,parent)


def spec_air_robot(d):
    reset();root=empty('Robot');body=empty('Chassis',root)
    c4_local_prism('CentralAirframe',[(.19,-.10),(.19,.10),(.12,.15),(-.12,.15),(-.19,.10),(-.19,-.10),(-.12,-.15),(.12,-.15)],.012,CARBON,body,'z',.17,.002)
    c4_local_prism('UpperAirframe',[(.15,-.09),(.15,.09),(-.15,.09),(-.15,-.09)],.006,CARBON,body,'z',.26,.002)
    for x in (-.13,.13):
        for y in (-.075,.075):box('AirframeStandoff',(.012,.012,.08),(x,y,.22),ROBOT_ALUMINUM,body,.001)
    box('FlightController',(.06,.06,.02),(0,0,.192),ROBOT_PANEL,body,.004)
    box('MechanicalBatteryCradle',(.27,.22,.012),(0,0,.272),ROBOT_ALUMINUM,body,.003)
    for y in (-.055,.055):box('FlightBattery',(.25,.09,.06),(0,y,.31),ROBOT_MATTE,body,.008)
    centers=[(.46*math.cos(k*math.tau/6),.46*math.sin(k*math.tau/6)) for k in range(6)] if d.get('rotor_count',4)==6 else [(-.33,-.33),(-.33,.33),(.33,-.33),(.33,.33)]
    for i,(x,y) in enumerate(centers):
        rod('RotorArmTube',(x*.25,y*.25,.2),(x,y,.27),.016,CARBON,body,16)
        box('ArmClamp',(.05,.05,.03),(x*.28,y*.28,.205),ROBOT_ALUMINUM,body,.003)
        cyl('BrushlessMotor',.040,.045,(x,y,.282),MOTOR,body,vertices=24)
        cyl('MotorBell',.036,.012,(x,y,.31),MOTOR_CAP,body,vertices=24)
        box('MotorEsc',(.06,.03,.012),((x*.7),(y*.7),.24),ROBOT_MATTE,body,.002)
        rotor=empty('Rotor_'+str(i),body);rotor.location=(x,y,.32)
        box('PropellerBlade',(2*d['rotor_radius_m'],.03,.006),(0,0,0),CARBON,rotor,.004)
        cyl('PropHub',.016,.016,(0,0,0),ALLOY,rotor,vertices=12)
        mesh_guard('FullPropellerGuard',x,y,.30,d['guard_radius_m'],d['guard_height_m'],body)
        for k in range(4):
            a=k*math.pi/2+math.pi/4;rod('GuardStrut',(x+.05*math.cos(a),y+.05*math.sin(a),.24),(x+d['guard_radius_m']*math.cos(a),y+d['guard_radius_m']*math.sin(a),.30-d['guard_height_m']/2),.005,ROBOT_ALUMINUM,body,6)
        # Four 440 mm upward LED strips total 1.76 m. Never place LEDs on blades.
        box('TeamNavTop',(.44,.007,.005),(x,y,.30+d['guard_height_m']/2+.006),GLOW,body,.002)
    for y in [-.11,.11]:
        beam('LandingSkid',(-.16,y,.018),(.16,y,.018),.02,ROBOT_MATTE,body)
        for x in [-.11,.11]:rod('LandingStrut',(x,y,.02),(x*.8,y*.8,.17),.008,CARBON,body,8)
    cyl('RigidSafetyMast',.013,.35,(0,0,.475),ROBOT_ALUMINUM,body,vertices=16)
    bpy.ops.mesh.primitive_torus_add(major_radius=.025,minor_radius=.003,location=(0,0,.65),rotation=(math.pi/2,0,0),major_segments=24,minor_segments=8)
    finish(bpy.context.object,'SafetyHookRing',ROBOT_ALUMINUM,body)
    beam('ProtectedCableLoom',(.07,0,.24),(0,0,.65),.006,ROBOT_MATTE,body)
    referee_box('PositioningModule',(.045,.045,.016),(-.12,0,.37),body)
    referee_box('JudgeMainControl',(.063,.076,.014),(.13,0,.272),body,REF_GRAY,True)
    turret=empty('Turret',body)
    gm6020('AirYawMotor',(0,0,.152),(0,0,1),turret)
    for side in (-1,1):box('AirGimbalCheek',(.06,.006,.08),(0,side*.05,.1),CARBON,turret,.002)
    pitch=empty('GunPitch',turret);pitch.location=(0,0,.10)
    rod('17mmAirBarrel',(.0,0,0),(.21,0,0),.0145,ALLOY,pitch,20)
    speed_module('AirMuzzleSpeedModule',.26,17,pitch)
    for side in (-1,1):cyl('AirFrictionWheel',.025,.016,(.03,side*.04,0),TYRE,pitch,vertices=20)
    box('FPVCamera',(.04,.055,.025),(.025,0,-.035),ROBOT_MATTE,pitch,.004)
    box('CameraLens',(.005,.02,.015),(.048,0,-.035),LENS,pitch,.002)
    box('RetainedAmmoMagazine',(.18,.16,.06),(-.08,0,.13),ROBOT_PANEL,body,.007)
    vtm_camera('VideoTransmitter',(.14,0,.18),body)
    verify_robot_envelope(d['slot'],d)
    export(Path(d['asset']).stem)


def spec_robots():
    spec_materials()
    only=set(filter(None,os.environ.get('RMUC_ROBOTS','').split(',')))
    for slot,design in CONFIG['robot_designs'].items():
        if only and slot not in only:continue
        if design.get('season')=='2027':season2027_robot(design);continue  # season2027.py
        if design['role']=='aerial':spec_air_robot(design)
        elif design['role']=='engineer':spec_engineer(design)
        elif design.get('chassis_type')=='wheel_legged':spec_wheel_legged(design)
        else:spec_ground_robot(int(slot),design)
