# BCI-host-computer
本项目是一个面向运动想象等BCI实验的实时脑电采集与分析上位机，支持64通道EEG数据通过WiFi/UDP接收（250 Hz），并兼容LSL协议与PsychoPy等刺激程序同步。系统采用多线程异步架构：UdpReceiver和LSLReceiver负责数据接收，DataProcessor线程完成滤波、存储与UI数据分发，主线程仅负责界面渲染，确保高数据率下图形界面流畅。  主要功能包括：实时波形滚动显示、功率谱密度（Welch）、时频谱图（STFT）、频段功率柱状图（绝对值/相对值/比值）、基于标准差的信号质量评估（阻抗检测）以及10‑20系统的头皮拓扑图。数据可保存为EDF（国际标准）和CSV（带元数据），并支持离线文件回放。
BCI实时脑电采集与分析系统
项目简介
这是一个功能完备的实时脑电（EEG）采集、可视化与在线分析系统，面向运动想象（Motor Imagery）等BCI实验范式。系统通过WiFi/UDP接收自研脑电板的64通道EEG数据，并支持LSL协议与外部刺激程序（如PsychoPy）同步。软件提供波形显示、频谱分析、时频谱图、频段功率、信号质量评估（阻抗检测）、头皮拓扑图等多种实时可视化工具，同时支持EDF/CSV数据保存、离线回放，并预留了在线机器学习分类接口。

项目采用多线程+异步信号架构，确保高数据率（250 Hz）下界面流畅；通过按需加载和跨窗口数据共享优化性能；可轻松扩展新的数据分析模块。

主要功能
实时数据采集

UDP接收自研脑电板数据（64通道，250 Hz）。

LSL标记接收（与PsychoPy等刺激程序同步）。

支持滤波器预设（RAW, Alpha, Beta, Gamma等），实时查看滤波后波形。

多种可视化窗口

波形曲线：64通道实时滚动显示，支持芯片分组、通道独立开关。

功率谱密度（PSD）：Welch方法计算，多通道垂直偏移显示。

时频谱图（Spectrogram）：STFT热图，支持通道选择、色图调节、dB范围调整。

频段功率柱状图：Delta/Theta/Alpha/Beta/Gamma功率（绝对值/相对值/比值）。

信号质量评估（阻抗检测）：基于标准差评估电极接触质量，柱状图+颜色分级。

头皮拓扑图：基于10‑20系统的2D地形图，可显示信号质量或指定频段功率的空间分布。

数据存储与回放

数据保存为EDF（国际标准）和CSV（带元数据）。

支持离线加载EDF/CSV文件，波形回放+同步频谱/拓扑图更新。

手动事件标记（artifact, blink, instruction等）插入。

在线分类扩展

预留CSP+SVM等机器学习模型接口，可实现实时运动想象解码。

分类结果可反馈至界面或外部设备。

性能优化

按需创建窗口，降低启动负载。

数据共享：阻抗检测结果复用给拓扑图，频带能量结果复用给拓扑图功率模式。

硬件数据日志降频输出，减少主线程I/O压力。

技术架构




语言：Python 3.9+

GUI框架：PyQt5

绘图库：pyqtgraph（波形/频谱/柱状图），matplotlib（拓扑图）

信号处理：SciPy (Welch, STFT, butter滤波器)

LSL通信：pylsl

文件读写：pyedflib, csv

机器学习（扩展）：scikit-learn, mne

安装与使用
环境准备
bash
# 推荐使用conda创建虚拟环境
conda create -n bci python=3.9
conda activate bci

# 安装依赖
pip install -r requirements.txt
requirements.txt 主要内容：

text
pyqt5
numpy
scipy
pyqtgraph
matplotlib
pylsl
pyedflib
# 可选（用于拓扑图增强）
mne
命令行启动
bash
python app.py
基本操作流程
硬件连接：确保脑电板通过WiFi发送UDP数据（默认端口8080）。

启动软件：主界面打开后，波形窗口自动显示实时信号。

设置保存路径：在“数据记录”区域选择保存目录，填写被试ID等信息。

开始记录：点击“开始记录”创建EDF/CSV文件，同时LSL接收器启动。

运行刺激程序（可选）：启动PsychoPy等LSL标记发送程序。

查看分析窗口：通过控制面板按钮打开频谱图、拓扑图等。

停止记录：数据自动保存，可立即回放验证。

项目文件结构
text
bci-python/
├── app.py                  # 主入口
├── controller.py           # 核心控制器（数据分发、记录控制）
├── data_processor.py       # 数据处理线程（接收、滤波、存储、UI分发）
├── udp_receiver.py         # UDP接收器
├── lslReceiver.py          # LSL接收器
├── dSPx.py                 # 多通道滤波器管理器
├── filterButter.py         # 实时IIR滤波器实现
├── edfSaver.py / csvSaver.py  # 文件保存
├── curvesForm.py           # 波形显示窗口
├── spectrumForm.py         # 频谱图窗口
├── spectrogramForm.py      # 时频谱图窗口
├── bandpowerForm.py        # 频段功率窗口
├── impedanceForm.py        # 信号质量（阻抗）窗口
├── topoMapForm.py          # 头皮拓扑图窗口
├── accelerometerForm.py    # 加速度计显示（可选）
├── playback.py             # 回放控制器
├── lsl_config.py           # 协议常量配置
├── constantValues.py       # 全局常量
├── debugPrinter.py         # 调试输出
├── ui.py                   # 主窗口UI逻辑
├── ui_config/              # UI设计文件和配置文件
│   ├── mainwindow.ui
│   ├── curvesform.ui
│   ├── filter_presets.json
│   └── ...
└── data/                   # 数据保存目录（自动创建）
主要特性详解
1. 实时数据流与滤波
UDP数据以250 Hz频率到达，DataProcessor线程负责接收并分发给存储和显示。

用户可在主界面选择滤波预设（RAW/Alpha/Beta等），波形立即更新，但不影响原始数据存储。

滤波器采用Butterworth IIR，逐点实时处理，保证低延迟。

2. 数据共享优化
拓扑图的信号质量模式直接读取ImpedanceForm已算好的标准差。

拓扑图的功率模式直接读取BandpowerForm每500ms计算的全通道频段功率。

避免重复进行64次FFT，显著降低CPU负载。

3. 回放与离线分析
支持加载历史EDF/CSV文件，波形窗口显示完整数据，X轴可拖动/自动播放。

回放时，频谱图、时频谱图、拓扑图同步更新（采用按需刷新策略，避免卡顿）。

回放结束后自动恢复实时数据接收。

4. 头皮拓扑图
基于10‑20系统电极坐标，支持信号质量（标准差）和功率分布两种模式。

动态调整dB范围（百分位法），自动适应不同信号强度。

标志性电极（Cz, Fz, T7等）高亮显示，便于定位。

5. 实验范式支持
通过LSL接收psycho_marker标记（begin, left, right, end）。

标记与EEG数据同步保存至EDF/CSV，方便后期分析。

预留机器学习接口，可集成CSP/SVM等模型实现实时分类。

依赖与版本
库	版本	用途
PyQt5	5.15+	GUI框架
numpy	1.21+	数组计算
scipy	1.7+	信号处理（滤波，Welch，STFT）
pyqtgraph	0.13+	实时绘图（波形，频谱，柱状图）
matplotlib	3.5+	拓扑图绘制
pylsl	1.16+	LSL协议
pyedflib	0.1.30+	EDF读写
mne	1.0+	（可选）电极坐标及拓扑图辅助
已知限制与未来计划
当前版本：未集成在线机器学习，但已预留接口。

拓扑图：实时插值计算略耗CPU，可通过降低分辨率/更新频率缓解。

多窗口性能：启动时仅创建曲线窗口，其他窗口按需创建，已优化。

计划添加：

实时运动想象分类（CSP+SVM/EEGNet）。

更丰富的伪迹检测（如EMG/EOG）。

支持更多类型的数据导入（如BrainVision、Neuroscan格式）。

贡献指南
欢迎提交Issue和Pull Request。若需增加新分析模块，建议：

继承QWidget创建新窗口类。

在app.py中按需创建实例。

在Controller._on_ui_data中分发数据给新窗口。

若窗口需要共享其他模块的计算结果，可通过接口获取。

许可证
本项目采用 MIT License，可自由使用和修改。
