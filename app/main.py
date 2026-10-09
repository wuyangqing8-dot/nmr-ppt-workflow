import argparse,json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(description='本地核磁归属与科研 PPT 工具')
    sub=p.add_subparsers(dest='command')
    run=sub.add_parser('run');run.add_argument('--structure',required=True);run.add_argument('--experiment',required=True)
    run.add_argument('--prediction');run.add_argument('--integrals');run.add_argument('--raw');run.add_argument('--template',required=True)
    run.add_argument('--grouping-profile',help='采用经过人工指定的等效氢分组 JSON')
    run.add_argument('--output',required=True);run.add_argument('--solvent',default='CDCl3');run.add_argument('--experiment-page',type=int)
    run.add_argument('--prediction-page',type=int);run.add_argument('--known-impurities',default='');run.add_argument('--no-export',action='store_true')
    run.add_argument('--temperature',type=float);run.add_argument('--frequency',type=float)
    ref=sub.add_parser('reference');ref.add_argument('--template',required=True);ref.add_argument('--output',required=True)
    exp=sub.add_parser('export');exp.add_argument('--task',required=True);exp.add_argument('--final',action='store_true')
    ui=sub.add_parser('gui');ui.add_argument('--task')
    a=p.parse_args()
    if a.command in [None,'gui']:
        from app.ui import launch
        launch(getattr(a,'task',None));return
    if a.command=='reference':
        from app.ppt_generator import reproduce_reference
        print(reproduce_reference(a.template,a.output));return
    from app.workflow import create_task,export_task
    if a.command=='export':
        from app.storage import read_json
        print(export_task(read_json(a.task),not a.final));return
    task=create_task({k:getattr(a,k) for k in ['structure','experiment','prediction','integrals','raw','template','grouping_profile']},a.output,a.solvent,
        a.experiment_page,a.prediction_page,[v.strip() for v in a.known_impurities.split(',') if v.strip()],a.temperature,a.frequency)
    if not a.no_export:print(export_task(task))
    print(json.dumps(task['assignment'],ensure_ascii=False))

if __name__=='__main__':main()
