import numpy as np
import matplotlib.pyplot as plt
from scipy import signal

# ======== 参数设置 ========
fs = 500                # 采样率 (Hz)
duration = 2.0          # 信号时长 (秒)
f_square = 12           # 方波基频 (Hz)

t = np.arange(0, duration, 1/fs)                     # 时间轴
square_wave = signal.square(2 * np.pi * f_square * t) # 生成方波（范围 -1 ~ 1）

# ======== 绘图 ========
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)

# ---- 子图1：时域波形 ----
ax1.plot(t, square_wave, linewidth=0.8)
ax1.set_ylabel('Amplitude')
ax1.set_title(f'{f_square} Hz 连续矩形波 (方波) —— 时域波形')
ax1.grid(True)
ax1.set_xlim(0, 0.5)          # 只显示前 0.5 秒，避免波形太密

# ---- 子图2：时频谱图 ----
f, t_spec, Sxx = signal.spectrogram(square_wave, fs, nperseg=256, noverlap=200)
Sxx_db = 10 * np.log10(Sxx + 1e-12)          # 转换为 dB

# 绘制并保存返回的绘图对象
mesh = ax2.pcolormesh(t_spec, f, Sxx_db, shading='gouraud', cmap='jet')
ax2.set_ylabel('Frequency [Hz]')
ax2.set_xlabel('Time [sec]')
ax2.set_title('时频谱图 (Spectrogram)')
ax2.set_ylim(0, 100)          # 显示到 100 Hz，清晰看到 12,36,60,84 Hz
ax2.set_xlim(0, duration)

# 添加颜色条，使用 mesh 对象
cbar = plt.colorbar(mesh, ax=ax2, label='Power [dB]')

plt.tight_layout()
plt.show()