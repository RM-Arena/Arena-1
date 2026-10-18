"""RMUC 2027 field geometry (rules manual V1.0.0, 2026-10-15, chapter 4), in metres.

Figure 4-5 is the placement reference (base 2411, fortress 6571, central highland vertex
9180, outpost 17024/3600, 28000 x 15000). Labelled module dimensions come from figures
4-9..4-38; unlabelled joints are reconstructed from the plan and the renders (figures
4-1..4-4) and stated as such. The blue half is a 180 degree rotation of the red half.
Darts, the radar base and electronic countermeasures are outside this arena.
"""
import math

NAME = 'rmuc2027'
REVISION = 'chapter4-2027-v1'

# Shared datum: the field tilts 1.5 degrees toward both long sides (figure 4-6, 1~2 degrees).
FLOOR_SLOPE_DEG = 1.5
# Figure 4-5.
BASE = [2.411, 7.5]
FORTRESS = [6.571, 7.5]
OUTPOST_BLUE = [17.024, 3.6]
OUTPOST = [28-OUTPOST_BLUE[0], 15-OUTPOST_BLUE[1]]
CENTRAL_VERTEX_X = 9.18
# Section A-A of figure 4-27: deck 300 mm, the fortress-facing band 200 mm, its 150 mm rim
# 400 mm; figure 4-28/4-31: assembly plinth 100 mm above the deck, rune hub 2300 mm above it.
DECK = .30
BAND = .20
RIM = .40
PLINTH_TOP = .40
# Figure 4-26: trapezoid highland 200 mm; figure 4-35 section A: road zone 200 mm.
TRAPEZOID = .20
ROAD = .20
# Figure 4-17: the high point's octagonal floor is 800 mm above the field (three 200 mm
# steps up from the trapezoid highland, 300 mm treads, 1200 mm wide).
HIGH_POINT = .80
HIGH_POINT_CENTER = [1.30, 2.90]
HIGH_POINT_STAIR_Y = (2.30, 3.50)
# Supply area (figure 5-23 [1], figure 7-1 [1]); the resource station and workbench stand
# against the west wall (figures 4-8, 4-20..4-23).
SUPPLY_AREA = [[0, 11.85], [3.1, 11.85], [3.5, 12.25], [3.5, 15], [0, 15]]
WORKBENCH = dict(x=(.05, .80), y=(12.60, 13.05), top=.40)
# Six energy units on a 454 mm diameter ring, 700 mm above the field, axes pointing into
# the field; a unit is withdrawn along its axis (figures 4-21/4-22).
RESOURCE_HUB = [.58, 13.85, .70]  # unit outer ends at x 0.62
RESOURCE_UNITS = 6
# Figure 4-35: road zone, identical in plan to 2026 (1500/1858/2634/3125/3902, 1561+2090).
ROAD_X0 = 3.75
ROAD_NORTH = 15-3.801
ROAD_KERB_Y = ROAD_NORTH+1.561
ROAD_SOUTH = ROAD_KERB_Y+.15
NOTCH_X = (ROAD_X0+3.902, ROAD_X0+3.902+1.148)
# Section A / plan of figure 4-35: road tunnel. The [2] 15 degree ramp climbs from the field
# floor to the road's south strip (200 mm in a 746 mm run) through an 800 mm portal: two
# 100 mm posts and a 350 mm deep roof over the top of the ramp, ending at the strip edge,
# 260 mm clear above road level and 358 mm to its chamfered top. No side walls.
ROAD_TUNNEL_X = 9.32
ROAD_TUNNEL_RAMP_Y = (round(ROAD_SOUTH-ROAD/math.tan(math.radians(15)), 6), ROAD_SOUTH)
ROAD_TUNNEL_ROOF_Y = (round(ROAD_SOUTH-.35, 6), ROAD_SOUTH)
ROAD_TUNNEL_POST = .10
# Cards: on the open part of the ramp, under the roof, and on the road beyond the portal.
ROAD_TUNNEL_CARD_Y = (12.33, round(ROAD_SOUTH-.175, 6), 13.31)
# Figure 4-38: the far-highland tunnel (2900 long, 800 passage between 155 mm rails with
# chamfered tops, 350 wide metal plate 250 mm above the passage and 270 to its top, flush
# with the rails) runs from the end of the red road onto the tip of the blue trapezoid
# highland's tongue, where 2026 had the fly slope. Its south rail meets the field edge.
FAR_TUNNEL_X = (12.57, 15.47)
FAR_TUNNEL_Y = 14.43
FAR_TUNNEL_WALL = .155
# Section B / figure 4-35 [1]: near-highland tunnel; an 11 degree ramp drops from the road to
# a floor-level 800 mm passage under a 350 mm roof 250 mm high (417 mm to its top), between a
# 155 mm rail on the central highland's edge and the far tunnel's north rail, which the two
# tunnels share (plan of figure 4-35).
NEAR_TUNNEL_ROOF_X = 14.92
NEAR_TUNNEL_Y = (round(FAR_TUNNEL_Y-.4-FAR_TUNNEL_WALL-.8, 6), round(FAR_TUNNEL_Y-.4-FAR_TUNNEL_WALL, 6))
NEAR_TUNNEL_RAIL = .155
# Figure 4-34: the outpost's 100 mm base plate (650 wide) is the 400 mm pedestal's top on the
# 300 mm deck; the outpost's own dimensions (armor 1116-1316, top 1578) start at its underside.
OUTPOST_PLINTH = .10
ACCESS_FOOT_X = round(NEAR_TUNNEL_ROOF_X-.175-.44, 6)
ACCESS_TOP_X = round(ACCESS_FOOT_X-ROAD/math.tan(math.radians(11)), 6)
# Figure 4-26: 6682+2717 long, 4131 deep, 4586 bottom edge, 1140 tongue, 23 degree slope.
TRAPEZOID_X0 = 3.13
TRAPEZOID_TIP_X = round(TRAPEZOID_X0+6.682+2.717, 6)
# Rune gantry: the 2026 frame members (figures 4-31/4-32 unchanged), on a 400 mm plinth.
RUNE_GANTRY = dict(face_offset_m=.35, hub_height_m=2.3, arm_radius_m=.7,
                   post_center_m=1.12, post_size_m=.165, post_top_m=2.56,
                   pedestal_half_length_m=.95, pedestal_half_depth_m=.3, pedestal_height_m=.1,
                   foot_outer_m=1.35, foot_half_depth_m=.32, foot_height_m=.36,
                   crossbeam_depth_m=.1, crossbeam_height_m=.14, gearbox_m=[.26, .24, .26],
                   # Figure 4-30: 400 x 400 hangar platforms (320 pad) 1200 mm above the plinth,
                   # outboard of each post; S109 places the hangar's infrared link on the post.
                   hangar_platform_m=.40, hangar_pad_m=.32, hangar_platform_above_plinth_m=1.2,
                   hangar_platform_center_m=1.40)
CORE_INITIAL_POSE = [-.2, .2, .8, 0, 90, 0]
# Figure 4-25: fortress, pointy-ended hexagon 2107 across flats, 150 high, 20 degree sides.
FORTRESS_OUTER_R = 2.107/math.sqrt(3)
FORTRESS_TOP_R = 1.131/math.sqrt(3)


def mirrored(point):
    return [round(28-point[0], 6), round(15-point[1], 6)]


def bounds(points):
    xs, ys = zip(*points)
    return dict(x=min(xs), y=min(ys), w=max(xs)-min(xs), h=max(ys)-min(ys))


def polygon(identifier, points, elevation, page, **extra):
    value = dict(id=identifier, **bounds(points), polygon=points, kind='platform',
                 elevation=elevation, speed_multiplier=1, direction=0, axis='x',
                 source_page=page, base_elevation=0, edge_ramp_m=0, bump_pitch=0, bump_height=0, slope_deg=0)
    value.update(extra)
    return value


def hexagon(x, y, radius, phase=0.0):
    return [[x+radius*math.cos(phase+i*math.tau/6), y+radius*math.sin(phase+i*math.tau/6)] for i in range(6)]


def octagon(x, y, width, chamfer):
    h, c = width/2, width/2-chamfer
    return [[x-c, y-h], [x+c, y-h], [x+h, y-c], [x+h, y+c], [x+c, y+h], [x-c, y+h], [x-h, y+c], [x-h, y-c]]


def ramp(identifier, start, end, width, low, high, page):
    dx, dy = end[0]-start[0], end[1]-start[1]; length = math.hypot(dx, dy)
    nx, ny = -dy/length*width/2, dx/length*width/2
    points = [[start[0]+nx, start[1]+ny], [end[0]+nx, end[1]+ny],
              [end[0]-nx, end[1]-ny], [start[0]-nx, start[1]-ny]]
    value = polygon(identifier, points, high, page)
    value.update(kind='ramp', ramp_start=start, ramp_end=end, base_elevation=low,
                 slope_deg=math.degrees(math.atan2(high-low, length)))
    return value


def edge_ramp(identifier, a, b, outward, low, high, degrees, page):
    """A sloped strip along edge a-b, falling toward `outward` (unit normal) from `high`."""
    run = (high-low)/math.tan(math.radians(degrees))
    o = [outward[0]*run, outward[1]*run]
    points = [list(a), list(b), [b[0]+o[0], b[1]+o[1]], [a[0]+o[0], a[1]+o[1]]]
    value = polygon(identifier, points, high, page)
    mid = [(a[0]+b[0])/2, (a[1]+b[1])/2]
    value.update(kind='ramp', ramp_start=[mid[0]+o[0], mid[1]+o[1]], ramp_end=mid, base_elevation=low, slope_deg=degrees)
    return value


def make_arena():
    terrain, walls, zones, paint, fixtures = [], [], [], [], []

    def line_wall(identifier, a, b, thickness, height, page, bottom=0, kind='barrier', **shape):
        # `shape` carries visual-only profile hints for the asset build (the engine ignores them).
        length = math.dist(a, b)
        walls.append(dict(id=identifier, x=(a[0]+b[0]-length)/2, y=(a[1]+b[1]-thickness)/2,
                          w=length, h=thickness, rotation=math.atan2(b[1]-a[1], b[0]-a[0]),
                          height=height, bottom=bottom+min((a[1]+b[1])/2, 15-(a[1]+b[1])/2)*math.tan(math.radians(FLOOR_SLOPE_DEG)),
                          kind=kind, source_page=page, **shape))

    def add_zone(identifier, kind, point, radius, owner=None, points=None, group=None, order=None, crossing=None):
        value = dict(id=identifier, kind=kind, x=point[0], y=point[1], radius=radius, owner=owner,
                     source='2027 chapter 4 placement + figure 5-23 buff-card outline')
        if points: value['polygon'] = points
        if group: value['group'] = group
        if order is not None: value['order'] = order
        if crossing: value['crossing'] = crossing
        zones.append(value)

    # ---- Central highland (figures 4-27/4-28): 7740 between the fortress-facing rims, 10820
    # long, oblique shoulders; both long-axis ends fall 12 degrees onto the road zones.
    x0, x1, y0, y1 = 14-3.87, 14+3.87, 2.09, 12.91
    end_run = (DECK-ROAD)/math.tan(math.radians(12))
    # 12 degree end slopes beside each outpost ([3] in figure 4-27) are cut out of the deck.
    red_end = [[x0+.35, y1], [12.40, y1]]
    cut = [[12.40, y1], [12.40, y1-end_run], [x0+.35, y1-end_run], [x0+.35, y1]]
    deck = [[12.45, y0], *map(mirrored, cut), [x1, y0], [x1, 9.17], [15.55, y1], *cut, [x0, y1], [x0, 5.83]]
    terrain.append(polygon('central_highland', deck, DECK, 50))
    for team, f in (('red', list), ('blue', mirrored)):
        a, b = map(f, red_end)
        outward = [0, 1] if team == 'red' else [0, -1]
        inward = [-outward[0]*end_run, -outward[1]*end_run]
        strip = polygon(f'central_{team}_end_slope', [a, b, [b[0]+inward[0], b[1]+inward[1]], [a[0]+inward[0], a[1]+inward[1]]], DECK, 50)
        mid = [(a[0]+b[0])/2, (a[1]+b[1])/2]
        strip.update(kind='ramp', ramp_start=mid, ramp_end=[mid[0]+inward[0], mid[1]+inward[1]], base_elevation=ROAD, slope_deg=12)
        terrain.append(strip)
    for team, f in (('red', list), ('blue', mirrored)):
        # Fortress-facing band (section A-A: 200 mm, reaching the 9180 vertex) and the deck's
        # 150 mm rim (400 mm): terrain-crossing robots climb two risers, as in 2026.
        band = [[x0, 5.83], [x0, 9.17], [CENTRAL_VERTEX_X, 8.25], [CENTRAL_VERTEX_X, 6.75]]
        terrain.append(polygon(f'central_{team}_band', list(map(f, band)), BAND, 50))
        rim = [[x0, 6.0], [x0+.15, 6.0], [x0+.15, 9.0], [x0, 9.0]]
        terrain.append(polygon(f'central_{team}_rim', list(map(f, rim)), RIM, 50))
        # Low kerbs on the oblique shoulders (renders 4-1..4-3), standing on the deck.
        for i, (a, b) in enumerate([([12.45, y0], [x0, 5.83]), ([x0, 9.17], [x0, y1]), ([12.40, y1], [15.55, y1])]):
            line_wall(f'central_{team}_kerb_{i}', f(a), f(b), .15, .15, 50, bottom=DECK)
    # Assembly plinth (figures 4-28/4-29): 100 mm above the deck, 12 degree sides.
    angle = math.pi/4; nx, ny = math.cos(angle), math.sin(angle); tx, ty = -ny, nx
    plinth = [[14+nx*a+tx*b, 7.5+ny*a+ty*b] for a, b in [(-1.25, -1.05), (-.9, -1.4), (.9, -1.4), (1.25, -1.05), (1.25, 1.05), (.9, 1.4), (-.9, 1.4), (-1.25, 1.05)]]
    assembly = polygon('assembly_plinth', plinth, PLINTH_TOP, 51, base_elevation=DECK, edge_ramp_m=(PLINTH_TOP-DECK)/math.tan(math.radians(12)))
    assembly['kind'] = 'bevel'; terrain.append(assembly)

    for team in ('red', 'blue'):
        flip = team == 'blue'; p = lambda v: mirrored(v) if flip else list(v)
        yaw = math.pi if flip else 0
        # ---- Trapezoid highland (figure 4-26).
        trap = [[TRAPEZOID_X0, 0], [TRAPEZOID_TIP_X, 0], [TRAPEZOID_TIP_X, 1.14], [TRAPEZOID_X0+6.682, 1.14],
                [TRAPEZOID_X0+4.586, 4.131], [TRAPEZOID_X0, 4.131]]
        terrain.append(polygon(team+'_trapezoid', list(map(p, trap)), TRAPEZOID, 49))
        edge_a, edge_b = trap[4], trap[3]
        dx, dy = edge_b[0]-edge_a[0], edge_b[1]-edge_a[1]; length = math.hypot(dx, dy)
        # Outward normal of the diagonal points away from the trapezoid (toward +x, +y).
        outward = [abs(dy)/length, abs(dx)/length]
        tr = edge_ramp(team+'_trapezoid_23', p(edge_a), p(edge_b), outward if not flip else [-outward[0], -outward[1]], 0, TRAPEZOID, 23, 49)
        terrain.append(tr)
        # ---- High point (figure 4-17): octagonal floor 800 mm high with a 300 mm parapet,
        # reached by three 200 mm steps (300 mm treads, 1200 mm wide) from the trapezoid.
        hp = HIGH_POINT_CENTER
        block = [[.04, 1.35], [2.53, 1.35], [2.53, 4.45], [.04, 4.45]]
        terrain.append(polygon(team+'_high_point', list(map(p, block)), HIGH_POINT, 41))
        sy = HIGH_POINT_STAIR_Y
        for k, (xa, xb, z) in enumerate([(2.53, 2.83, .60), (2.83, TRAPEZOID_X0, .40)]):
            terrain.append(polygon(f'{team}_high_point_step_{k}', list(map(p, [[xa, sy[0]], [xb, sy[0]], [xb, sy[1]], [xa, sy[1]]])), z, 41))
        floor = octagon(hp[0], hp[1], 2.4, .55)
        # Parapet: 300 mm above the floor on every octagon side except the stair opening (+x).
        for i in range(8):
            a, b = floor[i], floor[(i+1) % 8]
            if a[0] > hp[0]+1.1 and b[0] > hp[0]+1.1:
                continue  # east side: the 1200 mm stair opening
            line_wall(f'{team}_high_point_parapet_{i}', p(a), p(b), .10, .30, 41, bottom=HIGH_POINT)
        add_zone(team+'_high_point', 'high_point', p(hp), 1.0, team, list(map(p, octagon(hp[0], hp[1], 2.2, .5))))
        # ---- Dart launch station (figure 4-14): scenery and a both-team no-go area.
        line_wall(team+'_dart_station', p([.08, .70]), p([2.20, .70]), 1.10, 1.30, 40)
        fixtures.append(dict(kind='dart_station', team=team, point=p([1.14, .70]), yaw=yaw))
        # ---- Road zone (figure 4-35): 1561 north strip, 150 kerb, 2090 south strip.
        x0r, north, kerb, south = ROAD_X0, ROAD_NORTH, ROAD_KERB_Y, ROAD_SOUTH
        tun = (FAR_TUNNEL_Y-.4-FAR_TUNNEL_WALL, FAR_TUNNEL_Y+.4+FAR_TUNNEL_WALL)
        road = [[x0r, north], [x0r+1.858, north], [x0r+2.634, kerb], [x0r+2.634, south], [ACCESS_TOP_X, south],
                [ACCESS_TOP_X, tun[0]], [FAR_TUNNEL_X[0], tun[0]], [FAR_TUNNEL_X[0], 15], [x0r, 15]]
        terrain.append(polygon(team+'_road', list(map(p, road)), ROAD, 57))
        # [2] 15 degree slope from the notch floor onto the north strip, between the corners
        # labelled 1858/3125 (north) and 2634/3902 (kerb line).
        high = [[x0r+1.858, north], [x0r+2.634, kerb]]
        ex, ey = high[1][0]-high[0][0], high[1][1]-high[0][1]; length = math.hypot(ex, ey)
        normal = [ey/length, -ex/length]
        run = ROAD/math.tan(math.radians(15))
        low = [[high[0][0]+normal[0]*run, high[0][1]+normal[1]*run], [high[1][0]+normal[0]*run, high[1][1]+normal[1]*run]]
        slope = polygon(team+'_road_slope', list(map(p, [high[0], low[0], low[1], high[1]])), ROAD, 57)
        mid_high = [(high[0][0]+high[1][0])/2, (high[0][1]+high[1][1])/2]
        mid_low = [(low[0][0]+low[1][0])/2, (low[0][1]+low[1][1])/2]
        slope.update(kind='ramp', ramp_start=p(mid_low), ramp_end=p(mid_high), slope_deg=15)
        terrain.append(slope)
        # Kerb between the strips (the bumps' north edge), from 1500 to 3902.
        line_wall(team+'_road_kerb', p([x0r+1.5, kerb+.075]), p([x0r+3.902, kerb+.075]), .15, .15, 57, bottom=ROAD)
        # Figures 4-36/4-37: ten 70 mm humps, 240 mm pitch, across the south strip 1500..3902.
        ridge = polygon(team+'_road_bumps', list(map(p, [[x0r+1.5, south], [x0r+3.9, south], [x0r+3.9, 15], [x0r+1.5, 15]])), ROAD, 58)
        ridge.update(kind='bumps', bump_pitch=.24, bump_height=.07, speed_multiplier=.82)
        terrain.append(ridge)
        # Road tunnel (section A): 15 degree ramp from the floor onto the road through a portal
        # whose roof covers the top 350 mm of the ramp. Local +y of a wall runs left of a->b, so
        # `chamfer` names the top edges (-1/+1 across, 'ends' along) that are bevelled.
        rx, (ry0, ry1) = ROAD_TUNNEL_X, ROAD_TUNNEL_RAMP_Y
        half = .4+ROAD_TUNNEL_POST
        terrain.append(ramp(team+'_road_tunnel_ramp', p([rx, ry0]), p([rx, ry1]), 2*half, 0, ROAD, 57))
        ry = ROAD_TUNNEL_ROOF_Y
        roof_z = ROAD+.26
        line_wall(team+'_road_tunnel_roof', p([rx, ry[0]]), p([rx, ry[1]]), 2*half, .098, 57, bottom=roof_z,
                  chamfer=[-1, 1], chamfer_m=.06)
        post_bottom = ROAD*(ry[0]-ry0)/(ry1-ry0)
        for x in (rx-.4-ROAD_TUNNEL_POST/2, rx+.4+ROAD_TUNNEL_POST/2):
            line_wall(team+'_road_tunnel_post', p([x, ry[0]]), p([x, ry[1]]), ROAD_TUNNEL_POST, roof_z-post_bottom, 57, bottom=post_bottom)
        # Near-highland tunnel: 11 degree access ramp, floor-level passage, 350 mm roof.
        ny0, ny1 = NEAR_TUNNEL_Y
        mid_y = (ny0+ny1)/2
        access_y0 = ny0-NEAR_TUNNEL_RAIL
        terrain.append(ramp(team+'_near_tunnel_access', p([ACCESS_FOOT_X, (access_y0+ny1)/2]), p([ACCESS_TOP_X, (access_y0+ny1)/2]), ny1-access_y0, 0, ROAD, 57))
        line_wall(team+'_near_tunnel_roof', p([NEAR_TUNNEL_ROOF_X, access_y0]), p([NEAR_TUNNEL_ROOF_X, ny1]), .35, .167, 57, bottom=.25,
                  chamfer=[-1, 1], chamfer_m=.03)
        # North rail on the central highland's edge, ending with the shared rail where the
        # highland's edge turns away; the south side is the far tunnel's rail.
        line_wall(team+'_near_tunnel_side', p([ACCESS_TOP_X, ny0-NEAR_TUNNEL_RAIL/2]), p([FAR_TUNNEL_X[1], ny0-NEAR_TUNNEL_RAIL/2]),
                  NEAR_TUNNEL_RAIL, .417, 57, chamfer=[-1], chamfer_m=.05)
        # Far-highland tunnel (figure 4-38): road-level passage between rails, plate at x 14.
        fx0, fx1 = FAR_TUNNEL_X
        terrain.append(polygon(team+'_far_tunnel_floor', list(map(p, [[fx0, tun[0]], [fx1, tun[0]], [fx1, tun[1]], [fx0, tun[1]]])), ROAD, 59))
        for y, outer in ((tun[0]+FAR_TUNNEL_WALL/2, -1), (tun[1]-FAR_TUNNEL_WALL/2, 1)):
            line_wall(team+'_far_tunnel_side', p([fx0, y]), p([fx1, y]), FAR_TUNNEL_WALL, .27, 59, bottom=ROAD,
                      chamfer=[outer, 'ends'], chamfer_m=.05)
        line_wall(team+'_far_tunnel_roof', p([14.0, tun[0]]), p([14.0, tun[1]]), .35, .02, 59, bottom=ROAD+.25)
        # Low kerbs: road west wall and the trapezoid's north edge.
        for i, (a, b) in enumerate([([TRAPEZOID_X0, .05], [TRAPEZOID_TIP_X-.05, .05]), ([x0r, north], [x0r, 14.95]),
                                    ([x0r, north], [x0r+1.858, north])]):
            line_wall(team+f'_kerb_{i}', p(a), p(b), .15, .6 if i == 0 else .35, 49 if i == 0 else 57)
        # ---- Fortress (figure 4-25) and base pedestal (figure 4-10).
        fort = p(FORTRESS)
        ft = polygon(team+'_fortress', hexagon(*fort, FORTRESS_OUTER_R, math.pi/6), .15, 48, edge_ramp_m=.15/math.tan(math.radians(20)))
        ft['kind'] = 'bevel'; terrain.append(ft)
        base = p(BASE)
        pedestal = [(-.9365, -.1395), (-.547, -.8045), (.547, -.8045), (.9365, -.1395), (.386, .8045), (-.386, .8045)]
        bp = [[BASE[0]+dx, BASE[1]+dy] for dx, dy in pedestal]
        terrain.append(polygon(team+'_base_pedestal', list(map(p, bp)), .2, 37))
        # Outpost pedestal (figure 4-34): the outpost stands 400 mm above the field.
        op = p(OUTPOST)
        terrain.append(polygon(team+'_outpost_pedestal', [[op[0]+.33*math.cos(a), op[1]+.33*math.sin(a)] for a in [k*math.tau/8 for k in range(8)]], .40, 56))
        # ---- Supply area: workbench and resource station against the west wall.
        wb = WORKBENCH
        line_wall(team+'_workbench', p([wb['x'][0], sum(wb['y'])/2]), p([wb['x'][1], sum(wb['y'])/2]), wb['y'][1]-wb['y'][0], wb['top'], 46)
        line_wall(team+'_resource_frame', p([.05, RESOURCE_HUB[1]]), p([.42, RESOURCE_HUB[1]]), .50, 1.10, 45)
        hub = p(RESOURCE_HUB[:2])
        fixtures.append(dict(kind='resource', team=team, point=hub, yaw=yaw, units=RESOURCE_UNITS,
                             ring_diameter_m=.454, hub_z_m=RESOURCE_HUB[2],
                             # The gripper meets a unit's outer end and withdraws it along its axis.
                             pick_point=[*p([RESOURCE_HUB[0]+.04, RESOURCE_HUB[1]]), RESOURCE_HUB[2]],
                             pick_dir=[1 if flip else -1, 0, 0]))
        fixtures.append(dict(kind='workbench', team=team, point=p([sum(wb['x'])/2, sum(wb['y'])/2]), yaw=yaw,
                             top_m=wb['top'], size_m=[wb['x'][1]-wb['x'][0], wb['y'][1]-wb['y'][0]],
                             dock_point=p([wb['x'][1]+.42, sum(wb['y'])/2])))
        # ---- Buff points (figure 5-23).
        add_zone(team+'_base', 'base', base, 1.8, team, hexagon(*base, 2.0225, math.pi/6))
        add_zone(team+'_fortress', 'fortress', fort, .56, team, hexagon(*fort, FORTRESS_TOP_R, math.pi/6))
        add_zone(team+'_supply', 'supply', p([1.4, 13.0]), .9, team, list(map(p, SUPPLY_AREA)))
        add_zone(team+'_resource', 'resource', p([RESOURCE_HUB[0]+.62, RESOURCE_HUB[1]]), .55, team)
        add_zone(team+'_workbench', 'workbench', fixtures[-1]['dock_point'], .45, team)
        outpost_card = [[10.35, 10.38], [11.18, 10.38], [11.95, 12.30], [11.0, 12.30], [10.35, 11.30]]
        add_zone(team+'_outpost', 'outpost', op, .85, team, list(map(p, outpost_card)))
        central_card = [[12.15, 2.66], [12.85, 2.66], [11.18, 5.84], [11.18, 10.33], [10.35, 10.33], [10.35, 5.54]]
        # The central highland buff card doubles as the highland crossing's high card.
        add_zone(team+'_central', 'central', p([10.8, 7.5]), .55, team, list(map(p, central_card)),
                 group=team+'_highland', order=1, crossing='highland')
        add_zone(team+'_highland_low', 'highland', p([8.765, 7.5]), .4, team,
                 list(map(p, [[8.35, 6.08], [9.18, 6.08], [9.18, 8.92], [8.35, 8.92]])), group=team+'_highland', order=0)
        side = 1 if not flip else -1
        add_zone(team+'_assembly', 'assembly', [14-side*.94*nx, 7.5-side*.94*ny], .65, team)
        # Road crossing: low card in the notch floor, high card on the road (figure 4-35).
        notch_mid = sum(NOTCH_X)/2
        for order, pt in enumerate([[notch_mid-.25, 12.56], [notch_mid-.25, 13.40]]):
            add_zone(team+f'_road_{order}', 'road', p(pt), .35, group=team+'_road', order=order)
        # Tunnels: an end card, a card under the roof and the far end card (order 0, 1, 2).
        for name, cards in (('road_tunnel', [[ROAD_TUNNEL_X, y] for y in ROAD_TUNNEL_CARD_Y]),
                            ('near_tunnel', [[14.36, mid_y], [NEAR_TUNNEL_ROOF_X, mid_y], [15.50, mid_y]]),
                            ('far_tunnel', [[13.40, FAR_TUNNEL_Y], [14.0, FAR_TUNNEL_Y], [14.60, FAR_TUNNEL_Y]])):
            for order, pt in enumerate(cards):
                add_zone(team+f'_{name}_{order}', 'tunnel', p(pt), .30 if order != 1 else .17, group=team+'_'+name, order=order)
        paint.extend([dict(team=team, kind='edge', points=list(map(p, trap)), closed=True),
                      dict(team=team, kind='edge', points=list(map(p, road)), closed=True),
                      dict(team=team, kind='spawn', points=hexagon(*base, 2.0225, math.pi/6), closed=True)])

    # ---- Rune gantry and hangar platforms (figures 4-28..4-33).
    g = RUNE_GANTRY
    along = lambda s, d=0: [14+tx*s+nx*d, 7.5+ty*s+ny*d]
    line_wall('rune_pedestal', along(-g['pedestal_half_length_m']), along(g['pedestal_half_length_m']),
              2*g['pedestal_half_depth_m'], g['pedestal_height_m'], 51, bottom=PLINTH_TOP)
    for s in (-1, 1):
        line_wall('rune_post_foot', along(s*g['pedestal_half_length_m']), along(s*g['foot_outer_m']),
                  2*g['foot_half_depth_m'], g['foot_height_m'], 51, bottom=PLINTH_TOP)
        line_wall('rune_post', along(s*(g['post_center_m']-g['post_size_m']/2)), along(s*(g['post_center_m']+g['post_size_m']/2)),
                  g['post_size_m'], g['post_top_m']-g['foot_height_m'], 54, bottom=PLINTH_TOP+g['foot_height_m'])
    inner = g['post_center_m']-g['post_size_m']/2; hub_z = PLINTH_TOP+g['hub_height_m']
    line_wall('rune_crossbeam_roof', along(-inner), along(inner), g['crossbeam_depth_m'], g['crossbeam_height_m'], 54, bottom=hub_z-g['crossbeam_height_m']/2)
    box = g['gearbox_m']
    line_wall('rune_gearbox_roof', along(-box[0]/2), along(box[0]/2), box[1], box[2], 54, bottom=hub_z-box[2]/2)
    fixtures.append(dict(kind='rune_gantry', team=None, point=[14, 7.5], yaw=angle, plinth_top_m=PLINTH_TOP, **g))
    hangars = {}
    platform_z = PLINTH_TOP+g['hangar_platform_above_plinth_m']
    for team, s in (('red', 1), ('blue', -1)):
        c = along(s*g['hangar_platform_center_m'])
        half = g['hangar_platform_m']/2
        line_wall(f'{team}_hangar_platform_roof', along(s*(g['hangar_platform_center_m']-half)), along(s*(g['hangar_platform_center_m']+half)),
                  g['hangar_platform_m'], .04, 53, bottom=platform_z-.04)
        hangars[team] = dict(x=round(c[0], 6), y=round(c[1], 6), z=round(platform_z+min(c[1], 15-c[1])*math.tan(math.radians(FLOOR_SLOPE_DEG)), 6),
                             yaw=round(angle+(math.pi/2 if s > 0 else -math.pi/2), 6), pad_m=g['hangar_pad_m'], platform_m=g['hangar_platform_m'])
        fixtures.append(dict(kind='hangar_platform', team=team, point=[hangars[team]['x'], hangars[team]['y']], yaw=hangars[team]['yaw'],
                             top_m=platform_z, size_m=[g['hangar_platform_m']]*2))
    assembly_frames = {}
    for team, sign in (('red', -1), ('blue', 1)):
        x_axis = [sign*nx, sign*ny]; y_axis = [-x_axis[1], x_axis[0]]
        origin = along(0, sign*g['pedestal_half_depth_m'])
        assembly_frames[team] = dict(origin=origin, x_axis=x_axis, y_axis=y_axis, z0_m=PLINTH_TOP, initial_pose=CORE_INITIAL_POSE,
                                     pose_units='m,m,m,deg,deg,deg', source_pages=[78, 79, 80, 81, 82])

    forbidden = []
    for team in ('red', 'blue'):
        flip = team == 'blue'; p = lambda v: mirrored(v) if flip else list(v)
        for kind, pts, owner in [('base', [[BASE[0]-.95, BASE[1]-.85], [BASE[0]+.95, BASE[1]+.85]], None),
                                 ('supply', [[0, 11.85], [3.5, 15]], team),
                                 ('assembly', [[12.64, 6.14], [13.92, 7.42]], team),
                                 ('dart_station', [[0, 0], [2.3, 1.3]], None)]:
            b = bounds(list(map(p, pts))); forbidden.append(dict(kind=kind, owner=owner, **b))
    # Ground robots start in the hexagonal start zone; the aerial system on its hangar platform.
    points = {'red': {'1': [3.85, 7.5], '3': [3.2, 6.15], '4': [3.2, 8.85], '7': [1.55, 6.15],
                      '6': [hangars['red']['x'], hangars['red']['y']]}}
    points['blue'] = {k: mirrored(v) for k, v in points['red'].items()}
    points['blue']['6'] = [hangars['blue']['x'], hangars['blue']['y']]
    # Control positions (5.6.2): each team's outpost position (outpost + central highland
    # cards) and base position (base + fortress cards).
    positions = {}
    for team in ('red', 'blue'):
        positions[f'{team}_outpost'] = dict(owner=team, kind='outpost', zones=[f'{team}_outpost', f'{team}_central'])
        positions[f'{team}_base'] = dict(owner=team, kind='base', zones=[f'{team}_base', f'{team}_fortress'])
    route = [[5.2, 9.9], [7.6, 10.6], [8.25, 11.6], [8.25, 12.3], [7.0, 12.5], [5.6, 12.0], [4.5, 12.2], [4.5, 13.7],
             [10.6, 13.9], [11.9, 13.9], [12.0, 12.7], [11.4, 11.9]]
    nodes = [[1.2, 10.6], [3.9, 10.2], [7.2, 9.6], [8.0, 7.5], [10.6, 7.5], [12.0, 5.2], [12.0, 9.8], [13.0, 6.4],
             [15.0, 8.6], [16.0, 5.2], [16.0, 9.8], [17.4, 7.5], [20.0, 7.5], [20.8, 5.4], [24.1, 4.8], [26.8, 4.4],
             [4.4, 5.0], [23.6, 10.0], [5.0, 3.1], [8.9, 2.2], [12.9, 3.3], *route, *map(mirrored, route),
             mirrored([5.0, 3.1]), mirrored([8.9, 2.2]), mirrored([12.9, 3.3])]
    return dict(name=NAME, season='2027', ruleset='rmuc2027', layout_revision=REVISION, width=28, height=15, floor_slope_deg=FLOOR_SLOPE_DEG,
                terrain=terrain, obstacles=walls, zones=zones, forbidden=forbidden, spawn_points=points,
                bases={'red': BASE, 'blue': mirrored(BASE)},
                outposts={'red': OUTPOST, 'blue': OUTPOST_BLUE}, outpost_plinth_m=OUTPOST_PLINTH,
                pads={'red': [hangars['red']['x'], hangars['red']['y']], 'blue': [hangars['blue']['x'], hangars['blue']['y']]},
                hangars=hangars, positions=positions,
                flight_lanes={'red': dict(min_x=.3, max_x=27.7, center_y=7.5), 'blue': dict(min_x=.3, max_x=27.7, center_y=7.5)},
                rune=dict(x=14, y=7.5, z=hub_z+7.5*math.tan(math.radians(FLOOR_SLOPE_DEG)), axis_yaw=angle,
                          face_offset_m=g['face_offset_m'], arm_radius_m=g['arm_radius_m'],
                          coaxial=True, red_face='-axis', source='2027 figures 4-28..4-33; 5.6.3 coaxial red/blue faces'),
                assembly_frames=assembly_frames,
                asset='/assets/map-rmuc2027.glb',
                # The 2027 rune faces and tech core keep the chapter-4 geometry; the hangar
                # platforms are part of the field mesh.
                structure_assets=dict(base='/assets/base-ch4.glb', outpost='/assets/outpost-ch4.glb',
                                      rune='/assets/rune-ch4v2.glb', core='/assets/tech-core-ch4v2.glb'),
                field_geometry=dict(fixtures=fixtures, paint=paint, source_pages=[29, 31, 32, 35, 36, 37, 41, 44, 45, 46, 48, 49, 50, 51, 52, 53, 54, 56, 57, 58, 59, 102, 133],
                                    dimension_note='Labelled 2027 dimensions are normative; unlabelled joints and heights are plan/render reconstructions.'),
                navigation=dict(nodes=nodes))


if __name__ == '__main__':
    import json
    arena = make_arena()
    print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in arena.items() if k in ('terrain', 'obstacles', 'zones', 'forbidden')}))
