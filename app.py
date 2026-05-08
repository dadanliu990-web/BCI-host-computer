from PyQt5.QtWidgets import QApplication
import sys
import traceback

# === 全局异常钩子：捕获 traceback 写入文件（WSL2 下控制台输出可能被吞） ===
def _excepthook(exc_type, exc_value, exc_tb):
    tb_str = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
    print(tb_str, flush=True)
    with open('crash_log.txt', 'w') as f:
        f.write(tb_str)
    sys.__excepthook__(exc_type, exc_value, exc_tb)

sys.excepthook = _excepthook

# === BISECT STEP 2.8: + Controller (FULL RESTORE) ===
from ui import MainWindow
from curvesForm import CurvesForm
from spectrumForm import SpectrumForm
from impedanceForm import ImpedanceForm
from bandpowerForm import BandpowerForm
from spectrogramForm import SpectrogramForm
from accelerometerForm import AccelerometerForm
from topoMapForm import TopoMapForm
from controller import Controller

if __name__ == "__main__":
    print("=== BCI App Starting (Step 2.8: + Controller) ===", flush=True)

    print("[1/4] Creating QApplication...", flush=True)
    app = QApplication(sys.argv)

    print("[2/4] Creating MainWindow...", flush=True)
    w = MainWindow()
    print("[2/4] MainWindow created OK", flush=True)

    # --- Step 2.1: CurvesForm ---
    print("[3/4] Creating CurvesForm...", flush=True)
    cf = CurvesForm()
    cf.show()
    print("[3/4] CurvesForm created OK", flush=True)
    print("[3/4] Creating SpectrumForm...", flush=True)
    sf = SpectrumForm()
    sf.show()
    print("[3/4] SpectrumForm created OK", flush=True)
    print("[3/4] Creating ImpedanceForm...", flush=True)
    impf = ImpedanceForm()
    print("[3/4] ImpedanceForm created OK", flush=True)
    print("[3/4] Creating BandpowerForm...", flush=True)
    bpf = BandpowerForm()
    print("[3/4] BandpowerForm created OK", flush=True)
    print("[3/4] Creating SpectrogramForm...", flush=True)
    sgf = SpectrogramForm()
    print("[3/4] SpectrogramForm created OK", flush=True)
    print("[3/4] Creating AccelerometerForm...", flush=True)
    af = AccelerometerForm()
    print("[3/4] AccelerometerForm created OK", flush=True)
    print("[3/4] Creating TopoMapForm...", flush=True)
    topo = TopoMapForm(impf=impf, bpf=bpf)
    # 初始隐藏，通过"头皮拓扑图"按钮切换显示
    print("[3/4] TopoMapForm created OK", flush=True)
    w.cf = cf
    w.sf = sf
    w.impf = impf
    w.bpf = bpf
    w.sgf = sgf
    w.af = af
    w.topo = topo
    impf._mw = w
    print("[3/4] attributes assigned OK", flush=True)
    print("[3/4] Creating Controller...", flush=True)
    w.controller = Controller(w, cf, sf, impForm=impf, bpForm=bpf, sgForm=sgf, accForm=af, topoForm=topo)
    print("[3/4] Controller created OK", flush=True)

    print("[4/4] Showing MainWindow...", flush=True)
    w.show()
    print("=== Entering event loop ===", flush=True)
    sys.exit(app.exec_())
