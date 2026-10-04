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
    w.cf = cf
    w.sf = sf
    print("[3/4] attributes assigned OK", flush=True)
    print("[3/4] Creating Controller...", flush=True)
    w.controller = Controller(w, cf, sf)
    print("[3/4] Controller created OK", flush=True)
    # 初始化默认滤波: HP 0.5Hz, LP 40Hz, Notch 50Hz
    w.controller.set_highpass(0.5)
    w.controller.set_lowpass(40.0)
    w.controller.set_notch(50.0)

    print("[4/4] Showing MainWindow...", flush=True)
    w.show()
    print("=== Entering event loop ===", flush=True)
    sys.exit(app.exec_())
