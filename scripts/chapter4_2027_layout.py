"""RMUC 2027 field geometry (rules manual V1.0.0, 2026-10-15, chapter 4), in metres.

Figure 4-5 is the placement reference (base 2411, fortress 6571, central highland vertex
9180, outpost 17024/3600, 28000 x 15000). Labelled module dimensions come from figures
4-9..4-38. Unlabelled outlines and the floor markings were measured on the module drawings
after calibrating each figure on its own dimension lines (figures 4-9, 4-25..4-27, 4-35:
57..192 px/m) and cross-checked on the calibrated plan of figure 4-5 (25 px/m); those values
carry their figure in the comments. The blue half is a 180 degree rotation of the red half.
Darts, the radar base and electronic countermeasures are outside this arena.
"""
import math

NAME = 'rmuc2027'
REVISION = 'chapter4-2027-v2'

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
# steps up from the trapezoid highland, 300 mm treads, 1200 mm wide). In the plan of figure 4-17
# (192 px/m, located on the trapezoid's red line) the red floor octagon runs x 0.398..2.440,
# y 1.798..3.840: the floor centre is (1.42, 2.82).
HIGH_POINT = .80
HIGH_POINT_CENTER = [1.42, 2.82]
HIGH_POINT_STAIR_Y = (2.22, 3.42)
# Section B-B of figure 4-17: a second 1200 mm flight leaves the floor's south opening and
# drops to the field in four 200 mm risers (300 mm treads), recessed into the block, which
# ends at y 4.82 on both sides of it (plan of figure 4-17; figure 4-8 within 3 cm).
HIGH_POINT_SOUTH_STEPS = [(3.92, 4.22, .60), (4.22, 4.52, .40), (4.52, 4.82, .20)]
# Section A-A: from the floor's east opening a 600 mm tread, then the 400 mm second tread,
# which is a ledge along the trapezoid's whole west edge from the field wall to y 4.72 (plans of
# figures 4-17 and 4-8: x 2.82..3.13, its south end chamfered).
HIGH_POINT_TREAD_X = (2.51, 2.82)
HIGH_POINT_LEDGE = [[2.82, 0], [3.13, 0], [3.13, 4.57], [2.98, 4.72], [2.82, 4.72]]
# Supply area (figure 5-23 [1], figure 7-1 [1]); the resource station and workbench stand
# against the west wall (figures 4-8, 4-20..4-23).
# Its white boundary (figures 4-5 and 4-8, which agree on the 30 degree leg within 3 cm and differ by 4 cm on the
# straight one, averaged): y 11.805 from the west wall to x 2.662, then 30 degrees to (3.29, 12.168); the road's
# west wall (x 3.51) closes the area.
SUPPLY_LINE = [[0.08, 11.805], [2.662, 11.805], [3.29, 12.168]]
SUPPLY_AREA = [[0, 11.805], [2.662, 11.805], [3.51, 12.296], [3.51, 15], [0, 15]]
WORKBENCH = dict(x=(.05, .80), y=(12.60, 13.05), top=.40)
# Six energy units on a 454 mm diameter ring, 700 mm above the field, axes pointing into
# the field; a unit is withdrawn along its axis (figures 4-21/4-22).
RESOURCE_HUB = [.58, 13.85, .70]  # unit outer ends at x 0.62
RESOURCE_UNITS = 6
# Figure 4-35: road zone, identical in plan to 2026 (1500/1858/2634/3125/3902, 1561+2090).
# Its dimensions start at the inner face of the road's west wall, x 3.71 on figure 4-5
# (wall 3.51..3.71, red line 3.886).
ROAD_X0 = 3.71
ROAD_NORTH = 15-3.801
ROAD_KERB_Y = ROAD_NORTH+1.561
ROAD_SOUTH = ROAD_KERB_Y+.15
NOTCH_X = (ROAD_X0+3.902, ROAD_X0+3.902+1.148)
# Road crossing cards (figure 4-35): low card on the notch floor, high card past the step.
ROAD_CARDS_Y = ((12.24, 12.83), (13.098, 13.678))
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
# Floor planes of the tunnel cards (card_z_m); the road tunnel's two cards on its ramp have
# none and follow the ramp under the robot, as a horizontal plane would not.
TUNNEL_CARD_PLANES = {'road_tunnel': (None, None, ROAD), 'near_tunnel': (0, 0, 0), 'far_tunnel': (ROAD, ROAD, ROAD)}
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
# Figure 4-9: the robot start zone is an irregular hexagon (outer edge of its 52 mm white
# line): flat sides at x 770 (2385 long) and 4245 (1692 long), points at x 2208, 4045 apart.
START_ZONE = [[2.208, 5.4775], [4.245, 6.654], [4.245, 8.346], [2.208, 9.5225], [.77, 8.6925], [.77, 6.3075]]
# Figure 4-25: fortress, pointy-ended hexagon 2107 across flats, 150 high, 20 degree sides.
# On the field (figure 4-5) its points face along the long axis: vertices at +-x.
FORTRESS_OUTER_R = 2.107/math.sqrt(3)
FORTRESS_TOP_R = 1.131/math.sqrt(3)
# Central highland outline, red half (figures 4-27 at 57 px/m and 4-35 at 100 px/m, both
# matching figure 4-5): the 200 mm fortress-facing band's face spans y 6.631..8.080 at the
# 9180 vertex; the deck's upper-left edge runs from its top end at 55 degrees down to it,
# the lower-left edge at 66.4 degrees to the outpost, where the 150 mm kerb steps round the
# outpost pedestal (vertical at x 10.455..10.605) and then runs back to the deck end at
# -0.667 m/m. The 400 mm rim (x 9.99..10.14) is 2988 long (y 5.99..8.98); the deck end falls
# to the road over 0.555 m (both figures; the text says 12 degrees, the drawings give 10).
BAND_FACE = (9.182, 6.631, 8.080)
UPPER_EDGE_SLOPE = 1.4333   # -dy/dx of the 55 degree edge
LOWER_EDGE_RUN = .437        # dx/dy of the 66.4 degree edge
STRIP_X = (9.99, 10.14)
RIM_Y = (5.99, 8.98)
NOTCH = ((10.455, 10.993), (10.455, 11.695))
END_KERB_RUN = -.667         # dx/dy of the kerb behind the outpost
DECK_END_Y = 12.906
END_SLOPE_RUN = .555


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


def inset_convex(points, d):
    """Convex polygon offset inward by d (counter- or clockwise input)."""
    n = len(points); area = sum(points[i][0]*points[(i+1) % n][1]-points[(i+1) % n][0]*points[i][1] for i in range(n))
    sign = 1 if area > 0 else -1
    lines = []
    for i in range(n):
        (x1, y1), (x2, y2) = points[i], points[(i+1) % n]; L = math.hypot(x2-x1, y2-y1)
        nx, ny = -sign*(y2-y1)/L, sign*(x2-x1)/L  # inward normal
        lines.append(((x1+nx*d, y1+ny*d), (x2-x1, y2-y1)))
    out = []
    for i in range(n):
        (p1, d1), (p2, d2) = lines[i-1], lines[i]
        den = d1[0]*d2[1]-d1[1]*d2[0]; t = ((p2[0]-p1[0])*d2[1]-(p2[1]-p1[1])*d2[0])/den
        out.append([p1[0]+d1[0]*t, p1[1]+d1[1]*t])
    return out


def markings(p):
    """Floor paint of one half (red coordinates; `p` rotates them for blue), measured on the
    module drawings: team lines 30 mm (drawn 36 mm), white lines 40..50 mm (figure 4-9: 52 mm).
    Each entry: team ('red'/'blue') or None for white, points, closed, width."""
    team_lines, white = [], []
    T = TRAPEZOID_X0
    # Trapezoid (figure 4-26): ~65 mm inside the field-edge sides, ~105 mm inside the slope
    # sides; open at the tongue tip, where both lines stop 85 mm short.
    team_lines.append([[TRAPEZOID_TIP_X-.084, 1.036], [9.763, 1.036], [7.668, 4.025], [T+.065, 4.025], [T+.065, .065], [TRAPEZOID_TIP_X-.084, .065]])
    # Road zone (figure 4-35): south edge, west wall, north wall up to the slope's top corner;
    # the kerb's north side with a drop round its west end; the strip east of the road tunnel.
    x0 = ROAD_X0
    team_lines.append([[FAR_TUNNEL_X[0]-.028, 14.945], [x0+.176, 14.945], [x0+.176, 11.29], [x0+3.145, 11.30]])
    team_lines.append([[x0+1.47, 12.95], [x0+1.47, 12.692], [x0+3.837, 12.692]])
    team_lines.append([[ROAD_TUNNEL_X+.584, 13.959], [FAR_TUNNEL_X[0]-.028, 13.959]])
    # Central highland deck edge, 0.36 m inside the kerb's outer face (figure 4-27), broken
    # along the rim and round the outpost.
    team_lines.append([[12.597, 2.39], [10.355, 5.582], [10.355, 6.06]])
    team_lines.append([[10.355, 8.92], [10.355, 9.857], [10.763, 10.79]])
    team_lines.append([[10.75, 11.90], [10.06, 12.906]])
    # Assembly card outline round the red half of the plinth (figures 4-27/4-29: 1230, 1411,
    # 383, 927).
    team_lines.append([[14.392, 6.384], [13.21, 6.043], [12.129, 6.950], [12.129, 7.333], [12.841, 7.926]])
    # High point floor octagon (figure 4-17): 0.385 m chamfers, broken by the east (0.74 m) and south (0.74 m)
    # stair openings.
    hx, hy = HIGH_POINT_CENTER; h, c = 1.021, .636
    team_lines.append([[hx+h, hy-.37], [hx+h, hy-c], [hx+c, hy-h], [hx-c, hy-h], [hx-h, hy-c], [hx-h, hy+c], [hx-c, hy+h], [hx-.372, hy+h]])
    team_lines.append([[hx+.372, hy+h], [hx+c, hy+h], [hx+h, hy+c], [hx+h, hy+.37]])
    # Fortress top (figure 4-25): three hooked brackets on alternate sides of a hexagon of
    # 419 mm apothem: on the red fortress the side facing -y and the two sides facing +y.
    fx, fy = FORTRESS
    for bracket in ([(-.2795, -.354), (-.2419, -.419), (.2419, -.419), (.2795, -.354)],
                    [(-.1669, .419), (-.2419, .419), (-.4838, 0), (-.4463, -.065)],
                    [(.1669, .419), (.2419, .419), (.4838, 0), (.4463, -.065)]):
        team_lines.append([[fx+dx, fy+dy] for dx, dy in bracket])
    out = [dict(team='red', points=pts, closed=False, width=.03) for pts in team_lines]
    # Base stripes (figure 4-9): seven 34 mm lines at 161.5 mm pitch from the side wall to
    # x 1651, three at 200 mm pitch from x 3274 to 4185.
    out += [dict(team='red', points=[[0.0, 7.5+k*.1615], [1.651, 7.5+k*.1615]], closed=False, width=.034) for k in range(-3, 4)]
    out += [dict(team='red', points=[[3.274, 7.5+k*.2], [4.185, 7.5+k*.2]], closed=False, width=.034) for k in (-1, 0, 1)]
    # Start zone (figure 4-9): centre line of the 52 mm outline, its flat sides broken where
    # the stripes pass (y 6.755..8.255 at x 770, 7.099..7.906 at x 4245).
    z = inset_convex(START_ZONE, .026)
    white.append(([[z[5][0], 6.755], z[5], z[0], z[1], [z[1][0], 7.099]], .05))
    white.append(([[z[2][0], 7.906], z[2], z[3], z[4], [z[4][0], 8.255]], .05))
    # Deck (figure 4-27 rows, 57 px/m; figure 4-35 agrees): inner white line of the central card, the outpost card's
    # L and the dash between them.
    white.append(([[12.61, 2.69], [12.61, 3.83], [11.201, 5.856], [11.201, 9.517], [11.83, 10.98]], .045))
    white.append(([[10.68, 12.315], [11.27, 12.31], [11.81, 11.765]], .045))
    white.append(([[10.78, 10.378], [11.35, 10.378]], .045))
    # Highland crossing low card in front of the band's steps (figures 4-5 and 4-8): 2.82 m tall about the centre
    # line, outer side at x 8.348, 45 degree chamfers of 0.226 m on the outer corners, open toward the band.
    white.append(([[9.15, 6.09], [8.574, 6.09], [8.348, 6.316], [8.348, 8.684], [8.574, 8.91], [9.15, 8.91]], .045))
    white.append((SUPPLY_LINE, .04))
    # Fortress outline brackets (figures 4-5 and 4-8): 1.17 m from the centre across the flats, their corners 0.677 m
    # either side, the side points 1.28 m out; the upper brackets end with a 0.14 m tick past the side point, the bottom
    # one with 0.15 m ticks up toward them; 0.15 m pieces along the top flat.
    fx, fy = FORTRESS; A, C, Rs = 1.17, .677, 1.28
    for s_ in (-1, 1):
        white.append(([[fx+s_*(C-.15), fy-A], [fx+s_*C, fy-A], [fx+s_*Rs, fy], [fx+s_*(Rs-.08), fy+.115]], .03))
    white.append(([[fx-C-.075, fy+A-.13], [fx-C, fy+A], [fx+C, fy+A], [fx+C+.075, fy+A-.13]], .03))
    # Dart station: a 0.65 m bracket off its field end (figures 4-5 and 4-8).
    white.append(([[2.217, .52], [2.267, .57], [2.267, 1.12], [2.217, 1.17]], .03))
    # Road crossing cards (figure 4-8, 4-35): 100 mm chamfers, open at the step between them.
    a0, a1 = 7.732, 8.761
    (c0, c1), (c2, c3) = ROAD_CARDS_Y
    white.append(([[a0, c1-.01], [a0, c0+.1], [a0+.1, c0], [a1-.1, c0], [a1, c0+.1], [a1, c1-.01]], .03))
    white.append(([[a0, c2], [a0, c3-.1], [a0+.1, c3], [a1-.1, c3], [a1, c3-.1], [a1, c2]], .03))
    # Road tunnel (figure 4-35 columns, 100 px/m): a dash across its approach on the floor, broken bars down both
    # sides of its ramp card and its road card, and a solid line closing the road card.
    for y in (11.737, 13.773):
        white.append(([[8.931, y], [9.754, y]], .04))
    for xs in (8.905, 9.774):
        for ya, yb in ((12.25, 12.30), (12.34, 12.391), (12.431, 12.541), (13.095, 13.396), (13.436, 13.497), (13.527, 13.577)):
            white.append(([[xs, ya], [xs, yb]], .04))
    # Near and far tunnels: solid bars at both ends of their card area.
    for xs, (ya, yb) in ((13.947, (13.135, 13.829)), (16.003, (13.135, 13.829)), (12.984, (14.10, 14.804)), (15.05, (14.10, 14.804))):
        white.append(([[xs, ya], [xs, yb]], .04))
    out += [dict(team=None, points=pts, closed=False, width=w) for pts, w in white]
    return [dict(m, points=[p([round(x, 4), round(y, 4)]) for x, y in m['points']]) for m in out]


# Crossing-card icons (figure 4-35, 100 px/m): a filled step and a double arrow joined by a diagonal (pointing -x),
# in metres about their centres, field axes (y toward the bottom of figure 4-5).
STEP_ICON = [(-.12, -.0025), (.005, -.0025), (.005, -.0825), (.12, -.0825), (.12, .0825), (-.12, .0825)]
ARROW_ICON = [(-.125, -.0675), (-.075, -.1175), (-.065, -.1025), (.015, -.1025), (.095, .0275), (.125, .0275), (.125, .1025),
              (-.065, .1025), (-.075, .1175), (-.125, .0625), (-.075, .0125), (-.065, .0275), (.014, .0275), (-.02, -.0275),
              (-.065, -.0275), (-.075, -.0175)]


def icons(p):
    """White crossing icons of one half (red coordinates): steps on the road and highland cards, arrows on the
    tunnel cards pointing toward their roof (the road tunnel's both point -x)."""
    out = []
    for c in ((8.25, 12.565), (8.25, 13.33), (8.82, 7.47), (10.70, 7.49)):
        out.append([[c[0]+u, c[1]+v] for u, v in STEP_ICON])
    for c, flip in (((9.34, 12.385), 1), ((9.34, 13.34), 1), ((14.525, 13.475), -1), ((15.385, 13.475), 1),
                    ((13.585, 14.455), -1), ((14.44, 14.455), 1)):
        pts = [[c[0]+flip*u, c[1]+v] for u, v in ARROW_ICON]
        out.append(pts if flip > 0 else pts[::-1])
    return [dict(points=[p([round(x, 4), round(y, 4)]) for x, y in pts]) for pts in out]


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
    terrain, walls, zones, paint, fixtures, icon_list = [], [], [], [], [], []

    def line_wall(identifier, a, b, thickness, height, page, bottom=0, kind='barrier', **shape):
        # `shape` carries visual-only profile hints for the asset build (the engine ignores them).
        length = math.dist(a, b)
        walls.append(dict(id=identifier, x=(a[0]+b[0]-length)/2, y=(a[1]+b[1]-thickness)/2,
                          w=length, h=thickness, rotation=math.atan2(b[1]-a[1], b[0]-a[0]),
                          height=height, bottom=bottom+min((a[1]+b[1])/2, 15-(a[1]+b[1])/2)*math.tan(math.radians(FLOOR_SLOPE_DEG)),
                          kind=kind, source_page=page, **shape))

    def add_zone(identifier, kind, point, radius, owner=None, points=None, group=None, order=None, crossing=None, card_elevation=None):
        value = dict(id=identifier, kind=kind, x=point[0], y=point[1], radius=radius, owner=owner,
                     source='2027 chapter 4 placement + figure 5-23 buff-card outline')
        if points: value['polygon'] = points
        if group: value['group'] = group
        if order is not None: value['order'] = order
        if crossing: value['crossing'] = crossing
        if card_elevation is not None:
            # Explicit floor plane for tunnel cards: a roof is a separate solid surface.
            # Other cards follow their local terrain (including ramps) in the engine.
            value['card_z_m'] = round(card_elevation + min(point[1], 15-point[1])*math.tan(math.radians(FLOOR_SLOPE_DEG)), 9)
        zones.append(value)

    # ---- Central highland (figures 4-27/4-28): 7740 between the rims' inner faces, 10820
    # long, centrally (not mirror) symmetric; see BAND_FACE. Both ends fall onto the road zones.
    bx, by0, by1 = BAND_FACE
    s0, s1 = STRIP_X
    upper_x = lambda y: bx+(by0-y)/UPPER_EDGE_SLOPE
    lower_x = lambda y: bx+(y-by1)*LOWER_EDGE_RUN
    end_x = lambda y: NOTCH[1][0]+(y-NOTCH[1][1])*END_KERB_RUN
    top = DECK_END_Y-END_SLOPE_RUN  # where the red end slope leaves the deck
    half = [[upper_x(15-top), 15-top], [s0, by0-(s0-bx)*UPPER_EDGE_SLOPE], [s0, by1+(s0-bx)/LOWER_EDGE_RUN],
            list(NOTCH[0]), list(NOTCH[1]), [end_x(top), top]]
    half = [[round(x, 4), round(y, 4)] for x, y in half]
    terrain.append(polygon('central_highland', half+list(map(mirrored, half)), DECK, 50))
    for team, f in (('red', list), ('blue', mirrored)):
        # End slope over the whole deck end, from the kerb behind the outpost to the far edge.
        lo = DECK_END_Y
        quad = [[end_x(top), top], [28-upper_x(15-top), top], [28-upper_x(15-lo), lo], [end_x(lo), lo]]
        mid = (quad[2][0]+quad[3][0])/2
        strip = polygon(f'central_{team}_end_slope', [f([round(x, 4), round(y, 4)]) for x, y in quad], DECK, 50)
        strip.update(kind='ramp', ramp_start=f([round(mid, 4), lo]), ramp_end=f([round(mid, 4), round(top, 4)]), base_elevation=ROAD,
                     slope_deg=round(math.degrees(math.atan2(DECK-ROAD, END_SLOPE_RUN)), 3))
        terrain.append(strip)
        # Fortress-facing band (section A-A: 200 mm) up to the strip, and the 400 mm rim:
        # terrain-crossing robots climb two risers, as in 2026.
        band = [[bx, by0], half[1], half[2], [bx, by1]]
        terrain.append(polygon(f'central_{team}_band', list(map(f, band)), BAND, 50))
        rim = [[s0, RIM_Y[0]], [s1, RIM_Y[0]], [s1, RIM_Y[1]], [s0, RIM_Y[1]]]
        terrain.append(polygon(f'central_{team}_rim', list(map(f, rim)), RIM, 50))
        # 150 mm kerbs (beige in figure 4-27) standing on the deck edge, centred 75 mm inside
        # it: the upper edge, the strip beside the rim, the lower edge, round the outpost pedestal
        # and back to the deck end. The end slopes have none: the road tunnel's portal flanks the
        # red one's west edge and the near tunnel's rail closes its far part.
        def edge_wall(name, a, b):
            dx, dy = b[0]-a[0], b[1]-a[1]; length = math.hypot(dx, dy)
            nx_, ny_ = dy/length, -dx/length
            if nx_ < 0: nx_, ny_ = -nx_, -ny_
            line_wall(f'central_{team}_{name}', f([a[0]+nx_*.075, a[1]+ny_*.075]), f([b[0]+nx_*.075, b[1]+ny_*.075]), .15, .15, 50, bottom=DECK)
        edge_wall('kerb_upper', half[0], half[1])
        kc = s0+.075
        line_wall(f'central_{team}_kerb_strip_0', f([kc, half[1][1]+.075]), f([kc, RIM_Y[0]]), .15, .15, 50, bottom=DECK)
        line_wall(f'central_{team}_kerb_strip_1', f([kc, RIM_Y[1]]), f([kc, half[2][1]-.075]), .15, .15, 50, bottom=DECK)
        edge_wall('kerb_lower', half[2], half[3])
        edge_wall('kerb_outpost', half[3], half[4])
        edge_wall('kerb_end', half[4], half[5])
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
        # [1] 23 degree slopes outside the flat top along its 4586 bottom edge and its diagonal,
        # meeting in a mitre; the diagonal slope stops at the line of the tongue's lower edge.
        run = TRAPEZOID/math.tan(math.radians(23))
        a, b = trap[4], trap[3]
        dx, dy = b[0]-a[0], b[1]-a[1]; length = math.hypot(dx, dy)
        n = [-dy/length, dx/length] if -dy/length > 0 else [dy/length, -dx/length]  # outward (+x, +y)
        d = [dx/length, dy/length]
        def on_outer(y):  # point of the diagonal's outer line at height y of the plan
            o = [a[0]+n[0]*run, a[1]+n[1]*run]; t = (y-o[1])/d[1]
            return [o[0]+d[0]*t, y]
        bottom_y = trap[5][1]+run
        mitre = on_outer(bottom_y)
        for name, quad, low, high in (
                ('_trapezoid_23_bottom', [trap[5], a, mitre, [trap[5][0], bottom_y]], [(trap[5][0]+a[0])/2, bottom_y], [(trap[5][0]+a[0])/2, a[1]]),
                ('_trapezoid_23', [a, b, on_outer(b[1]), mitre], [(a[0]+b[0])/2+n[0]*run, (a[1]+b[1])/2+n[1]*run], [(a[0]+b[0])/2, (a[1]+b[1])/2])):
            r = polygon(team+name, [p([round(x, 4), round(y, 4)]) for x, y in quad], TRAPEZOID, 49)
            r.update(kind='ramp', ramp_start=p([round(v, 4) for v in low]), ramp_end=p([round(v, 4) for v in high]), slope_deg=23)
            terrain.append(r)
        # ---- High point (figure 4-17): octagonal floor 800 mm high with a 300 mm parapet,
        # reached by three 200 mm steps (300 mm treads, 1200 mm wide) from the trapezoid.
        hp = HIGH_POINT_CENTER
        sy = HIGH_POINT_STAIR_Y; sx = (hp[0]-.6, hp[0]+.6); tread = HIGH_POINT_TREAD_X
        top, bottom = HIGH_POINT_SOUTH_STEPS[0][0], HIGH_POINT_SOUTH_STEPS[-1][1]
        # Block (plans of figures 4-17 and 4-8): from y 1.45 to 4.82, its north-east corner chamfered toward the
        # ledge, the east stair opening and the recessed south flight cut out, the south-west corner chamfered.
        block = [[.05, 1.45], [2.26, 1.45], [2.71, 1.90], [2.71, sy[0]], [tread[0], sy[0]], [tread[0], sy[1]], [2.71, sy[1]],
                 [2.71, 3.92], [2.633, 4.009], [2.633, bottom], [sx[1], bottom], [sx[1], top], [sx[0], top], [sx[0], bottom],
                 [.40, bottom], [.05, 4.47]]
        terrain.append(polygon(team+'_high_point', list(map(p, block)), HIGH_POINT, 41))
        terrain.append(polygon(team+'_high_point_step_0', list(map(p, [[tread[0], sy[0]], [tread[1], sy[0]], [tread[1], sy[1]], [tread[0], sy[1]]])), .60, 41))
        terrain.append(polygon(team+'_high_point_ledge', list(map(p, HIGH_POINT_LEDGE)), .40, 41))
        for k, (ya, yb, z) in enumerate(HIGH_POINT_SOUTH_STEPS):
            terrain.append(polygon(f'{team}_high_point_south_step_{k}', list(map(p, [[sx[0], ya], [sx[1], ya], [sx[1], yb], [sx[0], yb]])), z, 41))
        # Parapet (300 mm) on the octagon round the floor, open on the east (trapezoid steps)
        # and south (field flight) sides; its centre line is 1.1 m from the floor's centre.
        floor = octagon(hp[0], hp[1], 2.2, .42)
        for i in range(8):
            a, b = floor[i], floor[(i+1) % 8]
            if (a[0] > hp[0]+1.0 and b[0] > hp[0]+1.0) or (a[1] > hp[1]+1.0 and b[1] > hp[1]+1.0):
                continue  # the two 1200 mm stair openings
            line_wall(f'{team}_high_point_parapet_{i}', p(a), p(b), .10, .30, 41, bottom=HIGH_POINT)
        add_zone(team+'_high_point', 'high_point', p(hp), 1.0, team, list(map(p, octagon(hp[0], hp[1], 2.0, .38))))
        # ---- Dart launch station (figure 4-14): scenery and a both-team no-go area.
        line_wall(team+'_dart_station', p([.08, .70]), p([2.20, .70]), 1.10, 1.30, 40)
        fixtures.append(dict(kind='dart_station', team=team, point=p([1.14, .70]), yaw=yaw))
        # ---- Road zone (figure 4-35): 1561 north strip, 150 kerb, 2090 south strip.
        x0r, north, kerb, south = ROAD_X0, ROAD_NORTH, ROAD_KERB_Y, ROAD_SOUTH
        tun = (FAR_TUNNEL_Y-.4-FAR_TUNNEL_WALL, FAR_TUNNEL_Y+.4+FAR_TUNNEL_WALL)
        road = [[x0r, north], [x0r+1.858, north], [x0r+2.634, kerb], [x0r+2.634, south], [ACCESS_TOP_X, south],
                [ACCESS_TOP_X, tun[0]], [FAR_TUNNEL_X[0], tun[0]], [FAR_TUNNEL_X[0], 15], [x0r, 15]]
        terrain.append(polygon(team+'_road', list(map(p, road)), ROAD, 57))
        # The slope falls from the north strip to the notch floor between the diagonals
        # 1858->2634 (200 mm) and 3125->3902 (floor): its low end meets the kerb line where the
        # bumps end. 200 mm over 1.135 m is 10 degrees.
        hi_a, hi_b, lo_a, lo_b = [x0r+1.858, north], [x0r+2.634, kerb], [x0r+3.125, north], [x0r+3.902, kerb]
        ex, ey = hi_b[0]-hi_a[0], hi_b[1]-hi_a[1]; length = math.hypot(ex, ey)
        normal = [ey/length, -ex/length]  # toward the low diagonal
        width = (lo_a[0]-hi_a[0])*normal[0]
        lo_mid = [(lo_a[0]+lo_b[0])/2, (lo_a[1]+lo_b[1])/2]
        hi_foot = [lo_mid[0]-normal[0]*width, lo_mid[1]-normal[1]*width]
        slope = polygon(team+'_road_slope', [p([round(x, 4), round(y, 4)]) for x, y in (hi_a, lo_a, lo_b, hi_b)], ROAD, 57)
        slope.update(kind='ramp', ramp_start=p([round(v, 4) for v in lo_mid]), ramp_end=p([round(v, 4) for v in hi_foot]),
                     slope_deg=round(math.degrees(math.atan2(ROAD, width)), 3))
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
        # Low kerbs: the trapezoid's north edge, the road's west wall (x 3.51..3.71) and north
        # wall (y 11.06..11.21 up to x 5.60, figure 4-35), which ends in a tapered guard block
        # standing on the floor beside the slope's top end (x 5.60..6.84, out to y 10.77).
        line_wall(team+'_kerb_0', p([TRAPEZOID_X0, .05]), p([TRAPEZOID_TIP_X-.05, .05]), .15, .6, 49)
        line_wall(team+'_kerb_1', p([x0r-.10, north-.14]), p([x0r-.10, 15]), .20, .35, 57)
        line_wall(team+'_kerb_2', p([x0r-.20, north-.065]), p([x0r+1.886, north-.065]), .15, .35, 57)
        guard = [[x0r+1.886, north-.14], [x0r+2.653, north-.427], [x0r+3.044, north-.427], [x0r+3.125, north-.286],
                 [x0r+3.125, north-.065], [x0r+3.004, north-.005], [x0r+1.886, north+.01]]
        fixtures.append(dict(kind='road_guard', team=team, polygon=[p([round(x, 4), round(y, 4)]) for x, y in guard], top_m=.35))
        line_wall(team+'_road_guard_end', p([x0r+2.653, north-.2135]), p([x0r+3.125, north-.2135]), .427, .35, 57)
        line_wall(team+'_road_guard_taper', p([x0r+1.886, north-.065]), p([x0r+2.653, north-.2135]), .20, .35, 57)
        # ---- Fortress (figure 4-25) and base pedestal (figure 4-10).
        fort = p(FORTRESS)
        ft = polygon(team+'_fortress', hexagon(*fort, FORTRESS_OUTER_R), .15, 48, edge_ramp_m=.15/math.tan(math.radians(20)))
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
        add_zone(team+'_base', 'base', base, 1.8, team, list(map(p, START_ZONE)))
        add_zone(team+'_fortress', 'fortress', fort, .56, team, hexagon(*fort, FORTRESS_TOP_R))
        add_zone(team+'_supply', 'supply', p([1.4, 13.0]), .9, team, list(map(p, SUPPLY_AREA)))
        add_zone(team+'_resource', 'resource', p([RESOURCE_HUB[0]+.62, RESOURCE_HUB[1]]), .55, team)
        add_zone(team+'_workbench', 'workbench', fixtures[-1]['dock_point'], .45, team)
        # Figure 5-23 [9]/[12] inside the deck's red and white lines (figure 4-27): the outpost card
        # below the white dash at y 10.395, the central card in the strip above it.
        outpost_card = [[10.59, 10.395], [11.553, 10.395], [11.82, 11.01], [11.81, 11.765], [11.27, 12.31], [10.47, 12.315], [10.62, 11.71], [10.62, 10.99]]
        add_zone(team+'_outpost', 'outpost', op, .85, team, list(map(p, outpost_card)))
        central_card = [[12.392, 2.66], [12.63, 2.66], [12.62, 3.842], [11.19, 5.867], [11.19, 9.569], [11.553, 10.395], [10.59, 10.395], [10.355, 9.857], [10.355, 5.582]]
        # The central highland buff card doubles as the highland crossing's high card.
        add_zone(team+'_central', 'central', p([10.8, 7.5]), .55, team, list(map(p, central_card)),
                 group=team+'_highland', order=1, crossing='highland')
        add_zone(team+'_highland_low', 'highland', p([8.765, 7.5]), .4, team,
                 list(map(p, [[8.35, 6.08], [9.18, 6.08], [9.18, 8.92], [8.35, 8.92]])), group=team+'_highland', order=0)
        side = 1 if not flip else -1
        add_zone(team+'_assembly', 'assembly', [14-side*.94*nx, 7.5-side*.94*ny], .65, team)
        # Road crossing (figure 4-35): the low card on the notch floor and the high card on the
        # road beyond the step, inside their white outlines (x 7.742..8.776, y 12.255..13.678).
        for order, (ya, yb) in enumerate(ROAD_CARDS_Y):
            card = [[x0r+4.032, ya], [x0r+5.066, ya], [x0r+5.066, yb], [x0r+4.032, yb]]
            add_zone(team+f'_road_{order}', 'road', p([x0r+4.549, (ya+yb)/2]), .35, None, list(map(p, card)), group=team+'_road', order=order)
        # Tunnels: an end card, a card under the roof and the far end card (order 0, 1, 2).
        for name, cards in (('road_tunnel', [[ROAD_TUNNEL_X, y] for y in ROAD_TUNNEL_CARD_Y]),
                            ('near_tunnel', [[14.36, mid_y], [NEAR_TUNNEL_ROOF_X, mid_y], [15.50, mid_y]]),
                            ('far_tunnel', [[13.40, FAR_TUNNEL_Y], [14.0, FAR_TUNNEL_Y], [14.60, FAR_TUNNEL_Y]])):
            for order, pt in enumerate(cards):
                add_zone(team+f'_{name}_{order}', 'tunnel', p(pt), .30 if order != 1 else .17,
                         group=team+'_'+name, order=order, card_elevation=TUNNEL_CARD_PLANES[name][order])
        paint.extend(dict(m, team=team if m['team'] else None) for m in markings(p))
        icon_list.extend(icons(p))

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
                                 ('supply', [[0, 11.83], [3.51, 15]], team),
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
                field_geometry=dict(fixtures=fixtures, paint=paint, icons=icon_list, source_pages=[29, 31, 32, 35, 36, 37, 41, 44, 45, 46, 48, 49, 50, 51, 52, 53, 54, 56, 57, 58, 59, 102, 133],
                                    dimension_note='Labelled 2027 dimensions are normative; unlabelled joints and heights are plan/render reconstructions.'),
                navigation=dict(nodes=nodes))


if __name__ == '__main__':
    import json
    arena = make_arena()
    print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in arena.items() if k in ('terrain', 'obstacles', 'zones', 'forbidden')}))
