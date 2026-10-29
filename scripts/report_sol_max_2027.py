"""Audit a frozen Sol Max acceptance run without pooling different test tiers."""
import argparse
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path
import statistics

ROOT=Path(__file__).resolve().parents[1]


def summarize(rows,performance=True):
    valid=[r for r in rows if r['valid']]
    margins=sorted(r['candidate']['control']-r['opponent_final']['control'] for r in valid)
    result={'games':len(rows),'valid_games':len(valid),'invalid_games':len(rows)-len(valid),
        'policy_errors':sum(r['policy_errors'] for r in rows),'invalid_actions':sum(len(r.get('action_errors',[])) for r in rows),
        'decision_ms':{'max':max((r['decision_ms']['max'] for r in rows),default=0),
            'p99_max':max((r['decision_ms']['p99'] for r in rows),default=0)}}
    if performance:
        result.update({k:sum(r['outcome']==v for r in valid) for k,v in [('wins','win'),('draws','draw'),('losses','loss')]})
        result['control_margin']={'min':min(margins,default=0),'median':statistics.median(margins) if margins else 0,
            'p10':margins[max(0,(len(margins)-1)//10)] if margins else 0,'mean':statistics.mean(margins) if margins else 0}
    else:
        result['winner_colors']=dict(Counter(r['side'] if r['outcome']=='win' else ('blue' if r['side']=='red' else 'red') if r['outcome']=='loss' else 'draw' for r in valid))
    return result


def compact(r):
    keys=('opponent','seed','side','outcome','time','reason','candidate','opponent_final','policy_errors','action_errors',
        'valid','diagnostics','activity','digest','lineup','actual_lineups','native_hardware','versions','agents',
        'engine_hash','rules_hash','sdk_hash','decision_ms','wall_seconds','replay_recording')
    row={k:r[k] for k in keys if k in r}
    row['control_timeline']=[{'time':t['time'],'control':{team:v['control'] for team,v in t['teams'].items()},
        'positions':{name:{k:v[k] for k in ('controller','control','active')} for name,v in t['positions'].items()}}
        for t in r.get('timeline',[])]
    return row


def audit(plan_path):
    plan_path=Path(plan_path);plan=json.loads(plan_path.read_text());base=plan_path.parent
    failures=[];groups=defaultdict(list);runtimes={};evidence={}
    for name,expected in plan['frozen_artifact_sha256'].items():
        if hashlib.sha256((Path(plan['candidate'])/name).read_bytes()).hexdigest()!=expected:
            failures.append('Frozen artifact changed: '+name)
    for folder,artifact in plan.get('frozen_submissions',{}).items():
        for name,expected in artifact['files'].items():
            if hashlib.sha256((Path(folder)/name).read_bytes()).hexdigest()!=expected:
                failures.append('Frozen opponent changed: '+folder+'/'+name)
    if plan.get('evaluation_host_sha256') and hashlib.sha256((ROOT/'scripts/evaluate_sol_max_2027.py').read_bytes()).hexdigest()!=plan['evaluation_host_sha256']:
        failures.append('Evaluation host changed after registration')
    for runtime,phases in plan['phases'].items():
        by_phase={};runtime_rows=[]
        info=plan['runtimes'][runtime]
        if hashlib.sha256(Path(info['binary']).read_bytes()).hexdigest()!=info['binary_sha256']:
            failures.append('Runtime binary changed: '+runtime)
        if hashlib.sha256((Path(info['root'])/'rmuc_arena/sdk.py').read_bytes()).hexdigest()!=info['sdk_sha256']:
            failures.append('Runtime SDK changed: '+runtime)
        for name,expected in info['configuration_sha256'].items():
            if hashlib.sha256((Path(info['root'])/'config'/name).read_bytes()).hexdigest()!=expected:
                failures.append('Runtime configuration changed: '+runtime+'/'+name)
        for phase in phases:
            file=base/(phase['name']+'-'+runtime+'.json')
            if not file.exists():failures.append('Missing '+file.name);continue
            data=json.loads(file.read_text());rows=data['matches'];label=phase['name']
            if data.get('evaluation_host_sha256')!=plan.get('evaluation_host_sha256'):
                failures.append('Recorded evaluation host mismatch: '+label+'/'+runtime)
            if data.get('duration')!=420:
                failures.append('Recorded duration mismatch: '+label+'/'+runtime)
            wanted=len(phase['opponents'])*len(phase['seeds'])*len(phase.get('sides',['red','blue']))
            if len(rows)!=wanted:failures.append(f'Incomplete {label}/{runtime}: {len(rows)}/{wanted}')
            manifest=json.loads((Path(phase.get('candidate',plan['candidate']))/'manifest.json').read_text())
            expected_keys={(Path(opponent).name+'-'+json.loads((Path(opponent)/'manifest.json').read_text())['version'],seed,side)
                           for opponent in phase['opponents'] for seed in phase['seeds'] for side in phase.get('sides',['red','blue'])}
            actual_keys={(r['opponent'],r['seed'],r['side']) for r in rows}
            if actual_keys!=expected_keys or len(rows)!=len(actual_keys):failures.append('Missing or duplicate match identities: '+label+'/'+runtime)
            for row in rows:
                if row['versions'][row['side']]!=manifest['version']:failures.append('Mixed candidate versions')
                other='blue' if row['side']=='red' else 'red'
                if not row['opponent'].endswith('-'+row['versions'][other]):failures.append('Opponent version mismatch')
                if row['sdk_hash']!=info['sdk_sha256'] or row['rules_hash']!=info['rules_sha256']:failures.append('Runtime fingerprint mismatch')
                if info.get('engine_hash') and row['engine_hash']!=info['engine_hash']:failures.append('Engine fingerprint mismatch')
                if bool(row.get('native_hardware'))!=bool(phase.get('native')):failures.append('Hardware tier mismatch')
                if row['time']>420. or row['reason'] not in ('timeout','base_destroyed'):failures.append('Unfinished or nonstandard match')
            if not phase.get('diagnostic') and not all(r['valid'] for r in rows):failures.append('Invalid attempts in '+label+'/'+runtime)
            if phase.get('nonwins_max') is not None and sum(r['valid'] and r['outcome']!='win' for r in rows)>phase['nonwins_max']:
                failures.append('Phase performance gate failed: '+label+'/'+runtime)
            if any(r['reason']=='timeout' and abs(r['time']-420.)>1e-6 for r in rows):
                failures.append('Short timeout match in '+label+'/'+runtime)
            groups[label]+=rows;runtime_rows+=rows if label!='qualification' else []
            by_phase[label]=summarize(rows,label!='mirror')
            evidence[label+'/'+runtime]=[compact(r) for r in rows]
        by_phase['sdk_hash']=info['sdk_sha256'];by_phase['rules_hash']=info['rules_sha256']
        by_phase['engine_hashes']=sorted({r['engine_hash'] for r in runtime_rows})
        if len(by_phase['engine_hashes'])>1:failures.append('Mixed engines within '+runtime)
        runtimes[runtime]=by_phase
    stats={name:summarize(rows,name!='mirror') for name,rows in groups.items()}
    gates=plan['gates']
    for name,maximum in [('regression',0),('reference',0),('native',gates['native_nonwins_max']),('adversarial',gates['adversarial_nonwins_max'])]:
        s=stats.get(name,{})
        if maximum is not None and s.get('losses',0)+s.get('draws',0)>maximum:failures.append(name+' win-rate gate failed')
    reference=stats.get('reference',{}).get('control_margin',{})
    if reference.get('median',0)<gates['reference_median_control_margin_min']:failures.append('Reference median margin too small')
    if reference.get('p10',0)<gates['reference_p10_control_margin_min']:failures.append('Reference lower-tail margin too small')
    diagnostics={phase['name'] for phases in plan['phases'].values() for phase in phases if phase.get('diagnostic')}
    for name in diagnostics:
        if name in stats:stats[name]['scope']='Supplemental diagnostic; excluded from team-match performance gates'
    candidate_rows=[r for name,rows in groups.items() if name!='qualification' and name not in diagnostics for r in rows]
    if any(r['policy_errors'] or r.get('action_errors') for r in candidate_rows):failures.append('Candidate stability gate failed')
    qualification=defaultdict(list)
    for row in groups.get('qualification',[]):qualification[row['opponent']].append(row)
    qualification={name:{'games':len(rows),'opponent_wins':sum(r['outcome']=='loss' and r['valid'] for r in rows),
        'baseline_wins':sum(r['outcome']=='win' and r['valid'] for r in rows)} for name,rows in qualification.items()}
    if 'qualification_opponent_wins_min' in gates:
        if sum(r['opponent_wins'] for r in qualification.values())<gates['qualification_opponent_wins_min']:
            failures.append('Opponent pool did not beat the published baseline often enough')
        if sum(r['opponent_wins']>=5 for r in qualification.values())<gates['qualified_variants_min']:
            failures.append('Too few opponent variants qualified against the baseline')
    qualified_names=sorted(name for name,row in qualification.items() if row['opponent_wins']>=5)
    qualified_rows=[r for r in groups.get('adversarial',[]) if r['opponent'] in qualified_names]
    qualified_results={'criterion':'At least 5 wins in 8 qualification games against the published baseline',
        'opponents':qualified_names,'candidate_results':summarize(qualified_rows),
        'by_opponent':{name:summarize([r for r in qualified_rows if r['opponent']==name]) for name in qualified_names}}
    return {'format':'sol-max-2027-acceptance-v2','candidate_version':plan['candidate_version'],'passed':not failures,
        'failures':sorted(set(failures)),'protocol':{k:plan[k] for k in ('duration_s','decision_timeout_ms','reference_seeds','stress_seeds','gates','expected_games','host_equivalence','notes')},
        'jobs_per_runtime':plan.get('jobs_per_runtime',1),
        'reused_qualification':plan.get('reused_qualification',{}),
        'qualification_seeds':plan.get('qualification_seeds',plan['stress_seeds']),
        'expected_fresh_games':plan.get('expected_fresh_games',plan['expected_games']),
        'artifact_sha256':plan['frozen_artifact_sha256'],'by_runtime':runtimes,'by_tier':stats,
        'opponent_qualification':qualification,'qualified_adversarial':qualified_results,'matches':evidence}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('plan',type=Path);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--allow-incomplete',action='store_true');a=p.parse_args();result=audit(a.plan)
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('candidate_version','passed','failures','by_tier')},ensure_ascii=False))
    if not result['passed'] and not a.allow_incomplete:raise SystemExit(1)

if __name__=='__main__':main()
