"""RMUC 2027 assets, loaded by build_assets.py after chapter4.py and robot_specs.py.

Field: maps.rmuc2027 (scripts/chapter4_2027_layout.py) in the chapter-4 style, with the 2027
fixtures (workbench, resource hub, hangar platforms on the rune gantry, dart stations).
Robots: heavies (engineer chassis and arm(s) plus a gimbal whose 42 mm launcher lives under
`LauncherModule`), infantry and sentries derived from their 2026 base builders, and aerial
systems (hangar GLB plus one drone GLB per system). Only robot_designs entries with
season == '2027' and maps with season == '2027' are built here.
"""

S27_ENV = CONFIG['rulebook_2027']['construction']['envelope']
S27_REPORT = {}
# Use the same two S68 envelope alternatives as lineup inspection. Blender is
# launched outside scripts/, so load the shared check by its explicit path.
import importlib.util
_s27_spec = importlib.util.spec_from_file_location('s27_construction', ROOT/'scripts/robot_compliance.py')
_s27_construction = importlib.util.module_from_spec(_s27_spec)
_s27_spec.loader.exec_module(_s27_construction)


# ---------------------------------------------------------------------------- helpers

def s27_cyl(name, radius, depth, pos, material, parent, rotation=(0, 0, 0), vertices=16, bevel=0):
    """Cylinder without the default 8 mm bevel (small parts of the drones and the hangar)."""
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=pos, rotation=rotation)
    return finish(bpy.context.object, name, material, parent, bevel)


def s27_ring_z(name, r_in, r_out, depth, z, material, parent, centre=(0, 0), segments=40):
    """Annulus in the XY plane from z to z+depth (c4_ring is built along +X; turn it upright)."""
    obj = c4_ring(name, r_in, r_out, depth, material, parent, 0, segments)
    obj.rotation_euler = (0, -math.pi/2, 0)
    obj.location = (centre[0], centre[1], z)
    return obj


def s27_bars(name, segments, thickness, material, parent):
    """Many thin square bars in one mesh (guard grilles, wire frames)."""
    vertices, faces = [], []
    for a, b in segments:
        v = Vector(b)-Vector(a)
        if v.length < 1e-6:
            continue
        axis = v.normalized(); side = axis.cross(Vector((0, 0, 1)))
        if side.length < .01:
            side = Vector((1, 0, 0))
        side.normalize(); up = axis.cross(side); i = len(vertices)
        for point in (Vector(a), Vector(b)):
            for s, t in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                vertices.append(tuple(point+(side*s+up*t)*thickness/2))
        faces.extend([tuple(i+j for j in f) for f in [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]])
    return c4_mesh(name, vertices, faces, material, parent)


def s27_flat_text(text, size, location, rot_z, material, parent, depth=.0006):
    """Text lying flat (readable from above), converted to a mesh."""
    curve = bpy.data.curves.new('Badge', 'FONT'); curve.body = text; curve.size = size
    curve.align_x = 'CENTER'; curve.align_y = 'CENTER'; curve.extrude = depth
    obj = bpy.data.objects.new('BadgeText', curve); bpy.context.collection.objects.link(obj)
    obj.parent = parent; obj.location = location; obj.rotation_euler[2] = rot_z; curve.materials.append(material)
    bpy.ops.object.select_all(action='DESELECT'); bpy.context.view_layer.objects.active = obj; obj.select_set(True)
    bpy.ops.object.convert(target='MESH'); obj.select_set(False)
    return obj


def s27_side_text(text, size, location, facing, material, parent, depth=.0006):
    """Text standing on a face whose outward normal is +Y (facing=1) or -Y (facing=-1)."""
    obj = c4_text_x(text, size, location, material, parent, depth)
    obj.rotation_euler = (math.pi/2, 0, math.pi if facing > 0 else 0)
    return obj


def s27_badge(parent, location, rot_z=0, text='27', width=.075, depth=.048):
    """2027 livery badge: orange plate with a dark season number."""
    box('Badge2027', (width, depth, .004), location, ORANGE, parent, .0015)
    s27_flat_text(text, depth*.62, (location[0], location[1], location[2]+.0021), rot_z, ROBOT_MATTE, parent)


# ---------------------------------------------------------------------------- field

S27_FIXTURE_WALLS = ('_dart_station', '_workbench', '_resource_frame', '_hangar_platform_roof')


def s27_support(arena, t):
    """Lowest terrain under polygon t (other terrain only), sampled just inside its corners."""
    pts = t['polygon']; cx = sum(p[0] for p in pts)/len(pts); cy = sum(p[1] for p in pts)/len(pts)
    samples = [(cx, cy)]
    for x, y in pts:
        d = math.hypot(cx-x, cy-y) or 1
        samples.append((x+(cx-x)/d*.02, y+(cy-y)/d*.02))
    others = [o for o in arena['terrain'] if o is not t]
    return min(max([0]+[c4_height(o, x, y) for o in others if c4_inside(x, y, o['polygon'])]) for x, y in samples)


def s27_clip(points, elevations, low):
    """Clip a field polygon at the centreline y = 7.5 (keep the low or the high side),
    interpolating the per-vertex elevation above the floor."""
    out = []; n = len(points)
    inside = (lambda p: p[1] <= 7.5+1e-9) if low else (lambda p: p[1] >= 7.5-1e-9)
    for i in range(n):
        a, b = points[i], points[(i+1) % n]; ea, eb = elevations[i], elevations[(i+1) % n]
        if inside(a):
            out.append((list(a), ea))
        if inside(a) != inside(b):
            t = (7.5-a[1])/(b[1]-a[1]); out.append(([a[0]+(b[0]-a[0])*t, 7.5], ea+(eb-ea)*t))
    return out


def s27_prism(name, points, elevations, material, parent, bottom=None):
    """c4_prism whose top follows the tilted floor exactly: the floor is a ridge at y = 7.5
    (1.5 deg toward both long sides), so polygons crossing it are split there."""
    if min(p[1] for p in points) < 7.5 < max(p[1] for p in points):
        for low in (True, False):
            part = s27_clip(points, elevations, low)
            if len(part) >= 3:
                c4_prism(name, [p for p, _ in part], [floor_z(p[1])+e for p, e in part], material, parent, bottom)
    else:
        c4_prism(name, points, [floor_z(p[1])+e for p, e in zip(points, elevations)], material, parent, bottom)


def s27_ridge(points, elevations):
    """Insert the centreline crossings into an outline so side walls follow the ridge too."""
    out_p, out_e = [], []
    for i in range(len(points)):
        a, b = points[i], points[(i+1) % len(points)]; ea, eb = elevations[i], elevations[(i+1) % len(points)]
        out_p.append(a); out_e.append(ea)
        if (a[1]-7.5)*(b[1]-7.5) < 0:
            t = (7.5-a[1])/(b[1]-a[1]); out_p.append([a[0]+(b[0]-a[0])*t, 7.5]); out_e.append(ea+(eb-ea)*t)
    return out_p, out_e


def s27_inset(points, distance):
    """Convex polygon moved inward by `distance` along every edge normal: the top of an
    edge-ramped terrain piece (the engine's slope is a function of distance to the edge)."""
    n = len(points); area = sum(a[0]*b[1]-b[0]*a[1] for a, b in zip(points, points[1:]+points[:1]))
    sign = 1 if area > 0 else -1
    lines = []
    for a, b in zip(points, points[1:]+points[:1]):
        dx, dy = b[0]-a[0], b[1]-a[1]; length = math.hypot(dx, dy)
        nx, ny = -dy/length*sign, dx/length*sign  # inward normal
        lines.append(((a[0]+nx*distance, a[1]+ny*distance), (dx, dy)))
    inner = []
    for i in range(n):
        (p1, d1), (p2, d2) = lines[i-1], lines[i]
        det = d1[0]*d2[1]-d1[1]*d2[0]
        t = ((p2[0]-p1[0])*d2[1]-(p2[1]-p1[1])*d2[0])/det
        inner.append([p1[0]+d1[0]*t, p1[1]+d1[1]*t])
    return inner


def s27_dense(points, closed, step=.25):
    """Split long paint segments so each piece follows the terrain level under it."""
    seq = [list(p) for p in points]+([list(points[0])] if closed else [])
    out = []
    for a, b in zip(seq, seq[1:]):
        n = max(1, math.ceil(math.dist(a, b)/step))
        out.extend([[a[0]+(b[0]-a[0])*i/n, a[1]+(b[1]-a[1])*i/n] for i in range(n)])
    out.append(seq[-1])
    return out


def s27_paint(arena, points, material, parent, width=.035, closed=False, step=.08):
    """Field paint strip that follows the terrain along its length (slopes, humps) and stays
    level across its width; on a terrain edge it sits on the higher side, like c4_paint."""
    pts = s27_dense(points, closed, step)
    vertices, faces = [], []
    for a, b in zip(pts, pts[1:]):
        dx, dy = b[0]-a[0], b[1]-a[1]; length = math.hypot(dx, dy)
        if length < 1e-4:
            continue
        ox, oy = -dy/length*width/2, dx/length*width/2
        za = max(c4_ground(arena, a[0]+ox, a[1]+oy), c4_ground(arena, a[0]-ox, a[1]-oy))+.008
        zb = max(c4_ground(arena, b[0]+ox, b[1]+oy), c4_ground(arena, b[0]-ox, b[1]-oy))+.008
        i = len(vertices)
        vertices.extend([(a[0]+ox-14, 7.5-a[1]-oy, za), (b[0]+ox-14, 7.5-b[1]-oy, zb), (b[0]-ox-14, 7.5-b[1]+oy, zb), (a[0]-ox-14, 7.5-a[1]+oy, za)])
        faces.append((i, i+3, i+2, i+1))
    if vertices:
        c4_mesh('CourtPaint', vertices, faces, material, parent)


def s27_local(root, name, point, yaw, z=None):
    """Empty at a field point (+X along the fixture's yaw), standing on the tilted floor."""
    x, y = point
    local = empty(name, root); local.location = (x-14, 7.5-y, floor_z(y) if z is None else z); local.rotation_euler[2] = -yaw
    return local


def s27_profile_wall(w, frame):
    """Tunnel rail or roof with bevelled top edges (figure 4-35 section A, figure 4-38): its
    cross-section extruded along the wall. `chamfer` lists the bevelled top edges: -1/+1 for
    the right/left side of the wall's a->b direction in field coordinates (the field's y is
    flipped in Blender, so field-left is local -y) and 'ends' to slope the top at both ends."""
    L, T, H = w['w'], w['h'], w['height']; c = w.get('chamfer_m', .04)
    profile = [(-T/2, 0), (T/2, 0)]
    profile += [(T/2, H-c), (T/2-c, H)] if -1 in w['chamfer'] else [(T/2, H)]
    profile += [(-T/2+c, H), (-T/2, H-c)] if 1 in w['chamfer'] else [(-T/2, H)]
    rings = [(-L/2, H), (L/2, H)]
    if 'ends' in w['chamfer']:
        rings = [(-L/2, H-c), (-L/2+c, H), (L/2-c, H), (L/2, H-c)]
    n = len(profile)
    vertices = [(x, y, min(z, top)) for x, top in rings for y, z in profile]
    faces = [tuple(reversed(range(n))), tuple(range((len(rings)-1)*n, len(rings)*n))]
    for r in range(len(rings)-1):
        faces += [(r*n+i, r*n+(i+1) % n, (r+1)*n+(i+1) % n, (r+1)*n+i) for i in range(n)]
    return c4_mesh(w['id']+'Body', vertices, faces, KERB, frame)


def s27_wall(w, root):
    """Box obstacle (x/y top-left of the unrotated rectangle, rotated about its centre)."""
    cx, cy = w['x']+w['w']/2, w['y']+w['h']/2
    frame = empty(w['id'], root); frame.location = (cx-14, 7.5-cy, w['bottom']); frame.rotation_euler[2] = -w['rotation']
    if w.get('chamfer'):
        s27_profile_wall(w, frame)
    else:
        box(w['id']+'Body', (w['w'], w['h'], w['height']), (0, 0, w['height']/2), KERB, frame, min(.01, w['height']/4))
    L, T, H = w['w'], w['h'], w['height']
    if '_tunnel_roof' in w['id']:
        # Hazard band round the roof's flat top (both tunnel portals are visible from either side).
        flat = T-2*w.get('chamfer_m', 0) if w.get('chamfer') else T
        for s in (-1, 1):
            box('RoofHazard', (L, .03, .004), (0, s*(flat/2-.015), H+.002), AMBER, frame, 0)
            box('RoofHazard', (.03, flat, .004), (s*(L/2-.015), 0, H+.002), AMBER, frame, 0)
    elif '_parapet_' in w['id']:
        box('ParapetCap', (L+.01, T+.02, .02), (0, 0, H+.01), STEEL, frame, .004)
    elif w['id'].startswith('central_') and '_kerb_' in w['id']:
        box('KerbCap', (L, T+.01, .012), (0, 0, H+.006), STEEL, frame, .003)
    return frame


def s27_dart_station(fixture, wall, root, color):
    """Dart launch station (scenery): closed bay on the wall's 2120 x 1100 x 1300 footprint,
    launch gate toward +X, sloped lid with the R mark, team lamps on the front edges."""
    local = s27_local(root, 'DartStation', fixture['point'], fixture['yaw'])
    L, W, H = wall['w'], wall['h'], wall['height']
    lid = mat('DartLidBlack', (.025, .027, .03), .3, .5)
    box('DartBase', (L, W, .1), (0, 0, .05), DARK, local, .008)
    front = L/2-.42
    for side in (-1, 1):
        c4_local_prism('DartSideFrame', [(-L/2, 0), (L/2, 0), (L/2, .92), (front, H), (-L/2, H)], .1, KERB, local, 'y', W/2-.1 if side > 0 else -W/2, .008)
        c4_strip('DartFrontLight', [(side*(W/2-.05), .14), (side*(W/2-.05), .88)], .03, .006, color, local, offset=L/2)
        box('DartSideRib', (L-.3, .006, .05), (-.1, side*(W/2+.003), .55), STEEL, local, .002)
    box('DartBackWall', (.06, W-.2, H), (-L/2+.03, 0, H/2), KERB, local, .006)
    box('DartLidTop', (front+L/2, W-.18, .05), ((front-L/2)/2, 0, H-.025), lid, local, .01)
    logo = c4_text_x('R', .34, (0, 0, 0), WHITE, local); logo.location = (-.35, 0, H+.002); logo.rotation_euler = (0, 0, math.pi/2)
    slope = empty('DartLidFront', local); slope.location = (front, 0, H); slope.rotation_euler[1] = math.atan2(H-.92, .42)
    box('DartLidPanel', (math.hypot(H-.92, .42), W-.18, .05), (math.hypot(H-.92, .42)/2, 0, -.025), lid, slope, .01)
    box('DartGate', (.03, W-.2, .78), (L/2-.015, 0, .1+.39), lid, local, .006)
    box('DartGateSeam', (.004, .006, .74), (L/2+.001, 0, .49), STEEL, local, 0)
    box('DartStatusLamp', (.02, .1, .03), (L/2+.002, 0, .9), color, local, .002)
    return local


def s27_resource_hub(fixture, wall, root, color):
    """Resource hub (figures 4-20..4-22, 2027): wall frame with a carousel presenting energy
    units on a vertical ring (diameter `ring_diameter_m`) whose centre is `hub_z_m` high; the
    units point into the field with their outer ends at the pick point. The unit staged at the
    hub centre (the engine's pick point) is `AvailableUnit_<team>`; five stock units sit on the
    ring, the sixth socket is the one the staged unit came from."""
    local = s27_local(root, 'ResourceHub', fixture['point'], fixture['yaw'])
    hub_z = fixture['hub_z_m']; ring = fixture['ring_diameter_m']/2
    back = -(fixture['point'][0]-wall['x']) if fixture['yaw'] == 0 else -(wall['x']+wall['w']-fixture['point'][0])
    face = back+wall['w']
    # Frame column against the wall.
    box('ResourceFrameBody', (wall['w'], wall['h'], wall['height']), ((back+face)/2, 0, wall['height']/2), KERB, local, .01)
    box('ResourceFrameCap', (wall['w']+.02, wall['h']+.02, .03), ((back+face)/2, 0, wall['height']+.015), STEEL, local, .004)
    for side in (-1, 1):
        c4_strip('ResourceStatusLamp', [(side*(wall['h']/2-.03), .08), (side*(wall['h']/2-.03), wall['height']-.06)], .03, .006, color, local, offset=face)
    hub = empty('ResourceCarousel', local); hub.location = (0, 0, hub_z)
    cyl('HubBackplate', ring+.055, .02, (face+.01-0, 0, 0), DARK, hub, (0, math.pi/2, 0), 48)
    hexagon = [((ring+.045)*math.cos(a), (ring+.045)*math.sin(a)) for a in [k*math.tau/6 for k in range(6)]]
    c4_local_prism('HubCarouselPlate', hexagon, .018, STEEL, hub, 'x', face+.02, .004)
    c4_ring('HubLampRing', ring+.035, ring+.045, .004, color, hub, face+.038, 48)
    cyl('HubSpindle', .035, .05, (face+.06, 0, 0), ALLOY, hub, (0, math.pi/2, 0), 24)
    unit_base = face+.04
    for k in range(6):
        a = math.pi/2+k*math.tau/6; y, z = ring*math.cos(a), ring*math.sin(a)
        cyl('UnitSocket', .052, .02, (unit_base-.002, y, z), ALLOY, hub, (0, math.pi/2, 0), 24)
        beam('SocketSpoke', (face+.04, .04*math.cos(a), .04*math.sin(a)), (face+.04, (ring-.05)*math.cos(a), (ring-.05)*math.sin(a)), .016, DARK, hub)
        if k:
            energy_unit('HubUnit', hub, (unit_base, y, z), (0, math.pi/2, 0))
    staged = empty('AvailableUnit_'+fixture['team'], local)
    cyl('StagingCup', .05, .02, (unit_base-.002, 0, hub_z), ALLOY, staged, (0, math.pi/2, 0), 24)
    energy_unit('ReadyUnit', staged, (unit_base, 0, hub_z), (0, math.pi/2, 0))
    return local


def s27_workbench(fixture, root, color):
    """Workbench where the heavy robot's modular 42 mm launcher is fitted (figure 4-23):
    750 x 450 bench, top 400 mm, module cradle on top, docking face toward the field (+X)."""
    local = s27_local(root, 'Workbench', fixture['point'], fixture['yaw'])
    L, W = fixture['size_m']; top = fixture['top_m']
    box('WorkbenchBody', (L, W, top-.04), (0, 0, (top-.04)/2), KERB, local, .01)
    box('WorkbenchToeKick', (L-.04, W-.04, .04), (0, 0, .02), DARK, local, .004)
    box('WorkbenchTop', (L+.02, W+.02, .04), (0, 0, top-.02), DARK, local, .006)
    for y in (-.09, .09):
        box('ModuleCradleRail', (.36, .03, .022), (.02, y, top+.011), STEEL, local, .003)
    for x in (-.14, .18):
        for y in (-.12, .12):
            cyl('CradleGuidePin', .008, .03, (x, y, top+.015), ALLOY, local, vertices=12)
    box('ModuleChargeConnector', (.05, .07, .03), (-.22, 0, top+.015), DARK, local, .004)
    box('CradleStatusLamp', (.004, .2, .012), (L/2+.011, 0, top-.02), color, local, .001)
    # Docking face: bumper, connector and display.
    box('DockBumper', (.03, W-.06, .06), (L/2+.015, 0, .14), RUBBER, local, .008)
    box('DockFacePlate', (.006, W-.08, .2), (L/2+.003, 0, .26), DARK, local, .002)
    box('WorkbenchScreen', (.004, .16, .08), (L/2+.007, -.08, .27), GLASS, local, .001)
    box('DockConnector', (.02, .08, .05), (L/2+.01, .1, .27), STEEL, local, .004)
    for side in (-1, 1):
        c4_strip('WorkbenchLamp', [(side*(W/2-.01), .05), (side*(W/2-.01), top-.06)], .02, .006, color, local, offset=L/2)
    return local


def s27_hangar_platform(fixture, gantry, root, color):
    """Hangar platform (figure 4-30): 400 x 400 deck with the 320 pad, its top `top_m` above
    the field datum, cantilevered from the rune-gantry post on its outboard side. Local +X
    points away from the post (the hangar's forward direction)."""
    x, y = fixture['point']; size = fixture['size_m'][0]; pad = gantry['hangar_pad_m']
    top = floor_z(y)+fixture['top_m']
    local = s27_local(root, 'HangarPlatform', fixture['point'], fixture['yaw'], top)
    post = gantry['hangar_platform_center_m']-gantry['post_center_m']; ps = gantry['post_size_m']
    box('PlatformSlab', (size, size, .037), (0, 0, -.0215), KERB, local, .004)
    box('HangarPad', (pad, pad, .003), (0, 0, -.0015), DARK, local, 0)
    for s in (-1, 1):
        box('PadOutline', (pad, .012, .001), (0, s*(pad/2-.006), .0005), color, local, 0)
        box('PadOutline', (.012, pad, .001), (s*(pad/2-.006), 0, .0005), color, local, 0)
        box('PlatformEdgeLamp', (size-.06, .004, .012), (0, s*(size/2+.002), -.02), color, local, .001)
        box('PlatformKerb', (size-.02, .02, .02), (0, s*(size/2-.01), .007), STEEL, local, .004)
    box('PlatformKerb', (.02, size-.06, .02), (size/2-.01, 0, .007), STEEL, local, .004)
    box('PlatformEdgeLamp', (.004, size-.06, .012), (size/2+.002, 0, -.02), color, local, .001)
    s27_flat_text('H', .16, (0, 0, .0004), math.pi/2, WHITE_PAINT, local, .0004)
    # Cantilever arms from the post's outer face and diagonal braces down the post.
    face = -post+ps/2
    for s in (-1, 1):
        box('PlatformArm', (size/2-face+.0, .04, .06), ((face+size/2)/2, s*.13, -.07), DARK, local, .006)
        beam('PlatformBrace', (face, s*.13, -.48), (size/2-.03, s*.13, -.09), .035, DARK, local)
    for z in (-.07, -.48):
        box('PostClamp', (ps+.03, ps+.03, .05), (-post, 0, z), STEEL, local, .006)
    # Infrared link to the hangar on the post (S109) and the platform's status beacon.
    box('IrLinkModule', (.02, .06, .04), (face+.01, 0, .12), DARK, local, .004)
    box('IrLinkWindow', (.003, .04, .02), (face+.021, 0, .12), GLASS, local, .001)
    box('PlatformStatusLamp', (.02, .02, .02), (face+.01, 0, .2), color, local, .003)
    return local


def s27_field_paint(arena, root):
    geometry = arena['field_geometry']; colour = {'red': RED_PAINT, 'blue': BLUE_PAINT}
    painted = []
    for p in geometry['paint']:
        s27_paint(arena, p['points'], colour[p['team']], root, .04, p.get('closed', True))
        painted.append([[round(a, 3), round(b, 3)] for a, b in p['points']])
    for z in arena['zones']:
        material = colour.get(z.get('owner'), WHITE_PAINT)
        if z.get('polygon'):
            if [[round(a, 3), round(b, 3)] for a, b in z['polygon']] in painted:
                continue
            s27_paint(arena, z['polygon'], material, root, .035, True)
        elif z['kind'] in ('resource', 'workbench', 'assembly'):
            ring = [[z['x']+z['radius']*math.cos(a), z['y']+z['radius']*math.sin(a)] for a in [k*math.tau/36 for k in range(36)]]
            s27_paint(arena, ring, material, root, .03, True)
    # Crossing-point glyphs, as on the 2026 field: step for road/highland, -v- for tunnels.
    glyphs = {'road': [[[-.08, -.035], [0, -.035], [0, .035], [.08, .035]]], 'highland': [[[-.08, -.035], [0, -.035], [0, .035], [.08, .035]]],
              'tunnel': [[[-.13, 0], [-.06, 0]], [[-.04, .04], [0, -.03], [.04, .04]], [[.06, 0], [.13, 0]]]}
    for z in arena['zones']:
        if z['kind'] not in glyphs:
            continue
        flip = -1 if (z.get('group') or z['id']).startswith('blue') else 1
        for stroke in glyphs[z['kind']]:
            c4_paint(arena, [[z['x']+flip*u, z['y']-flip*v] for u, v in stroke], WHITE_PAINT, root, .028)
    for team, sign in (('red', 1), ('blue', -1)):
        def p(x, y):
            return (x, y) if sign > 0 else (28-x, 15-y)
        c4_text(arena, 'R', *p(4.32, 3.70), .7, WHITE_PAINT, root)
        c4_text(arena, 'ROBOMASTER', *p(5.6, .55), .36, WHITE_PAINT, root, 0 if sign > 0 else math.pi)
        c4_text(arena, '2027', *p(8.9, .55), .36, colour[team], root, 0 if sign > 0 else math.pi)


def s27_flatten_map(root, keep=('AvailableUnit_',)):
    """Join static sub-assemblies into the arena root so the GLB batches by material."""
    bpy.context.view_layer.update()
    for obj in list(bpy.context.scene.objects):
        if obj.type != 'MESH' or obj.parent in (None, root):
            continue
        node = obj.parent; held = False
        while node and node != root:
            held = held or node.name.startswith(keep); node = node.parent
        if not held:
            matrix = obj.matrix_world.copy(); obj.parent = root; obj.matrix_world = matrix
    for obj in list(bpy.context.scene.objects):
        if obj.type == 'EMPTY' and obj != root and not obj.name.startswith(keep) and not any(c for c in obj.children_recursive if c.type == 'MESH'):
            bpy.data.objects.remove(obj, do_unlink=True)
    # Bake rotations into the vertices so the joined per-material meshes stay axis-aligned.
    loose = [o for o in root.children if o.type == 'MESH']
    bpy.ops.object.select_all(action='DESELECT')
    for obj in loose:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = loose[0]
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)


def chapter4_2027_arena(arena):
    """RMUC 2027 field from maps.rmuc2027: terrain prisms at the engine heights (sides drop to
    the terrain they stand on), walls/kerbs/tunnels/parapets from the obstacles, the 2027
    fixtures and team-coloured field paint (edges, start zones and buff-card outlines)."""
    if 'ALLOY' not in globals():
        spec_materials()  # fixtures share the robot hardware materials
    reset(); root = empty('ArenaChapter4'); root['season'] = '2027'; root['layout_revision'] = arena['layout_revision']
    box('Substructure', (28.25, 15.25, .2), (0, 0, -.14), DARK, root, .02)
    for a, b in [(0, 7.5), (7.5, 15)]:
        pts = [[0, a], [28, a], [28, b], [0, b]]; c4_prism('TiltedField', pts, [floor_z(p[1]) for p in pts], FIELD, root, -.08)
    for t in arena['terrain']:
        pts = t['polygon']; material = KERB if 'pedestal' in t['id'] else ROAD
        if t['kind'] == 'bumps':
            # Smooth 70 mm humps (figures 4-36/4-37), sixteen facets per 240 mm pitch.
            for i in range(round(t['w']/t['bump_pitch'])*16):
                x = t['x']+i*t['bump_pitch']/16; xn = x+t['bump_pitch']/16
                p = [[x, t['y']], [xn, t['y']], [xn, t['y']+t['h']], [x, t['y']+t['h']]]
                c4_prism('RoadRidge', p, [floor_z(y)+c4_height(t, xx, y) for xx, y in p], ROAD, root, t['elevation'])
        elif t.get('edge_ramp_m', 0):
            # Fortress (20 deg) and assembly plinth (12 deg on the deck): flat top, sloped skirt.
            inner = s27_inset(pts, t['edge_ramp_m'])
            s27_prism(t['id']+'Top', inner, [t['elevation']]*len(inner), KERB if t['id'] == 'assembly_plinth' else material, root)
            for i in range(len(pts)):
                p = [pts[i], pts[(i+1) % len(pts)], inner[(i+1) % len(pts)], inner[i]]
                base = t.get('base_elevation', 0)
                s27_prism(t['id']+'Slope', p, [base, base, t['elevation'], t['elevation']], material, root)
        elif t['kind'] == 'ramp' and t['id'].endswith('_trapezoid_23'):
            c4_stepped_ramp(arena, t, ROAD, SIDE, root)
        else:
            elevations = [c4_height(t, x, y) for x, y in pts]
            s27_prism(t['id'], pts, elevations, material, root)
            outline, levels = s27_ridge(pts, elevations)
            c4_sides(t['id']+'Side', outline, [floor_z(p[1])+e for p, e in zip(outline, levels)], s27_support(arena, t), SIDE if material is ROAD else material, root)
    walls = {w['id']: w for w in arena['obstacles']}
    for w in arena['obstacles']:
        if w['id'].startswith('rune_') or w['id'].endswith(S27_FIXTURE_WALLS):
            continue
        s27_wall(w, root)
    c4_fence(root)
    s27_field_paint(arena, root)
    fixtures = arena['field_geometry']['fixtures']
    gantry = next(f for f in fixtures if f['kind'] == 'rune_gantry')
    for fixture in fixtures:
        kind = fixture['kind']; team = fixture['team']
        color = RED_PAINT if team == 'red' else BLUE_PAINT
        if kind == 'rune_gantry':
            rune_gantry(arena, fixture, root)
        elif kind == 'dart_station':
            s27_dart_station(fixture, walls[team+'_dart_station'], root, color)
        elif kind == 'resource':
            s27_resource_hub(fixture, walls[team+'_resource_frame'], root, color)
        elif kind == 'workbench':
            s27_workbench(fixture, root, color)
        elif kind == 'hangar_platform':
            s27_hangar_platform(fixture, gantry, root, color)
    s27_flatten_map(root)
    export(Path(arena['asset']).stem)


# ---------------------------------------------------------------------------- robots

S27_KEEP = ('Wheel_', 'SteerModule_', 'FoldMast_', 'ArmorNumber', 'Aux_', 'Turret', 'GunPitch', 'GunElevator', 'Arm', 'Gripper',
            'CarriedUnit', 'Leg', 'Rotor_', 'Magazine', 'LauncherModule', 'StatusBeacon', 'DroneBay', 'Hangar')


def s27_flatten(body):
    """flatten_static with the 2027 animated/toggled nodes (LauncherModule, StatusBeacon) kept."""
    for obj in list(bpy.context.scene.objects):
        if obj.type != 'MESH':
            continue
        parent = obj.parent
        if parent and parent != body and not parent.name.startswith(S27_KEEP) and parent.name not in ('Robot', 'Chassis'):
            target = parent
            while target and target != body and not target.name.startswith(S27_KEEP):
                target = target.parent
            matrix = obj.matrix_world.copy(); obj.parent = target or body; obj.matrix_world = matrix


def s27_meshes(exclude=()):
    bpy.context.view_layer.update()
    out = []
    for obj in bpy.context.scene.objects:
        if obj.type != 'MESH':
            continue
        node = obj.parent; skipped = obj.name in exclude
        while node and not skipped:
            skipped = node.name in exclude; node = node.parent
        if not skipped:
            out.append(obj)
    return out


def s27_bounds(objects):
    points = [obj.matrix_world@Vector(v) for obj in objects for v in obj.bound_box]
    return [min(p[i] for p in points) for i in range(3)], [max(p[i] for p in points) for i in range(3)]


def s27_size(exclude=()):
    lo, hi = s27_bounds(s27_meshes(exclude))
    return [b-a for a, b in zip(lo, hi)]


def verify_2027(slot, d):
    """Sampled-pose envelope check against the 2027 construction limits. The heavy's stowed
    size excludes `LauncherModule` (rules: stowed_excludes_launcher_module). Invalid
    geometry is saved in the envelope JSON and then fails the asset build."""
    role = d['role']; env = S27_ENV[role]; issues = []
    stowed_limit = env['hangar']['stowed_m'] if role == 'aerial' else env['stowed_m']
    extended_limit = env['hangar']['extended_m'] if role == 'aerial' else env['extended_m']
    exclude = ('LauncherModule',) if role == 'heavy' else ()
    legged = d.get('chassis_type') == 'wheel_legged'
    if legged:
        pose_legs(d, d['leg_min_m'])
    stowed = s27_size(exclude)
    if not all(a <= b+.002 for a, b in zip(stowed, stowed_limit)):
        issues.append(f'stowed mesh {[round(v, 3) for v in stowed]} exceeds {stowed_limit}')
    turret = bpy.data.objects.get('Turret'); pitch = bpy.data.objects.get('GunPitch')
    maximum = s27_size()
    poses = [(d['leg_min_m'], 0), (d['leg_max_m'], 0)] if legged else [None]
    if legged and d.get('leg_type') == 'serial':
        poses += [(length, k*math.pi/4) for length in (d['leg_min_m'], d['leg_nominal_m']) for k in range(1, 8)]
    low, high = d.get('pitch_limits_rad', [0, 0])
    for legs in poses:
        if legs:
            pose_legs(d, *legs)
        if turret and pitch:
            for yaw in range(0, 360, 15):
                for elevation in (low, 0, high):
                    turret.rotation_euler[2] = math.radians(yaw); pitch.rotation_euler[1] = -elevation
                    maximum = [max(a, b) for a, b in zip(maximum, s27_size())]
            turret.rotation_euler[2] = 0; pitch.rotation_euler[1] = 0
    if legged:
        pose_legs(d, d['leg_nominal_m'])
    if d.get('arm'):
        arm = d['arm']; lim = arm['limits']
        for slew in (lim[0][0], -math.pi/2, 0, math.pi/2, lim[0][1]):
            for lift in lim[1]:
                for pitch_q in (lim[4][0], 0, lim[4][1]):
                    pose_arm(arm, [slew, lift, lim[2][1], 0, pitch_q, 0, 1])
                    if d.get('arm_count') == 2:
                        pose_arm(d['arm2'], [-slew, lift, d['arm2']['limits'][2][1], 0, pitch_q, 0, 1], 'Aux_')
                    maximum = [max(a, b) for a, b in zip(maximum, s27_size())]
        pose_arm(arm, arm['stowed'])
        if d.get('arm_count') == 2:
            pose_arm(d['arm2'], d['arm2']['stowed'], 'Aux_')
    measured = [max(0, value-.002) for value in maximum]  # mesh/export tolerance
    extended_ok = (_s27_construction.extended_envelope_2027(d, env, measured) if role == 'heavy'
                   else all(a <= b+.002 for a, b in zip(maximum, extended_limit)))
    if not extended_ok:
        issues.append(f'articulated mesh {[round(v, 3) for v in maximum]} exceeds {extended_limit}')
    envelope = {'slot': slot, 'season': '2027', 'stowed_mesh_m': stowed, 'articulated_mesh_max_m': maximum,
                'stowed_limit_m': stowed_limit, 'extended_limit_m': extended_limit,
                'bare_mass_kg': d.get('bare_mass_kg'), 'referee_mass_kg': d.get('referee_mass_kg'), 'mast_excluded': False}
    if role == 'heavy':
        module = bpy.data.objects['LauncherModule']
        lo, hi = s27_bounds([o for o in module.children_recursive if o.type == 'MESH'])
        envelope.update(launcher_module_excluded=True, launcher_module_mesh_m=[b-a for a, b in zip(lo, hi)],
                        launcher_module_limit_m=env['launcher_module']['stowed_m'])
    if d.get('transform_allowed'):
        pose_transform(d, 1)
        folded = [0, 0, 0]; top = 0.0
        for yaw in range(0, 360, 15):
            for elevation in (-8, 0, 8):
                turret.rotation_euler[2] = math.radians(yaw); pitch.rotation_euler[1] = -math.radians(elevation)
                folded = [max(a, b) for a, b in zip(folded, s27_size())]
                top = max(top, s27_bounds(s27_meshes())[1][2])
        if top > d['folded_height_m']+.002:
            issues.append(f'folded top {top:.3f} exceeds {d["folded_height_m"]}')
        envelope.update(folded_mesh_max_m=folded, folded_top_m=top, folded_height_limit_m=d['folded_height_m'])
        pose_transform(d, 0); turret.rotation_euler[2] = 0; pitch.rotation_euler[1] = 0
    envelope['issues'] = issues
    for issue in issues:
        print('S27 ENVELOPE', slot, issue, flush=True)
    S27_REPORT[slot] = envelope
    (OUT/f'robot-{slot}-envelope.json').write_text(json.dumps(envelope, indent=2))
    if issues:
        raise ValueError(f'2027 model {slot} failed construction envelope inspection: {issues}')


def s27_with_base_builder(build, decorate):
    """Run a 2026 base builder unchanged, adding the 2027 parts just before its envelope
    check; the check, flattening and export then use the 2027 versions."""
    saved = globals()['verify_robot_envelope'], globals()['flatten_static']

    def verify(slot, d):
        decorate(d)
        verify_2027(d['slot'], d)
    globals()['verify_robot_envelope'] = verify; globals()['flatten_static'] = s27_flatten
    try:
        build()
    finally:
        globals()['verify_robot_envelope'], globals()['flatten_static'] = saved


def s27_world(name):
    obj = bpy.data.objects[name]; bpy.context.view_layer.update()
    return obj.matrix_world.translation.copy()


# ---- heavy robots

def s27_heavy_arm(d, body, prefix='', key='arm', mast=.24):
    """engineer_arm with a shorter mast, a long carriage shoe for the 0.64 m lift and the
    boom overhang behind the carriage cut to boom_tail_m, so the tail stays clear of the
    central gimbal; node names and joint frames are identical to the engineer's."""
    before = set(bpy.data.objects)
    arm = d[key]; rest = arm['shoulder_rest_z_m']-arm['base_m'][2]; tail = arm['boom_tail_m']
    slew = empty('ArmSlew', body); slew.location = tuple(arm['base_m'])
    # The bearing's outer race is fixed to the mount plate; everything above it slews.
    cyl('SlewBearing', .08, .02, (arm['base_m'][0], arm['base_m'][1], arm['base_m'][2]-.006), ALLOY, body, vertices=28)
    # Slew drive fixed inboard of the bearing; the lift motor lies along the mast's inboard
    # face when stowed, so the folded arm keeps inside the 600 mm box.
    inboard = -math.copysign(1, arm['base_m'][1])
    box('SlewDriveMotor', (.05, .05, .04), (arm['base_m'][0], arm['base_m'][1]+inboard*.09, arm['base_m'][2]), MOTOR, body, .004)
    for y in (-.045, .045):
        box('MastOuterRail', (.03, .022, mast), (0, y, mast/2), ROBOT_ALUMINUM, slew, .002)
    box('MastHead', (.05, .12, .02), (0, 0, mast+.01), ROBOT_ALUMINUM, slew, .003)
    box('MastFoot', (.08, .14, .02), (0, 0, .01), ROBOT_ALUMINUM, slew, .003)
    rod('LiftBelt', (-.022, 0, .02), (-.022, 0, mast), .004, ROBOT_MATTE, slew, 6)
    m3508('LiftMotor', (-.04, 0, .035), (0, inboard, 0), slew, .75)
    stage = empty('ArmMastStage', slew)
    # Inner stage tops out 60 mm below the mast head, under the barrel when stowed (also
    # the dual arm's upper fold); the longer carriage shoe still grips it at full lift.
    inner = mast+.045
    for y in (-.03, .03):
        box('MastInnerRail', (.022, .016, inner), (0, y, mast-.06-inner/2), ALLOY, stage, .002)
    lift = empty('ArmLift', slew); lift.location = (0, 0, rest)
    box('LiftCarriage', (.07, .13, .06), (0, 0, 0), ROBOT_ALUMINUM, lift, .004)
    box('LiftCarriageShoe', (.012, .1, .185), (-.026, 0, -.1225), ROBOT_ALUMINUM, lift, .002)
    box('BoomOuter', (.2+tail, .05, .05), ((.2-tail)/2, 0, 0), ROBOT_PANEL, lift, .004)
    box('BoomTail', (.06, .07, .06), (-tail+.03, 0, 0), MOTOR, lift, .004)
    m3508('ReachMotor', (-tail+.005, 0, .03), (1, 0, 0), lift, .6)
    rod('BoomCableChain', (-tail+.04, 0, .035), (.16, 0, .035), .008, ROBOT_MATTE, lift, 8)
    box('BoomStripe', (.2, .052, .008), (.08, 0, .021), ORANGE, lift, .002)
    reach = empty('ArmReach', lift); reach.location = (arm['stowed'][2], 0, 0)
    inner = min(.30, arm['limits'][2][0]+tail)
    box('BoomInner', (inner, .036, .036), (-inner/2, 0, 0), ALLOY, reach, .003)
    box('WristBlock', (.05, .05, .05), (-.015, 0, 0), ROBOT_MATTE, reach, .004)
    wyaw = empty('ArmWristYaw', reach)
    cyl('WristYawMotor', .024, .024, (0, 0, .032), MOTOR, wyaw, vertices=18)
    wpitch = empty('ArmWristPitch', wyaw)
    for y in (-.032, .032):
        box('WristYoke', (.05, .008, .05), (.015, y, 0), ROBOT_ALUMINUM, wpitch, .002)
    cyl('WristPitchMotor', .022, .018, (0, -.047, 0), MOTOR, wpitch, (math.pi/2, 0, 0), 18)
    roll = empty('ArmWristRoll', wpitch)
    cyl('WristRollMotor', .021, .03, (.035, 0, 0), MOTOR_CAP, roll, (0, math.pi/2, 0), 18)
    box('GripperPalm', (.03, .075, .04), (.062, 0, 0), ROBOT_MATTE, roll, .004)
    cyl('SuctionCup', .017, .03, (.09, 0, 0), ROBOT_MATTE, roll, (0, math.pi/2, 0), 16)
    cyl('SuctionLip', .02, .006, (.108, 0, 0), TYRE, roll, (0, math.pi/2, 0), 16)
    for k, side in enumerate((-1, 1)):
        jaw = empty(f'GripperJaw_{k}', roll); jaw.location = (0, side*.018, 0)
        box('JawGuide', (.024, .01, .012), (.066, 0, 0), ALLOY, jaw, .002)
        c4_local_prism('JawFinger', [(.075, -.018), (.15, -.012), (.15, .012), (.075, .018)], .008, ROBOT_ALUMINUM, jaw, 'y', -.004)
        box('JawPad', (.05, .003, .022), (.122, -side*.006, 0), TYRE, jaw, .001)
    # Camera on the mast's inboard face when stowed (folded across the front).
    vtm_camera('ArmCamera', (-.01, -math.copysign(.085, arm['base_m'][1]), .17), slew, 0)
    if prefix:
        for obj in set(bpy.data.objects)-before:
            obj.name = prefix+(obj.name.rsplit('.', 1)[0] if obj.name.rsplit('.', 1)[-1].isdigit() else obj.name)
    pose_arm(arm, arm['stowed'], prefix)
    return slew


def s27_launcher_module(d, turret, base_z):
    """Modular 42 mm launcher (rules: fitted at the workbench). Everything here lives under
    `LauncherModule` so the viewer can hide it until the module is fitted: cradle, trunnion
    cheeks and pitch drive (static on the yaw frame) and `GunPitch` with the launcher head,
    friction wheels, barrel, 42 mm speed module, magazine and camera. Its stowed box is
    launcher_module_stowed_m (x from the cradle's rear to the speed module's face)."""
    size = d['launcher_module_stowed_m']; muzzle = d['muzzle_z_m']; reach = d['muzzle_reach_m']
    module = empty('LauncherModule', turret)
    module['stowed_m'] = json.dumps(size); module['mass_kg'] = d.get('launcher_module_kg', 0)
    back = reach-size[0]+.002
    box('ModuleCradlePlate', (.075-back, .26, .012), ((back+.075)/2, 0, base_z+.006), ROBOT_ALUMINUM, module, .003)
    box('ModuleLatchLever', (.03, .09, .014), (back+.016, 0, base_z+.019), ORANGE, module, .003)
    for side in (-1, 1):
        y0 = .122 if side > 0 else -.134
        cheek = c4_local_prism('ModuleCheek', [(-.07, 0), (.07, 0), (.045, muzzle-base_z+.045), (-.045, muzzle-base_z+.045)], .012, CARBON, module, 'y', y0)
        cheek.location = (0, 0, base_z+.012)
        s27_cyl('PitchBearingCap', .022, .008, (0, side*.138, muzzle), ALLOY, module, (math.pi/2, 0, 0), 20, .001)
        box('CheekLamp', (.06, .002, .008), (0, side*.1345, base_z+.045), GLOW, module, 0)
    s27_cyl('ModulePitchDrive', .028, .012, (0, -.146, muzzle), MOTOR, module, (math.pi/2, 0, 0), 24, .002)
    s27_cyl('ModulePitchDriveCap', .016, .004, (0, -.1535, muzzle), MOTOR_CAP, module, (math.pi/2, 0, 0), 20)
    pitch = empty('GunPitch', module); pitch.location = (0, 0, muzzle)
    # Launcher head: open housing round the friction wheels (pitch axis at its lower third).
    lo = base_z+.012-muzzle+.001; hx0 = back; hx1 = .125
    for side in (-1, 1):
        box('HeadSidePlate', (hx1-hx0, .006, .065-lo), ((hx0+hx1)/2, side*.112, (lo+.065)/2), ROBOT_PANEL, pitch, .002)
        box('HeadStatusLamp', (.12, .003, .008), (.02, side*.1155, .04), GLOW, pitch, .001)
    box('HeadTopPlate', (hx1-hx0, .23, .006), ((hx0+hx1)/2, 0, .068), CARBON, pitch, .002)
    box('HeadBottomPlate', (hx1-hx0, .23, .006), ((hx0+hx1)/2, 0, lo+.003), CARBON, pitch, .002)
    box('BarrelMountBlock', (.03, .07, .07), (.115, 0, 0), ALLOY, pitch, .004)
    bore = .0235; wheel = .038
    for side in (-1, 1):
        y = side*(bore+wheel+.002)
        cyl('FrictionWheel', wheel, .026, (.03, y, 0), TYRE, pitch, vertices=28)
        cyl('FrictionHub', wheel*.55, .028, (.03, y, 0), ALLOY, pitch, vertices=16)
        m3508('FrictionMotor', (.03, y, -.016), (0, 0, -1), pitch, .62)
    cyl('FeederDial', .04, .02, (-.045, 0, .03), ROBOT_MATTE, pitch, vertices=24)
    rod('BarrelTube', (.13, 0, 0), (reach-.055, 0, 0), bore+.004, ALLOY, pitch, 24)
    speed_module('MuzzleSpeedModule', reach-.0015, 42, pitch)
    s27_cyl('MuzzleBore', .0215, .0015, (reach-.00075, 0, 0), ROBOT_MATTE, pitch, (0, math.pi/2, 0), 24)
    # 42 mm magazine on the head (pitches with it), lid at the module's top face.
    top = base_z+size[2]-muzzle
    box('ModuleMagazine', (.15, .19, top-.071-.006), (back+.075, 0, (.071+top-.006)/2), ROBOT_PANEL, pitch, .006)
    box('ModuleMagazineLid', (.152, .192, .006), (back+.075, 0, top-.003), ROBOT_MATTE, pitch, .002)
    box('MagazineWindow', (.08, .002, .03), (back+.075, .0955, .12), GLASS, pitch, 0)
    for side in (-1, 1):
        s27_side_text('42', .045, (back+.075, side*.0962, .145), side, STATUS_WHITE, pitch)
    box('VisionCamera', (.034, .03, .03), (.1, .075, .086), ROBOT_MATTE, pitch, .003)
    cyl('VisionLens', .0105, .02, (.125, .075, .086), ROBOT_MATTE, pitch, (0, math.pi/2, 0), 16)
    s27_cyl('VisionGlass', .008, .002, (.136, .075, .086), LENS, pitch, (0, math.pi/2, 0), 16)
    return module, pitch


def spec_heavy_2027(d):
    """Heavy robot: the engineer chassis and arm(s) of its base model with the lift mast(s)
    at the front corners (arm.base_m), a gimbal dock on a central column (Turret, coaxial
    with the engine's muzzle pivot) and the modular 42 mm launcher under LauncherModule
    (hidden by the viewer until fitted)."""
    reset(); root = empty('Robot'); body = empty('Chassis', root)
    root['season'] = '2027'; root['launcher'] = d['launcher']
    deck = mecanum_chassis(2, d, body)
    s27_heavy_arm(d, body)
    if d.get('arm_count') == 2:
        s27_heavy_arm(d, body, 'Aux_', 'arm2')
    for key in ('arm', 'arm2'):
        if d.get(key):
            # Carbon plate under the top deck carrying the corner slew bearing past its edge.
            x, y = d[key]['base_m'][:2]
            box('CornerMountPlate', (.16, .16, .005), (x, y, deck-.006), CARBON, body, .002)
    dock = deck+.28
    # The dock stands on its own column at the chassis centre, clear of the arm(s).
    box('GimbalColumn', (.05, .05, dock-deck), (0, 0, (dock+deck)/2), ROBOT_ALUMINUM, body, .003)
    box('GimbalColumnFoot', (.11, .11, .012), (0, 0, deck+.006), ROBOT_ALUMINUM, body, .002)
    for k in range(4):
        a = k*math.pi/2
        box('GimbalColumnGusset', (.04, .006, .06), (.045*math.cos(a), .045*math.sin(a), deck+.042), ROBOT_ALUMINUM, body, .001).rotation_euler[2] = a
    box('GimbalColumnHead', (.12, .12, .012), (0, 0, dock-.006), ROBOT_ALUMINUM, body, .002)
    # Yaw drive hangs static under the column head and turns the ring by belt, so nothing
    # that yaws reaches past 0.205 m from the axis (the magazine tipped back at full
    # elevation) except the launcher's barrel.
    gm6020('YawMotor', (-.07, 0, dock-.03), (0, 0, -1), body)
    # Bare gimbal (stays visible without the module): hollow yaw ring, dock frame, guide
    # pins, module connector and latches.
    turret = empty('Turret', body)
    s27_ring_z('YawRing', .045, .085, .016, dock+.002, ALLOY, turret)
    s27_ring_z('YawRingCover', .045, .09, .004, dock+.018, CARBON, turret)
    plate = dock+.022
    for x0, x1, y0, y1 in ((.05, .105, -.105, .105), (-.105, -.05, -.105, .105), (-.05, .05, .05, .105), (-.05, .05, -.105, -.05)):
        box('DockFrame', (x1-x0, y1-y0, .01), ((x0+x1)/2, (y0+y1)/2, plate+.005), CARBON, turret, .002)
    for x in (-.09, .09):
        for y in (-.085, .085):
            s27_cyl('DockGuidePin', .007, .02, (x, y, plate+.02), ALLOY, turret, vertices=12, bevel=.001)
    box('ModuleConnector', (.03, .06, .016), (.07, 0, plate+.018), DARK, turret, .003)
    for side in (-1, 1):
        box('DockLatch', (.04, .012, .02), (0, side*.099, plate+.01), ORANGE, turret, .003)
    box('DockStatusLamp', (.004, .16, .006), (-.107, 0, plate+.007), GLOW, turret, .001)
    s27_launcher_module(d, turret, plate+.01)
    # Energy-unit cradles behind the gimbal column (as the engineer's) and the referee light bar.
    for i, y in enumerate((-.07, .07)):
        box('UnitCradle', (.10, .10, .012), (-.17, y, deck+.006), ROBOT_ALUMINUM, body, .003)
        for k in range(3):
            a = k*math.tau/3; rod('UnitCradlePost', (-.17+.05*math.cos(a), y+.05*math.sin(a), deck), (-.17+.05*math.cos(a), y+.05*math.sin(a), deck+.06), .004, ROBOT_ALUMINUM, body, 6)
        unit = empty('CarriedUnit_'+str(i), body); unit.location = (-.17, y, deck+.012)
        energy_unit('CarriedEnergyUnit', unit)
    light_bar('LightBar', (.15, 0, deck), 0, body, .035)
    # 2027 livery: orange deck stripes and the season badge.
    hl, hw = d['chassis_size_m'][0]/2, d['chassis_size_m'][1]/2
    for s in (-1, 1):
        box('LiveryStripe', (hl*1.2, .012, .002), (-hl*.04, s*(hw*.55-.012), deck+.001), ORANGE, body, 0)
    s27_badge(body, (hl*.45, -hw*.35, deck+.002), -math.pi/2, 'H27')
    verify_2027(d['slot'], d)
    s27_flatten(body)
    export(Path(d['asset']).stem)


# ---- infantry and sentries

def s27_base_design(d):
    """The 2026 design this one was derived from, and the design dict its builder expects."""
    base = CONFIG['robot_designs'][str(d['base_model'])]
    return base, dict(d, base_model=base.get('base_model', d['base_model']))


def s27_sentry_parts(d):
    """Sentry identity: a taller hopper on the magazine (700-round capacity) and a status
    beacon on the turret top."""
    mag = bpy.data.objects['Magazine']; turret = bpy.data.objects['Turret']
    chamber = .12
    lid = chamber*.3+.008
    box('MagazineHopper', (chamber*1.12, chamber*1.22, .044), (0, 0, lid+.022), ROBOT_PANEL, mag, .006)
    box('HopperLid', (chamber*1.14, chamber*1.24, .006), (0, 0, lid+.047), ROBOT_MATTE, mag, .002)
    box('HopperStripe', (chamber*1.13, .004, .012), (0, chamber*.61+.002, lid+.03), ORANGE, mag, 0)
    box('HopperStripe', (chamber*1.13, .004, .012), (0, -chamber*.61-.002, lid+.03), ORANGE, mag, 0)
    bpy.context.view_layer.update()
    top = (mag.matrix_world@Vector((0, 0, lid+.05))); local = turret.matrix_world.inverted()@top
    beacon = empty('StatusBeacon', turret); beacon.location = (local.x-.035, local.y, local.z)
    s27_cyl('BeaconBase', .02, .008, (0, 0, .004), ROBOT_MATTE, beacon, vertices=20, bevel=.001)
    s27_cyl('BeaconLens', .016, .018, (0, 0, .017), GLOW, beacon, vertices=20, bevel=.002)
    s27_cyl('BeaconCap', .012, .004, (0, 0, .028), STATUS_WHITE, beacon, vertices=20, bevel=.001)


def s27_magazine_livery(d):
    """2027 livery on the gimbal: orange band round the magazine with the season number."""
    mag = bpy.data.objects['Magazine']; chamber = .12
    box('MagazineBand', (chamber*.9+.004, chamber+.004, .016), (0, 0, -chamber*.12), ORANGE, mag, .002)
    for side in (-1, 1):
        s27_side_text('27', .028, (0, side*(chamber/2+.0025), chamber*.1), side, STATUS_WHITE, mag)


def s27_decorate_ground(d):
    """2027 livery on the mecanum/omni well chassis (2732, 2771)."""
    body = bpy.data.objects['Chassis']; hl, hw = d['chassis_size_m'][0]/2, d['chassis_size_m'][1]/2
    lift = d.get('ground_clearance_m', .035)+d['suspension_static_compression_m']-.053
    deck = .065+lift+d['chassis_size_m'][2]
    for s in (-1, 1):
        box('LiveryStripe', (hl*1.1, .01, .002), (-hl*.05, s*(hw*.38), deck+.001), ORANGE, body, 0)
        box('LiveryGlow', (hl*.7, .006, .003), (-hl*.05, s*(hw*.5), deck+.0015), GLOW, body, 0)
    s27_badge(body, (-hl*.62, 0, deck+.002), -math.pi/2, 'S27' if d['role'] == 'sentry' else 'I27', .06, .04)
    s27_magazine_livery(d)
    if d['role'] == 'sentry':
        s27_sentry_parts(d)


def s27_decorate_legged(d):
    """2027 livery on the wheel-legged body (2731, 2772)."""
    body = bpy.data.objects['Chassis']; length, width, height = d['chassis_size_m']; hip = d['hip_height_m']
    hl, hw = length/2, width/2; top = hip+height/2
    for s in (-1, 1):
        box('LiveryStripe', (length*.7, .01, .002), (0, s*hw*.78, top+.001), ORANGE, body, 0)
        box('LiveryGlow', (length*.55, .004, .012), (0, s*(hw+.001), hip+.025), GLOW, body, .001)
    s27_badge(body, (-hl*.62, 0, top+.002), -math.pi/2, 'S27' if d['role'] == 'sentry' else 'I27', .06, .04)
    s27_magazine_livery(d)
    if d['role'] == 'sentry':
        s27_sentry_parts(d)


def spec_derived_2027(d):
    base, design = s27_base_design(d)
    if d.get('chassis_type') == 'wheel_legged':
        s27_with_base_builder(lambda: spec_wheel_legged(design), s27_decorate_legged)
    else:
        s27_with_base_builder(lambda: spec_ground_robot(d['slot'], design), s27_decorate_ground)
    bpy.data.objects['Robot']['season'] = '2027'


# ---- aerial systems: hangar + drones

def s27_bay_cells(n):
    """Drone bays on a 2 x 2 grid of 150 mm cells: front-right, front-left, rear-right, rear-left."""
    return [(.075, -.075), (.075, .075), (-.075, -.075), (-.075, .075)][:max(1, min(4, n))]


def spec_hangar_2027(d):
    """Aerial system hangar (0.30 x 0.30 x 0.20 m, forward +X): shell with drone bays and
    landing pads on top (`DroneBay_<k>` empties mark each pad's centre at its surface),
    referee light bar recessed in the rear face, status lights and video transmitter in the
    front face. The drones are separate GLBs (drone-<model>-spec2027.glb)."""
    reset(); root = empty('Robot'); hangar = empty('Hangar', root)
    n = d['drone_count']; drone = d['drone']; L, W, H = d['chassis_size_m']
    root['season'] = '2027'; root['drone_count'] = n; root['drone_size_m'] = drone['size_m']
    root['drone_asset'] = Path(d['asset']).name.replace('robot-', 'drone-')
    hx, hy = L/2, W/2; floor = .135; pad_top = .141
    c = .012
    outline = [(hx-.002-c, -hy+.002), (hx-.002, -hy+.002+c), (hx-.002, hy-.002-c), (hx-.002-c, hy-.002),
               (-hx+.024, hy-.002), (-hx+.024, -hy+.002)]
    c4_local_prism('HangarBase', [(hx-c, -hy), (hx, -hy+c), (hx, hy-c), (hx-c, hy), (-hx+c, hy), (-hx, hy-c), (-hx, -hy+c), (-hx+c, -hy)], .012, ROBOT_MATTE, hangar, 'z', 0, .002)
    c4_local_prism('HangarShell', outline, floor-.012, ROBOT_PANEL, hangar, 'z', .012, .003)
    # Rear frame round the recessed light bar.
    for s in (-1, 1):
        box('RearCornerPost', (.022, .02, floor-.012), (-hx+.011, s*(hy-.01), (floor+.012)/2), ROBOT_ALUMINUM, hangar, .002)
    box('RearSill', (.022, W-.04, .02), (-hx+.011, 0, .022), ROBOT_ALUMINUM, hangar, .002)
    box('RearHeader', (.022, W-.04, .014), (-hx+.011, 0, floor-.007), ROBOT_ALUMINUM, hangar, .002)
    light_bar('LightBar', (-hx+.0145, 0, .045), math.pi, hangar, .03)
    # Bay level: perimeter walls, dividers and the top rim.
    wall = .006; top = H-.005
    for s in (-1, 1):
        box('BayWall', (L, wall, top-floor), (0, s*(hy-wall/2), (floor+top)/2), ROBOT_PANEL, hangar, .001)
        box('BayWall', (wall, W-2*wall, top-floor), (s*(hx-wall/2), 0, (floor+top)/2), ROBOT_PANEL, hangar, .001)
        box('RimCap', (L, .012, H-top), (0, s*(hy-.006), (top+H)/2), ROBOT_ALUMINUM, hangar, .001)
        box('RimCap', (.012, W-.024, H-top), (s*(hx-.006), 0, (top+H)/2), ROBOT_ALUMINUM, hangar, .001)
    box('BayDivider', (L-2*wall, .004, top-floor-.01), (0, 0, (floor+top-.01)/2), CARBON, hangar, 0)
    box('BayDivider', (.004, W-2*wall, top-floor-.01), (0, 0, (floor+top-.01)/2), CARBON, hangar, 0)
    for k in range(4):
        cx, cy = [(.075, -.075), (.075, .075), (-.075, -.075), (-.075, .075)][k]
        if k < n:
            pad = min(.134, drone['size_m']+.012)
            box('LandingPad', (.138, .138, pad_top-floor), (cx, cy, (floor+pad_top)/2), CARBON, hangar, .001)
            for s in (-1, 1):
                box('PadOutline', (pad, .004, .0008), (cx, cy+s*(pad/2-.002), pad_top+.0004), GLOW, hangar, 0)
                box('PadOutline', (.004, pad, .0008), (cx+s*(pad/2-.002), cy, pad_top+.0004), GLOW, hangar, 0)
                box('ChargeContact', (.03, .006, .0012), (cx, cy+s*.02, pad_top+.0006), ALLOY, hangar, 0)
            s27_flat_text(str(k+1), .03, (cx-.035, cy+.035, pad_top+.0002), -math.pi/2, STATUS_WHITE, hangar, .0003)
            bay = empty(f'DroneBay_{k}', hangar); bay.location = (cx, cy, pad_top); bay['bay'] = k
            box('BayStatusLed', (.002, .012, .006), (hx-wall-.001 if cx > 0 else -hx+wall+.001, cy, top-.012), GLOW, hangar, 0)
        else:
            # Service hatch over an unused cell: referee main controller and the VTM antenna.
            box('ServiceHatch', (.138, .138, .006), (cx, cy, .173), ROBOT_PANEL, hangar, .001)
            referee_box('JudgeMainControl', (.063, .076, .014), (cx, cy, .183), hangar, REF_GRAY, True)
            s27_cyl('VtmAntennaStub', .004, .014, (cx+.045, cy+.045, .183), ROBOT_MATTE, hangar, vertices=10)
    # Front face: status strip, per-drone status LEDs, video transmitter lens and badge.
    fx = hx-.002
    box('StatusStrip', (.002, .2, .008), (fx+.001, 0, .118), GLOW, hangar, 0)
    for k in range(n):
        box('DroneStatusLed', (.002, .012, .012), (fx+.001, -.06+k*.04, .095), STATUS_WHITE, hangar, 0)
    s27_cyl('VideoTransmitterLens', .012, .003, (fx+.0005, .1, .05), LENS, hangar, (0, math.pi/2, 0), 20)
    box('VideoTransmitterBezel', (.002, .04, .04), (fx+.0001, .1, .05), REF_GRAY, hangar, 0)
    c4_text_x(d['name_en'].split()[0], .028, (fx+.0005, -.04, .045), STATUS_WHITE, hangar, .0003)
    # Side faces: vent slats and recessed handles; base rubber feet.
    for s in (-1, 1):
        for k in range(5):
            box('VentSlat', (.06, .002, .004), (.05, s*(hy-.0015), .04+k*.012), ROBOT_MATTE, hangar, 0)
        box('SideHandle', (.07, .002, .016), (-.05, s*(hy-.0015), .09), ROBOT_ALUMINUM, hangar, 0)
        for t in (-1, 1):
            s27_cyl('RubberFoot', .012, .004, (s*(hx-.03), t*(hy-.03), .002), RUBBER, hangar, vertices=12)
    verify_2027(d['slot'], d)
    export(Path(d['asset']).stem)


def spec_drone_2027(d):
    """One aerial robot of the system: quadrotor whose overall plan size is drone.size_m,
    every rotor enclosed by a duct ring with grilles above and below (holes under
    guard_hole_m), the seven-LED navigation ring on top, origin at its centre, forward +X.
    Animated nodes Rotor_0..3 (rear-right, rear-left, front-right, front-left)."""
    drone = d['drone']; S = drone['size_m']; half = S/2; rr = drone['rotor_radius_m']
    reset(); root = empty('Drone'); root['season'] = '2027'; root['size_m'] = S; root['system'] = d['slot']
    wall, gap = .0018, .0015
    ri = rr+gap; ro = ri+wall; c = half-ro
    h = .012+.28*S; z0 = -h/2; hd = .55*h; zt = z0+hd; zr = z0+.55*hd
    body = empty('DroneBody', root)
    hole = min(.01, drone['guard_hole_m']-.002); bar = .0012
    for i, (sx, sy) in enumerate(((-1, -1), (-1, 1), (1, -1), (1, 1))):
        x, y = sx*c, sy*c
        s27_ring_z('GuardDuct', ri, ro, hd-.0012, z0, ROBOT_PANEL, body, (x, y), 40)
        s27_ring_z('DuctLip', ri-.0008, ro, .0012, zt-.0012, ROBOT_ALUMINUM, body, (x, y), 40)
        grille = []
        for zz in (z0+bar/2, zt-bar/2):
            m = math.floor(ri/hole)
            for k in range(-m, m+1):
                off = k*hole; span = math.sqrt(max(0, ri*ri-off*off))
                grille.append(((x-span, y+off, zz), (x+span, y+off, zz)))
                grille.append(((x+off, y-span, zz), (x+off, y+span, zz)))
        s27_bars('GuardGrille', grille, bar, ROBOT_MATTE, body)
        # Motor on three spokes from the duct ring, below the rotor plane.
        s27_cyl('RotorMotor', rr*.24, .006, (x, y, zr-.0045), MOTOR, body, vertices=16)
        s27_bars('MotorSpoke', [((x, y, zr-.007), (x+ri*math.cos(a), y+ri*math.sin(a), zr-.007)) for a in [k*math.tau/3+math.pi/6 for k in range(3)]], .0016, CARBON, body)
        rotor = empty(f'Rotor_{i}', body); rotor.location = (x, y, zr)
        for k in range(2):
            blade = box('PropellerBlade', (rr*.94, .0055*S/.141+.002, .0009), (rr*.47*(1 if k else -1), 0, 0), CARBON, rotor, 0)
            blade.rotation_euler[0] = .25*(1 if k else -1)
        s27_cyl('PropHub', .0032, .003, (0, 0, .0005), ALLOY, rotor, vertices=12)
        # Arm from the duct to the central pod.
        s27_bars('DuctArm', [((x*.35, y*.35, zt-.003), (x*(1-ro/c*.7), y*(1-ro/c*.7), zt-.003))], .003, CARBON, body)
    # Central pod above the ducts: flight controller, battery, camera, nav light ring on top.
    pod_top = h/2-.0035; px, py = .2*S, .15*S
    c4_local_prism('DronePod', [(px, -py*.7), (px, py*.7), (px*.7, py), (-px, py), (-px, -py), (px*.7, -py)], pod_top-zt-.0005, ROBOT_PANEL, body, 'z', zt+.0005, .0015)
    box('DroneBattery', (px*1.4, py*1.3, .004), (-px*.15, 0, zt+.0025), ROBOT_MATTE, body, .0008)
    s27_cyl('FpvCamera', .0045, .006, (px+.002, 0, (zt+pod_top)/2), ROBOT_MATTE, body, (0, math.pi/2, 0), 14)
    s27_cyl('FpvLens', .0032, .001, (px+.0052, 0, (zt+pod_top)/2), LENS, body, (0, math.pi/2, 0), 14)
    box('FrontMarker', (.001, py*.9, .0015), (px+.0004, 0, pod_top-.002), STATUS_WHITE, body, 0)
    s27_cyl('NavLightBase', .0145, .002, (0, 0, pod_top+.001), ROBOT_MATTE, body, vertices=28)
    for k in range(7):
        a = k*math.tau/7
        box('NavLightLed', (.0035, .0028, .0015), (.011*math.cos(a), .011*math.sin(a), pod_top+.00275), GLOW, body, 0).rotation_euler[2] = a
    box('ArmorMarker', (.012, .001, .006), (-px*.3, py+.0004, (zt+pod_top)/2), STATUS_WHITE, body, 0)
    box('ArmorMarker', (.012, .001, .006), (-px*.3, -py-.0004, (zt+pod_top)/2), STATUS_WHITE, body, 0)
    lo, hi = s27_bounds(s27_meshes())
    size = [b-a for a, b in zip(lo, hi)]
    S27_REPORT[f'drone-{d["slot"]}'] = {'size_m': size, 'target_m': S, 'height_m': h, 'centre': [(a+b)/2 for a, b in zip(lo, hi)]}
    print('S27 DRONE', d['slot'], [round(v, 4) for v in size], 'target', S, flush=True)
    if abs(size[0]-S) > .002 or abs(size[1]-S) > .002:
        print('S27 DRONE SIZE MISMATCH', d['slot'], size, S, flush=True)
    export('drone-'+Path(d['asset']).stem.split('-', 1)[1])


def season2027_robot(design):
    if design['role'] == 'heavy':
        spec_heavy_2027(design)
    elif design['role'] == 'aerial':
        spec_hangar_2027(design)
        spec_drone_2027(design)
    else:
        spec_derived_2027(design)


def season2027_assets():
    """RMUC_ASSETS=season2027 (or robots2027 / map2027): only the 2027 assets."""
    if 'ROBOT_MATTE' not in globals():
        spec_materials()
    only = set(filter(None, os.environ.get('RMUC_ROBOTS', '').split(',')))
    if PARTS & {'season2027', 'robots2027'}:
        for slot, design in CONFIG['robot_designs'].items():
            if design.get('season') == '2027' and (not only or slot in only):
                season2027_robot(design)
    if PARTS & {'season2027', 'map2027'}:
        for data in CONFIG['maps'].values():
            if data.get('season') == '2027':
                chapter4_2027_arena(data)
    for key, value in S27_REPORT.items():
        print('S27 REPORT', key, json.dumps(value), flush=True)
