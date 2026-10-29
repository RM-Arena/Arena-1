"""Run a preregistered, frozen Sol Max acceptance plan on one runtime."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]


def stop_evaluation(process,stop_file):
    # The sandbox can reject process-group signals once a group member has
    # exited. Workers poll this task-owned token and close Battle normally.
    stop_file.write_text('stop\n')
    try:process.wait(timeout=20.)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:process.wait(timeout=5.)
        except subprocess.TimeoutExpired:process.kill();process.wait()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('plan',type=Path);p.add_argument('--runtime',required=True)
    p.add_argument('--collect-all',action='store_true',help='Finish all valid matches even after a performance gate fails')
    args=p.parse_args();plan=json.loads(args.plan.read_text());runtime=plan['runtimes'][args.runtime]
    out=args.plan.parent;env=dict(os.environ)
    env.pop('RMUC_RESOURCE_ROOT',None)
    env['RMUC_EVAL_RUNTIME']=runtime['root'];env['RMUC_SIM_BINARY']=runtime['binary']
    def status(phase,**extra):
        record={'plan':str(args.plan),'runtime':args.runtime,'phase':phase,**extra}
        temporary=out/(args.runtime+'-status.tmp');temporary.write_text(json.dumps(record,indent=2)+'\n')
        temporary.replace(out/(args.runtime+'-status.json'))
    failed_phases=[]
    for phase in plan['phases'][args.runtime]:
        report=out/(phase['name']+'-'+args.runtime+'.json');log=out/(phase['name']+'-'+args.runtime+'.log')
        stop_file=out/(phase['name']+'-'+args.runtime+'.stop')
        stop_file.unlink(missing_ok=True)
        env['RMUC_EVAL_STOP_FILE']=str(stop_file.resolve())
        command=[sys.executable,str(ROOT/'scripts/evaluate_sol_max_2027.py'),phase.get('candidate',plan['candidate']),*phase['opponents'],
            '--seeds',*map(str,phase['seeds']),'--sides',*phase.get('sides',['red','blue']),
            '--duration','420','--jobs',str(plan.get('jobs_per_runtime',1)),'--resume','--output',str(report)]
        if phase.get('native'):command.append('--native')
        status(phase['name'],state='running',report=str(report))
        with log.open('a') as handle:
            process=subprocess.Popen(command,cwd=ROOT,env=env,stdout=handle,stderr=subprocess.STDOUT,
                                     start_new_session=True)
            try:
                while process.poll() is None:
                    time.sleep(1.)
                    native_nonwins=0
                    for name in plan['runtimes']:
                        native_report=out/('native-'+name+'.json')
                        if not native_report.exists():continue
                        try:native_rows=json.loads(native_report.read_text()).get('matches',[])
                        except ValueError:continue
                        native_nonwins+=sum(r['valid'] and r['outcome']!='win' for r in native_rows)
                    native_limit=plan['gates']['native_nonwins_max']
                    if native_limit is not None and native_nonwins>native_limit:
                        status(phase['name'],state='failed',reason='Combined native gate failed',nonwins=native_nonwins)
                        stop_evaluation(process,stop_file)
                        status(phase['name'],state='failed',reason='Combined native gate failed',nonwins=native_nonwins)
                        raise SystemExit('Combined native gate failed')
                    for peer in plan['runtimes']:
                        peer_status=out/(peer+'-status.json')
                        if peer==args.runtime or not peer_status.exists():continue
                        try:
                            peer_state=json.loads(peer_status.read_text()).get('state')
                            failed=peer_state=='error' or peer_state=='failed' and not args.collect_all
                        except ValueError:continue
                        if failed:
                            stop_evaluation(process,stop_file)
                            status(phase['name'],state='stopped',reason=peer+' gate failed')
                            raise SystemExit('Acceptance stopped after peer failure')
                    if not report.exists():continue
                    try:data=json.loads(report.read_text())
                    except ValueError:continue
                    matches=data.get('matches',[])
                    nonwins=sum(r['valid'] and r['outcome']!='win' for r in matches)
                    invalid=sum(not r['valid'] for r in matches)
                    if not phase.get('diagnostic') and (invalid or nonwins>phase.get('nonwins_max',10**9) and not args.collect_all):
                        status(phase['name'],state='failed',nonwins=nonwins,invalid=invalid,report=str(report))
                        stop_evaluation(process,stop_file)
                        raise SystemExit('Acceptance stopped: '+phase['name']+' '+args.runtime)
            except BaseException:
                if process.poll() is None:stop_evaluation(process,stop_file)
                raise
        if process.returncode:
            status(phase['name'],state='error',exit_code=process.returncode,log=str(log));raise SystemExit(process.returncode)
        data=json.loads(report.read_text())
        nonwins=sum(r['valid'] and r['outcome']!='win' for r in data['matches'])
        invalid=sum(not r['valid'] for r in data['matches'])
        if not phase.get('diagnostic') and (invalid or nonwins>phase.get('nonwins_max',10**9)):
            if invalid or not args.collect_all:
                status(phase['name'],state='failed',nonwins=nonwins,invalid=invalid,report=str(report))
                raise SystemExit('Acceptance stopped after final phase result')
            failed_phases.append({'phase':phase['name'],'nonwins':nonwins})
        expected=len(phase['opponents'])*len(phase['seeds'])*len(phase.get('sides',['red','blue']))
        valid=[r for r in data['matches'] if r['valid']]
        if len(data['matches'] if phase.get('diagnostic') else valid)!=expected:
            status(phase['name'],state='error',message='Incomplete phase');raise SystemExit('Incomplete phase')
        status(phase['name'],state='completed',games=len(valid),summary=data.get('summary'),failed_performance_gates=failed_phases)
        print(args.runtime,phase['name'],data.get('summary'),flush=True)
    status('all',state='failed' if failed_phases else 'completed',failed_performance_gates=failed_phases)
    if failed_phases:raise SystemExit('Performance gates failed; all valid matches were retained')


if __name__=='__main__':main()
