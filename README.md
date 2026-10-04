# BCI-host-computer

仓库提供三个独立的脑电波形显示 App 版本，各文件夹内都有中文安装与使用说明：

- [简化版（64 通道 WiFi/UDP）](eeg_waveform_app_simple/README.md)：UDP 端口 8080。
- [新协议简化版（4 通道串口）](eeg_waveform_app_new_protocol/README.md)：USB 虚拟串口，250 Hz。
- [OpenBCI / 自研板 LSL 版（8 通道）](eeg_waveform_app_openbci_lsl/README.md)：接收现有 LSL 流，也可将自研板串口数据桥接到 LSL；附 LabRecorder。

仓库不包含实验范式、个人 EEG 数据、离线分析脚本、训练模型、Alpha 校准文件和本机设备配置。各版本只保留 App 源码及运行所需依赖；数据、虚拟环境和生成文件均通过忽略规则排除。
