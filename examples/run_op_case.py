"""Real end-to-end case: no letter-to-peak assignments are supplied here."""
import argparse
from pathlib import Path
from app.workflow import create_task,export_task
from app.ppt_generator import reproduce_reference
from app.validation.compare_reference import compare

p=argparse.ArgumentParser();p.add_argument('folder');p.add_argument('--output',default='outputs/OP-3TH-OP-auto');a=p.parse_args()
folder=Path(a.folder)
inputs={'structure':str(next(folder.glob('*.cdxml'))),'experiment':str(next(folder.glob('*.mnova'))),
        'template':str(next(p for p in folder.glob('*.pptx') if not p.name.startswith('~$'))),'raw':str(next(folder.glob('*.jdf')))}
task=create_task(inputs,a.output);print(export_task(task));compare(task,inputs['template'],a.output)
print(reproduce_reference(inputs['template'],Path(a.output).parent/'OP-3TH-OP-reference'))
