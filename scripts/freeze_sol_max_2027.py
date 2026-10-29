"""Freeze a candidate, opponents and a multi-runtime acceptance plan.

Runtime packages must have been independently copied into runtime_plan first.
The plan records every input before its new reference and stress seeds run.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
FILES=('strategy.py','manifest.json','profile.json','showcase.json')


def hashes(folder):
    return {name:hashlib.sha256((folder/name).read_bytes()).hexdigest() for name in FILES}


def summary(rows):
    result={name:sum(r['valid'] and r['outcome']==name for r in rows) for name in ('win','draw','loss')}
    result.update(valid_games=sum(r['valid'] for r in rows),invalid_games=sum(not r['valid'] for r in rows),
                  policy_errors=sum(r['policy_errors'] for r in rows))
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate',type=Path,default=ROOT/'examples/gpt61_sol_max_2027')
    parser.add_argument('--runtime-plan',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--stress-seeds',type=int,nargs=2,required=True)
    parser.add_argument('--reference-seeds',type=int,nargs='+',required=True)
    parser.add_argument('--jobs-per-runtime',type=int,choices=(1,2),default=1)
    parser.add_argument('--elite-plan',type=Path,help='Reuse qualified opponent snapshots and baseline-only results')
    parser.add_argument('--pool-plan',type=Path,help='Keep an existing opponent league fixed for a new candidate')
    parser.add_argument('--fresh-qualification',action='store_true',help='Rerun every baseline qualification after a host change')
    parser.add_argument('--expanded-regressions',action='store_true',help='Cover both known tactical seeds on both sides')
    from rmuc_arena.catalog import resolve_strategy
    a=parser.parse_args();out=a.output.resolve()
    if out.exists():raise ValueError('Acceptance snapshots are immutable: '+str(out))
    out.mkdir(parents=True)
    if a.pool_plan:
        plan=json.loads(a.pool_plan.read_text());old_candidate=plan['candidate']
        host=hashlib.sha256((ROOT/'scripts/evaluate_sol_max_2027.py').read_bytes()).hexdigest()
        if host!=plan['evaluation_host_sha256'] and not a.fresh_qualification:
            raise ValueError('Evaluation host differs; rerun qualification with --fresh-qualification')
        for folder,artifact in plan['frozen_submissions'].items():
            if hashes(Path(folder))!=artifact['files']:raise ValueError('Frozen league input changed: '+folder)
        candidate=out/'candidate';shutil.copytree(a.candidate,candidate)
        manifest=json.loads((candidate/'manifest.json').read_text())
        plan.update(candidate=str(candidate),candidate_version=manifest['version'],
            stress_seeds=a.stress_seeds,reference_seeds=a.reference_seeds,
            frozen_artifact_sha256=hashes(candidate),jobs_per_runtime=a.jobs_per_runtime,
            evaluation_host_sha256=host)
        plan['frozen_submissions'][str(candidate)]={'version':manifest['version'],'files':hashes(candidate)}
        reused={}
        for runtime,phases in plan['phases'].items():
            for phase in phases:
                if phase['name'] in ('adversarial','mirror','native'):phase['seeds']=a.stress_seeds
                if phase['name']=='reference':phase['seeds']=a.reference_seeds
                if a.expanded_regressions and phase['name'] in ('split_regression','raid_regression'):
                    phase['seeds']=[12613,12821]
                    phase.pop('sides',None)
                phase['opponents']=[str(candidate) if path==old_candidate else path for path in phase['opponents']]
            file=a.pool_plan.parent/('qualification-'+runtime+'.json')
            if a.fresh_qualification or not file.exists():continue
            data=json.loads(file.read_text())
            phase=next(p for p in phases if p['name']=='qualification')
            baseline_version=json.loads((Path(phase['candidate'])/'manifest.json').read_text())['version']
            if data['runtime']!=plan['runtimes'][runtime]['root'] or any(not r['valid'] or r['versions'][r['side']]!=baseline_version for r in data['matches']):
                raise ValueError('Only valid identical-baseline qualification records can be reused')
            (out/file.name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
            reused[runtime]={'games':len(data['matches']),'source_sha256':hashlib.sha256(file.read_bytes()).hexdigest(),
                'opponent_wins':sum(r['outcome']=='loss' for r in data['matches'])}
        expected=Counter()
        for phases in plan['phases'].values():
            for phase in phases:
                expected[phase['name']]+=len(phase['opponents'])*len(phase['seeds'])*len(phase.get('sides',['red','blue']))
        plan['expected_games']=dict(expected)
        plan['reused_qualification']=reused
        plan['expected_fresh_games']=dict(plan['expected_games'])
        plan['expected_fresh_games']['qualification']-=sum(v['games'] for v in reused.values())
        plan['notes'].append('Opponent scripts are retained unchanged from an earlier frozen league; candidate results are always new.')
        if a.fresh_qualification:
            plan['notes'].append('All qualification matches are rerun on the current evaluation host; no baseline results are reused.')
        (out/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
        print(out/'plan.json','fresh games',sum(plan['expected_fresh_games'].values()))
        return
    plan=json.loads(a.runtime_plan.read_text())
    candidate=out/'candidate';shutil.copytree(a.candidate,candidate)
    opponents=out/'opponents';opponents.mkdir()
    for name in ('deepseek_flash_2027_anchor','dsv41_1017_pair','step5_2027_echo'):
        shutil.copytree(resolve_strategy(name),opponents/name)
    baseline=opponents/'published';shutil.copytree(ROOT/'build/sol-max-v2/published',baseline)
    league=opponents/'league'
    subprocess.run([sys.executable,str(ROOT/'scripts/build_sol_max_opponents_2027.py'),
        '--base',str(candidate),'--output',str(league)],check=True)
    counters=[str(league/('sol_max_'+name)) for name in ('wave','double_raid','split_guard','rotation','encirclement')]
    elites=[];reused={};qualification_seeds=a.stress_seeds
    if a.elite_plan:
        old=json.loads(a.elite_plan.read_text());old_rows={};wins=Counter()
        current_host=hashlib.sha256((ROOT/'scripts/evaluate_sol_max_2027.py').read_bytes()).hexdigest()
        if old['evaluation_host_sha256']!=current_host:raise ValueError('Elite evaluation host differs')
        qualification_seeds=old.get('qualification_seeds',old['stress_seeds'])
        sources={}
        for runtime in plan['runtimes']:
            phase=next(p for p in old['phases'][runtime] if p['name']=='qualification')
            if phase['seeds']!=qualification_seeds:raise ValueError('Mixed qualification seeds')
            data=json.loads((a.elite_plan.parent/('qualification-'+runtime+'.json')).read_text())
            for path in phase['opponents']:
                folder=Path(path);version=json.loads((folder/'manifest.json').read_text())['version']
                sources[folder.name+'-'+version]=folder
            old_rows[runtime]=data
            for row in data['matches']:
                if row['valid'] and row['outcome']=='loss':wins[row['opponent']]+=1
        qualified={name for name,n in wins.items() if n>=5}
        elite_root=opponents/'elite';elite_root.mkdir()
        for name in sorted(qualified):
            original=sources[name];target=elite_root/original.name
            if hashes(original)!=old['frozen_submissions'][str(original)]['files']:
                raise ValueError('Elite snapshot changed: '+name)
            shutil.copytree(original,target);elites.append(str(target))
        counters=elites+counters
        for runtime,data in old_rows.items():
            rows=[r for r in data['matches'] if r['opponent'] in qualified]
            info=plan['runtimes'][runtime]
            if data['runtime']!=info['root'] or any(r['sdk_hash']!=info['sdk_sha256'] or r['rules_hash']!=info['rules_sha256'] for r in rows):
                raise ValueError('Reused baseline runtime differs')
            if any(not r['valid'] or r['versions'][r['side']]!=json.loads((baseline/'manifest.json').read_text())['version'] for r in rows):
                raise ValueError('Only valid, identical-baseline records can be reused')
            data.update(candidate=str(baseline),matches=rows,summary=summary(rows))
            (out/('qualification-'+runtime+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
            reused[runtime]={'games':len(rows),'source_sha256':hashlib.sha256((a.elite_plan.parent/('qualification-'+runtime+'.json')).read_bytes()).hexdigest(),
                             'opponent_wins':sum(r['outcome']=='loss' for r in rows)}
    refs=[str(opponents/name) for name in ('deepseek_flash_2027_anchor','dsv41_1017_pair','step5_2027_echo','published')]
    expected=Counter();phases={}
    for runtime in plan['runtimes']:
        regression=opponents/('dsv41_1017_pair' if runtime=='source' else 'deepseek_flash_2027_anchor')
        phases[runtime]=[
            {'name':'regression','opponents':[str(regression)],'seeds':[2801,4093],'nonwins_max':0},
            {'name':'qualification','candidate':str(baseline),'opponents':counters,'seeds':qualification_seeds},
            {'name':'adversarial','opponents':counters,'seeds':a.stress_seeds,'nonwins_max':2},
            {'name':'mirror','opponents':[str(candidate)],'seeds':a.stress_seeds,'sides':['red']},
            {'name':'reference','opponents':refs,'seeds':a.reference_seeds,'nonwins_max':0},
            {'name':'native','opponents':refs[:2],'seeds':a.stress_seeds,'native':True,'diagnostic':True}]
        if elites:
            split=next(p for p in elites if Path(p).name=='sol_max_split_guard')
            raid=next(p for p in elites if Path(p).name=='sol_max_double_raid')
            phases[runtime][1:1]=[
                {'name':'split_regression','opponents':[split],'seeds':[12613],'nonwins_max':0},
                {'name':'raid_regression','opponents':[raid],'seeds':[12821],'sides':['red'],'nonwins_max':0}]
        for phase in phases[runtime]:
            expected[phase['name']]+=len(phase['opponents'])*len(phase['seeds'])*len(phase.get('sides',['red','blue']))
    artifacts={str(path):{'version':json.loads((path/'manifest.json').read_text())['version'],
                          'files':hashes(path)} for path in [candidate,*opponents.glob('*/')] if (path/'manifest.json').exists()}
    artifacts.update({str(path):{'version':json.loads((path/'manifest.json').read_text())['version'],
                          'files':hashes(path)} for path in league.iterdir()})
    artifacts.update({path:{'version':json.loads((Path(path)/'manifest.json').read_text())['version'],
                           'files':hashes(Path(path))} for path in elites})
    for runtime,info in plan['runtimes'].items():
        root=Path(info['root'])
        info['configuration_sha256']={str(path.relative_to(root/'config')):hashlib.sha256(path.read_bytes()).hexdigest()
                                      for path in sorted((root/'config').rglob('*')) if path.is_file()}
        previous=json.loads((a.runtime_plan.parent/('regression-'+runtime+'.json')).read_text())
        info['engine_hash']=previous['matches'][0]['engine_hash']
    plan.update(candidate=str(candidate),candidate_version=artifacts[str(candidate)]['version'],phases=phases,
        stress_seeds=a.stress_seeds,reference_seeds=a.reference_seeds,expected_games=dict(expected),
        frozen_artifact_sha256=hashes(candidate),frozen_submissions=artifacts,
        jobs_per_runtime=a.jobs_per_runtime,
        evaluation_host_sha256=hashlib.sha256((ROOT/'scripts/evaluate_sol_max_2027.py').read_bytes()).hexdigest())
    plan['gates']['native_nonwins_max']=None
    plan['qualification_seeds']=qualification_seeds
    plan['reused_qualification']=reused
    plan['expected_fresh_games']=dict(expected)
    plan['expected_fresh_games']['qualification']-=sum(r['games'] for r in reused.values())
    plan['gates']['qualification_opponent_wins_min']=24+sum(r['opponent_wins'] for r in reused.values())
    plan['gates']['qualified_variants_min']=3+len(elites)
    plan['notes'].append('RM team matches require identical registered lineups. Native-hardware results are supplemental diagnostics, outside the team-match performance gates.')
    (out/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
    print(out/'plan.json',dict(expected))


if __name__=='__main__':main()
