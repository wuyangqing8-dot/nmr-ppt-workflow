import sys,traceback
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from app.ui import MainWindow
from app.storage import read_json
app=QApplication([])
task=read_json(sys.argv[1]);task['output']=sys.argv[2]
w=MainWindow();w.load(task);code=0

def check():
    global code
    try:
        w.table.selectRow(0);app.processEvents()
        original=task['spectrum']['integrals'][0]['value'];w.confirm()
        assert task['structure']['environments'][0]['status']=='人工确认'
        w.table.item(0,1).setText('zz');app.processEvents()
        assert task['structure']['environments'][0]['label']=='zz'
        assert task['structure']['environments'][0]['status']=='待确认'
        w.moved((task['structure']['environments'][0]['id'],'spectrum'),[4.0,3.5]);w.save()
        saved=read_json(Path(sys.argv[2])/'task.json')
        assert saved['structure']['environments'][0]['positions']['spectrum']==[4.,3.5]
        assert saved['spectrum']['integrals'][0]['value']==original
        print('GUI review/edit/drag/save verified',flush=True)
    except Exception:
        traceback.print_exc();code=1
    finally:
        w.close();app.quit()
QTimer.singleShot(0,check)
app.exec()
sys.exit(code)
