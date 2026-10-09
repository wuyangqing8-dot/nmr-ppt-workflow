import os,subprocess,sys
from pathlib import Path
import pytest

def test_real_task_review_edit_move_save(tmp_path):
    root=Path(__file__).resolve().parents[1]
    path=root/'outputs/OP-3TH-OP-auto/task.json'
    if not path.exists():pytest.skip('real case required')
    env=dict(os.environ);env['QT_QPA_PLATFORM']='windows' if os.name=='nt' else 'offscreen'
    env['PYTHONPATH']=str(root)
    result=subprocess.run([sys.executable,str(root/'tests/gui_check.py'),str(path),str(tmp_path)],cwd=root,env=env,capture_output=True,text=True,timeout=90)
    assert result.returncode==0,result.stdout+result.stderr
    assert 'verified' in result.stdout
