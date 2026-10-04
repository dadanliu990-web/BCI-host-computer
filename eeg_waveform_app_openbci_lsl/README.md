# OpenBCI / 自研板 LSL 脑电波形 App

这是一个独立的 8 通道 EEG 上位机版本：可以发现并显示局域网内的 LSL 数据流，也提供自研板串口数据转为 LSL 的桥接程序。界面包含实时波形、频谱、滤波和 LabRecorder 控制。它不包含实验范式、个人脑电记录、离线分析脚本或分析数据。

## 运行环境

- Windows 10/11
- Python 3.10 或更新版本
- 使用 LSL 数据流时，发送端和本机需处于可互相发现的网络环境
- 使用自研板串口桥接时，需要安装板卡驱动并确认串口号

## 安装与启动

在本文件夹打开 PowerShell：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

仅打开查看界面（不尝试打开自研板串口）：

```powershell
python run.py --viewer-only
```

连接自研板串口并同时发布 `selfboard_eeg` LSL 流：

```powershell
python run.py --port COM6
```

把 `COM6` 改为设备管理器中显示的实际端口。串口默认波特率为 115200、采样率为 250 Hz；可用 `--baudrate`、`--srate` 和 `--name` 调整。也可以不传 `--port`，程序会在检测到串口时让你选择。

如果 OpenBCI 或其他设备软件已经把数据发布为 LSL 流，启动 App 后在“数据流”列表中选择相应 EEG 流并连接即可；此路径不需要串口桥接。当前界面按 8 个 EEG 通道绘制。

## LabRecorder

录制功能依赖 LabRecorder 1.17.0 Windows 版，本仓库不打包其二进制发行文件。请从 [LabRecorder 官方 Releases](https://github.com/labstreaminglayer/App-LabRecorder/releases) 下载并完整解压到本文件夹的 `LabRecorder/LabRecorder-1.17.0-Win_amd64/`，确认其中包含 `LabRecorder.exe`。不安装 LabRecorder 时，波形查看和 LSL 连接仍可使用，录制功能不可用。启动 App 后会尝试启动 LabRecorder，但不会自动开始记录。确认数据流和保存位置后，再通过界面操作录制。记录生成的 XDF 文件保存在本机 `recordings/`，该目录已加入忽略规则，请不要把个人记录提交到仓库。

## 目录内容

- `run.py`：App 启动入口，支持 viewer-only 和自研板串口桥接。
- `ui.py`、`stream_receiver.py`、`filter_controller.py`：波形界面、LSL 接收和滤波。
- `serial_to_lsl_fixed.py`：自研板串口到 LSL 的桥接。
- `labrecorder_controller.py`：LabRecorder 控制接口。
- `requirements.txt`：Python 运行依赖。
- `LabRecorder/`：LabRecorder 可执行程序和第三方许可证。

本文件夹提供 Python 源码运行方式；不包含本机 PyInstaller 打包目录、个人窗口布局配置、录制文件、虚拟环境、测试或分析程序。
