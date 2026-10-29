"""Spend the public, per-posture enhanced budget on useful close engagements."""
_sentry_decide=decide


def decide(robot,ctx):
    fields=_sentry_decide(robot,ctx)
    if robot['role']!='sentry' or not robot['alive'] or robot.get('weak') or robot.get('tipped'):
        return fields
    if ctx.time<(robot.get('posture_ready_at') or 0):return fields
    spent=robot.get('posture_enhanced_time',(0.,0.,0.))[0]
    enemies=[e for e in ctx.obs['enemies'] if e['alive'] and not e.get('invulnerable')
        and e.get('targetable',True) and distance(e,(robot['x'],robot['y']))<6.]
    friends=sum(r['alive'] and not r.get('weak') and r['role']!='aerial'
        and distance(r,(robot['x'],robot['y']))<5. for r in ctx.obs['robots'])
    continuing=robot.get('posture')=='attack' and robot.get('posture_enhanced') and robot['hp']>robot['max_hp']*.4
    start=robot['hp']>robot['max_hp']*.5 and robot['ammo']>=80 and len(enemies)<=max(1,friends+1)
    if ('aim' in fields and 'pitch' in fields) and robot['ammo']>0 and enemies and spent<14.5 and (start or continuing):
        fields.update(posture='attack',posture_enhanced=True)
    return fields
