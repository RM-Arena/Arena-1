"""Build the documentation's editable SVG schematics (standard library only).

Run after changing the diagrams or 2027 layout; --check detects stale SVG files.
These are learning aids, not screenshots, performance measurements or path plans.
"""
import argparse
from html import escape
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MEDIA = ROOT / 'docs/media'
RULES = json.loads((ROOT / 'config/rules.json').read_text(encoding='utf-8'))
GOLD, RED, BLUE, INK, MUTED = '#e8c478', '#fb8b94', '#7cc4ff', '#eef3f8', '#b1c0ce'


def text(x, y, value, size=22, color=INK, anchor='start', weight=400):
    return f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" text-anchor="{anchor}" font-weight="{weight}">{escape(str(value))}</text>'


def box(x, y, width, height, stroke='#435568', fill='#182430', radius=12):
    return f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="2"/>'


def line(x1, y1, x2, y2, color=MUTED, arrow=False, dashed=False):
    return f'<path d="M{x1} {y1} L{x2} {y2}" fill="none" stroke="{color}" stroke-width="2"'+(' marker-end="url(#arrow)"' if arrow else '')+(' stroke-dasharray="6 5"' if dashed else '')+'/>'


def svg(title, description, height, elements, width=880):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
<title id="title">{escape(title)}</title><desc id="desc">{escape(description)}</desc>
<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10" fill="{MUTED}"/></marker></defs>
<rect width="{width}" height="{height}" rx="16" fill="#101923"/>
<g font-family="'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',sans-serif">{''.join(elements)}</g></svg>
'''


def basics():
    parts = [text(36, 49, '看懂比赛：行动、资源、目标', 28, GOLD, weight=600)]
    rows = [
        ('01', '机器人在做什么？', '移动、瞄准、射击、搬运与配合', '先看路线与分工，再看是否打中。'),
        ('02', '为什么不能一直进攻？', '血量、弹药、金币、热量与能量有限', '需要补给、降温，也要保护执行任务的队友。'),
        ('03', '这些行动为谁创造优势？', '保护基地、争夺控制点、积累控制度', '2027 到时先比控制度；击毁基地可提前结束。'),
    ]
    for i, (number, heading, body, note) in enumerate(rows):
        y = 78 + i * 126
        parts += [box(30, y, 820, 112), text(50, y+44, number, 28, GOLD, weight=600),
                  text(120, y+35, heading, 24, weight=600), text(120, y+67, body, 22), text(120, y+96, note, 19, MUTED)]
    parts += [text(36, 493, '一局 420 秒（7 分钟） · 两个赛季的到时判据不同', 22, MUTED)]
    return svg('比赛的行动、资源与目标', '三个层次共同影响战术：机器人行动受资源约束，最终服务于基地保护与场上目标。', 525, parts)


def control():
    rule = RULES['rulebook_2027']['control']
    parts = [text(36, 48, '2027：控制点与控制度', 28, GOLD, weight=600),
             text(36, 84, '每个控制点关联两处增益卡；控制状态不等于是否有人站着。', 21, MUTED)]
    for x, team, color in ((30, '红方', RED), (455, '蓝方', BLUE)):
        parts += [text(x+18, 127, team, 24, color, weight=600)]
        for y, name, cards in ((146, '前哨控制点', '前哨卡 + 中央高地卡'), (270, '基地控制点', '基地卡 + 堡垒卡')):
            parts += [box(x, y, 395, 100, color), text(x+20, y+37, team+name, 23, color, weight=600), text(x+20, y+75, cards, 21)]
    parts += [box(30, 397, 820, 106, '#756447'), text(52, 434, f'同时控制双方前哨 → 每秒 +{rule["outpost_pair_rate_per_s"]}', 24, GOLD, weight=600),
              text(52, 474, f'同时控制双方基地 → 每秒 +{rule["base_pair_rate_per_s"]}', 24, GOLD, weight=600),
              text(36, 545, '占领示例：从对方完全控制的前哨控制点开始', 22, weight=600)]
    steps = [(30, '对方完全控制', '我方独占有效卡片'), (320, '我方临时控制', '持续驻守可维持'), (610, '对方完全控制', '临时方离开后返回')]
    for x, title, detail in steps:
        parts += [box(x, 580, 240, 90), text(x+120, 616, title, 22, anchor='middle', weight=600), text(x+120, 650, detail, 18, MUTED, 'middle')]
    parts += [line(275, 623, 313, 623, arrow=True), text(291, 571, f'{rule["capture_s"]} 秒', 18, MUTED, 'middle'),
              line(565, 623, 603, 623, arrow=True), text(584, 571, f'离开 {rule["release_s"]} 秒', 18, MUTED, 'middle'),
              text(36, 711, '击毁前哨还会改变控制状态并可能触发重建，完整条件见正文。', 19, MUTED)]
    return svg('2027 四个控制点、控制度与临时控制示例', '红蓝双方各有前哨和基地控制点。前哨点由前哨卡及高地卡组成，基地点由基地卡及堡垒卡组成。同时控制两方同类点才累计控制度。', 743, parts)


def workflow():
    parts = [text(36, 49, '从战术想法到一份可参赛的程序', 28, GOLD, weight=600),
             text(36, 99, '开发阶段：人或 Agent 阅读、写代码、做实验', 22, GOLD)]
    cards = [(30, '1  创建任务', '先选赛季、模式、阵容', '领取规则与任务目录'),
             (320, '2  开发与练习', '修改 Python + 战术卡', '检查错误、结果与回放'),
             (610, '3  成功提交', '在截止前保存版本', '只保存文件不等于提交')]
    for x, title, a, b in cards:
        parts += [box(x, 128, 240, 139), text(x+18, 164, title, 23, weight=600), text(x+18, 206, a, 18), text(x+18, 239, b, 18, MUTED)]
    parts += [line(277, 198, 313, 198, arrow=True), line(567, 198, 603, 198, arrow=True),
              text(36, 322, '比赛阶段：运行提交的代码，不逐帧调用语言模型', 22, GOLD),
              box(100, 354, 295, 132), box(485, 354, 295, 132),
              text(122, 394, '4  选策略开始对战', 23, weight=600), text(122, 432, '程序每 0.1 秒读取观察', 19), text(122, 463, '引擎执行动作并裁定规则', 19, MUTED),
              text(507, 394, '5  看结果与回放', 23, weight=600), text(507, 432, '找出丢点、缺弹或卡路原因', 19), text(507, 463, '提出下一次明确的改进', 19, MUTED),
              line(404, 420, 476, 420, arrow=True),
              f'<path d="M730 275 V284 H20 V420 H90" fill="none" stroke="{MUTED}" stroke-width="2" marker-end="url(#arrow)"/>',
              text(36, 546, '再次迭代：改一个问题 → 相同条件对照 → 提交新版本', 22, MUTED)]
    return svg('策略从开发到比赛的工作流', '创建任务后开发、练习、提交，再选择固定版本对战，复盘后继续迭代。开发计时和比赛内时间是两个时钟。', 580, parts)


def card_guide():
    parts = [text(36, 49, '怎样阅读一张战术卡', 28, GOLD, weight=600),
             text(36, 86, '下方为内容示意，不是策略性能测评或界面截图。', 20, MUTED)]
    rows = [('01', '身份与打法', '谁开发、控制哪种机器人、主打进攻还是防守'),
            ('02', '风格与阶段', '雷达图说明侧重；时间线说明开局、中段与终局'),
            ('03', '地图与决策', '到哪里、走哪条路线、什么条件触发撤退或换目标'),
            ('04', '优点与局限', '已实现的能力、已知短板；结合真实回放验证')]
    for i, (number, heading, detail) in enumerate(rows):
        y = 112 + i * 98
        parts += [box(30, y, 820, 82), text(50, y+49, number, 26, GOLD), text(117, y+32, heading, 23, weight=600), text(117, y+64, detail, 20, MUTED)]
    parts += [text(36, 553, '说明由作者提供；读懂意图之后，仍要看实际行为和对局结果。', 21, MUTED)]
    return svg('战术卡阅读指南', '战术卡包含身份、风格、阶段、地图路线、关键决策与已知局限。文字描述不等于实测胜率。', 587, parts)


def field():
    arena = RULES['maps']['rmuc2027']
    scale, left, top = 30, 50, 152
    def point(x, y):
        return left+x*scale, top+y*scale
    def marker(x, y, name, color, dx=0, dy=-19, anchor='middle', radius=7):
        px, py = point(x,y)
        return [f'<circle cx="{px:.2f}" cy="{py:.2f}" r="{radius}" fill="{color}" stroke="#101923" stroke-width="2"/>', text(round(px+dx,2), round(py+dy,2), name, 18, color, anchor, 600)]
    parts = [text(36, 49, '2027 场地：先记住这些地点', 28, GOLD, weight=600),
             text(36, 84, '俯视示意 · 28 × 15 m · 红左蓝右，y 轴向下', 21, MUTED),
             text(50, 132, '红方半场', 21, RED), text(890, 132, '蓝方半场', 21, BLUE, 'end'),
             box(left, top, 840, 450, '#647386', '#14202a', 0)]
    for x in range(2,28,2):
        parts += [line(*point(x,0), *point(x,15), '#273746')]
    for y in range(2,15,2):
        parts += [line(*point(0,y), *point(28,y), '#273746')]
    central = next(t for t in arena['terrain'] if t['id']=='central_highland')
    polygon = ' '.join(f'{point(x,y)[0]:.2f},{point(x,y)[1]:.2f}' for x,y in central['polygon'])
    parts += [f'<polygon points="{polygon}" fill="#344654" stroke="#718697" stroke-width="2"/>']
    zones = {z['id']: z for z in arena['zones']}
    for team, color in (('red',RED),('blue',BLUE)):
        for suffix, label in (('supply','补给 / 取件 / 工作台'),('high_point','制高点'),('fortress','堡垒卡')):
            zone = zones[f'{team}_{suffix}']
            x,y = zone['x'],zone['y']
            if suffix=='supply':
                # Move the long label into clear space; the dot keeps its actual position.
                parts += marker(x,y,label,color,dx=10 if team=='red' else -10,dy=30 if team=='red' else -20,anchor='start' if team=='red' else 'end')
            elif suffix=='high_point':
                parts += marker(x,y,label,color,dx=12 if team=='red' else -12,dy=-16,anchor='start' if team=='red' else 'end')
            else:
                parts += marker(x,y,label,color,dy=34)
        bx,by = arena['bases'][team]
        parts += marker(bx,by,('红方' if team=='red' else '蓝方')+'基地',color,dy=-24,radius=11)
        ox,oy = arena['outposts'][team]
        parts += marker(ox,oy,('红方' if team=='red' else '蓝方')+'前哨',color,dy=29 if team=='red' else -19,radius=10)
        zone = zones[f'{team}_central']
        parts += marker(zone['x'],zone['y'],'高地卡',color,dy=-24)
    parts += marker(14,7.5,'能量机关',GOLD,dy=-35,radius=9)
    parts += [text(470, 448, '中央装配区', 18, INK, 'middle'), text(470, 473, '高处为机库平台', 17, MUTED, 'middle'),
              text(36, 644, '圆点依据 maps.rmuc2027 的地点坐标；中央高地轮廓取自场地配置。', 19, MUTED),
              text(36, 677, '省略公路、隧道、墙体、坡道细节与精确卡片边界，不用于规划通行路线。', 19, MUTED)]
    return svg('2027 场地地点俯视示意', '红方在左，蓝方在右。标出双方基地、堡垒、前哨、高地卡、补给区、制高点与中央装配区。坐标取自仓库，未绘制所有障碍。', 710, parts, width=940)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    diagrams = {'match-basics.svg': basics(), 'control-2027.svg': control(),
                'strategy-workflow.svg': workflow(), 'strategy-card-guide.svg': card_guide(),
                'field-2027-guide.svg': field()}
    stale = []
    for name, content in diagrams.items():
        target = MEDIA / name
        if not target.exists() or target.read_text(encoding='utf-8') != content:
            stale.append(name)
            if not args.check:
                target.write_text(content, encoding='utf-8')
    if args.check and stale:
        raise SystemExit('Stale documentation diagrams: '+', '.join(stale))
    print(('Updated: '+', '.join(stale)) if stale else 'Documentation diagrams are current')


if __name__ == '__main__':
    main()
