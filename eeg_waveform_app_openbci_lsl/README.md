# OpenBCI / 自研板 LSL 脑电波形 App

这是一个独立的 8 通道 EEG 上位机版本，可发现并显示 LSL 数据流，也可把自研板串口数据桥接为 LSL。界面提供实时波形、频谱、滤波和 LSL 流连接功能。LabRecorder 用于把选中的 LSL 流保存为 XDF 文件。

本目录仅包含运行这个 App 所需的源码、依赖清单和 LabRecorder 许可证文件；不包含实验范式、个人 EEG 数据、离线分析脚本或分析数据。

## 运行环境

- Windows 10/11
- Python 3.10 或更新版本
- 发送端与本机需要处于可互相发现 LSL 流的网络环境；跨网段或防火墙可能阻止发现
- 使用自研板串口桥接时，需要安装相应板卡驱动并确认串口号
- 录制 XDF 需要另行下载 LabRecorder（见下文）；只看波形不要求安装 LabRecorder

## 安装 Python 依赖

在本文件夹打开 PowerShell：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

每次新开 PowerShell 使用程序前，先进入本文件夹并运行：

```powershell
.\.venv\Scripts\Activate.ps1
```

## 启动 App

### 只打开界面，或连接已有 LSL 流

```powershell
python run.py --viewer-only
```

此模式不会尝试打开自研板串口。若 OpenBCI 软件或其他采集程序已经向 LSL 发布 EEG 流，等待 App 扫描后，在“数据流”列表中选择 EEG 流并点击“连接”；也可以双击列表中的流。找不到流时点击“扫描流”重新搜索。

### 使用自研板串口并发布 LSL

```powershell
python run.py --port COM6
```

将 `COM6` 改为 Windows“设备管理器”中实际的串口号。程序会读取串口数据并发布名为 `selfboard_eeg` 的 LSL 流，App 随后可连接该流。默认串口波特率为 115200、标称采样率为 250 Hz。可调整参数：

```powershell
python run.py --port COM6 --baudrate 115200 --srate 250 --name selfboard_eeg
```

省略 `--port` 时，程序会扫描串口；只有一个串口时自动使用，有多个时弹出选择框。若只想验证界面启动，请用 `--viewer-only`，避免误打开其他串口设备。

当前界面按最多 8 个 EEG 通道绘制。不同设备的串口协议和通道顺序可能不同；串口桥接仅适用于与 `serial_to_lsl_fixed.py` 所解析格式兼容的自研板数据。

## LabRecorder：安装、录制与保存

LabRecorder 是独立程序，负责将 LSL 流写入 XDF。Python 依赖安装不会自动安装 LabRecorder；仓库没有包含其 EXE 和 DLL 等二进制文件。

### 1. 下载并放到 App 可识别的位置

1. 打开 [LabRecorder 官方 Releases](https://github.com/labstreaminglayer/App-LabRecorder/releases)，下载 Windows 64 位发行包。此版本代码按 LabRecorder 1.17.0 的目录布局查找程序。
2. 将发行包完整解压到本目录下：
   `LabRecorder/LabRecorder-1.17.0-Win_amd64/`
3. 确认最终路径为：
   `LabRecorder/LabRecorder-1.17.0-Win_amd64/LabRecorder.exe`

不要只把压缩包放进目录，也不要只复制 EXE；保留官方发行包中的其他运行文件。若下载到不同版本或目录名称不同，请将内容放到上述路径，或按本项目 `ui.py` 中的 `LABRECORDER_EXE` 路径调整目录。

### 2. 启动 LabRecorder

启动 App 后约 1 秒，程序会在上述路径存在 `LabRecorder.exe` 时尝试自动启动 LabRecorder。也可在 App 控制面板点击“启动 LR”。App 会尝试通过本机 RCS 服务（`127.0.0.1:22345`）设置初始参数：

- 保存目录：本项目目录下的 `recordings/`
- 文件/研究名称：`eeg_session`
- 选择当时可见的 LSL 流

连接 EEG 流后，App 还会再次请求选择可见流。请以 LabRecorder 窗口里实际显示的流及勾选状态为准。若采集程序在 LabRecorder 启动后才开始发布流，先让流开始发送，再在 App 点击“扫描流”并连接；随后检查 LabRecorder 是否列出并选中了需要记录的流。

### 3. 选择要记录的流并开始录制

在 LabRecorder 窗口中检查流列表，勾选本次需要保存的 EEG 流；如需同时保存独立的 LSL Marker 流，也要在列表中单独勾选。确认输出目录和文件名后，在 **LabRecorder 窗口**点击开始/Record 按钮开始录制，并在该窗口观察录制状态。

当前 App 的“启动 LR”按钮只负责启动 LabRecorder；App 界面没有开始录制或停止录制按钮。因此，必须在 LabRecorder 自己的窗口中开始和停止，不能仅凭 App 显示 “LR: Running” 判断正在录制。该状态表示 LabRecorder 进程在运行。

### 4. 停止录制并找到文件

实验结束后，在 LabRecorder 窗口点击停止录制。等待写入完成后，到以下目录确认 XDF 文件：

```text
eeg_waveform_app_openbci_lsl/recordings/
```

保存位置是相对于 App 文件夹的路径；用本项目的 `run.py` 启动时，会解析到本项目目录下的 `recordings/`。LabRecorder 会根据其文件命名规则生成 XDF 文件名。录制文件只保存在本机，仓库的忽略规则会排除 `recordings/` 和 `*.xdf`；请另行备份重要记录，不要提交到 GitHub。

## 常见问题排查

- **App 能开，但 LabRecorder 没有启动**：确认 `LabRecorder.exe` 的完整路径和发行包内容正确；在 App 点击“启动 LR”查看状态。若文件缺失，界面会显示找不到程序。
- **LabRecorder 无法启动或 RCS 状态异常**：关闭其他已打开的 LabRecorder 实例后重开 App；检查本机 TCP 端口 `22345` 没有被其他程序占用。App 与 LabRecorder 的 RCS 通信使用本机回环地址，不需要把 RCS 端口暴露到局域网。
- **数据流列表为空**：确认发送端已开始发布 LSL 流，点击“扫描流”；检查两台设备的网络连通性、LSL 所需的局域网发现通信和 Windows 防火墙规则。只连接 Wi-Fi/网线并不保证不同子网间能够自动发现流。
- **找不到自研板流**：确认串口号正确、设备驱动已安装且串口未被其他程序占用；成功启动桥接后应出现 `selfboard_eeg`。不要同时运行多个桥接进程占用同一串口。
- **LabRecorder 没有收到想要的流**：确认该流在 LabRecorder 列表中可见且已勾选。App 的“连接”用于显示波形；它与 LabRecorder 是否选中、是否正在录制是两项独立状态。
- **停止后没有找到 XDF**：先确认在 LabRecorder 窗口按了停止并等待文件写完，再检查本项目的 `recordings/` 目录以及 LabRecorder 窗口显示的输出路径。

## 目录内容

- `run.py`：App 启动入口，支持仅查看和自研板串口桥接。
- `ui.py`：波形、频谱、LSL 流选择及 LabRecorder 启动界面。
- `stream_receiver.py`：发现、订阅 LSL 流。
- `serial_to_lsl_fixed.py`：自研板串口数据到 LSL 的桥接。
- `filter_controller.py`：滤波设置。
- `labrecorder_controller.py`：启动 LabRecorder 并通过本机 RCS 设置路径、文件名和流选择；源码含录制控制方法，但当前界面未接线开始/停止按钮。
- `requirements.txt`：Python 第三方依赖。
- `LabRecorder/LabRecorder-1.17.0-Win_amd64/LICENSE`：LabRecorder 许可证文件。LabRecorder 运行程序需从官方发行版另行下载。

该目录提供 Python 源码运行方式；不包含本机打包产物、个人窗口配置、虚拟环境、录制文件、实验范式、分析程序或 EEG 数据。
