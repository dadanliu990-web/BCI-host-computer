# -*- coding: utf-8 -*-
# -*- coding: utf-8 -*-
"""
自研采集板串口数据 -> LSL EEG Stream 桥接程序（修正版）

默认数据包格式：
    Byte 0-3   : 包头 AA FF F1 10
    Byte 4-7   : CH1 int32 little-endian
    Byte 8-11  : CH2 int32 little-endian
    Byte 12-15 : CH3 int32 little-endian
    Byte 16-19 : CH4 int32 little-endian
    Byte 20-21 : 双累加校验 checksum1 checksum2

说明：
- 默认启用 checksum 校验。
- 默认把 raw int32 缩放为 raw * 0.001 后发送到 LSL，单位标注为 microvolts。
- 0.001 只是为了先让 BrainVision LSL Viewer 能正常显示波形，后续应替换成真实的 uV/count。
- 默认不手动传入 LSL timestamp，先由 LSL 自动打时间戳，避免 Viewer 出现斜线/竖线。
- 新增：若未指定 --port，则自动扫描系统所有可用串口，并选择第一个。
"""

import argparse
import struct
import time
import threading
import sys
from collections import deque

import serial
import serial.tools.list_ports
import pylsl


PACKET_SIZE = 22
SYNC_HEADER = bytes([0xAA, 0xFF, 0xF1, 0x10])
HEADER_LEN = 4
CHANNEL_COUNT = 4
NOMINAL_SRATE = 250


def calc_checksum(packet_without_checksum: bytes):
    """计算前 20 字节的双累加校验。"""
    sum1 = 0
    sum2 = 0
    for b in packet_without_checksum:
        sum1 = (sum1 + b) & 0xFF
        sum2 = (sum2 + sum1) & 0xFF
    return sum1, sum2


def create_lsl_outlet(name: str, srate: int):
    """创建 LSL EEG Outlet。"""
    info = pylsl.StreamInfo(
        name=name,
        type='EEG',
        channel_count=CHANNEL_COUNT,
        nominal_srate=float(srate),
        channel_format=pylsl.cf_float32,
        source_id=f'selfboard_serial_{name}',
    )

    desc = info.desc()
    desc.append_child_value('manufacturer', 'SelfMadeBoard')
    desc.append_child_value('unit', 'microvolts')

    channels = desc.append_child('channels')
    for i in range(CHANNEL_COUNT):
        ch = channels.append_child('channel')
        ch.append_child_value('label', f'Ch{i + 1}')
        ch.append_child_value('unit', 'microvolts')
        ch.append_child_value('type', 'EEG')

    outlet = pylsl.StreamOutlet(info, chunk_size=1, max_buffered=360)
    return outlet


class SerialToLSLBridge:
    def __init__(
        self,
        port: str,
        baudrate: int,
        stream_name: str,
        srate: int,
        uv_per_count: float,
        enable_checksum: bool,
        print_every: int,
    ):
        self.port = port
        self.baudrate = baudrate
        self.stream_name = stream_name
        self.srate = srate
        self.uv_per_count = uv_per_count
        self.enable_checksum = enable_checksum
        self.print_every = print_every

        self.ser = None
        self.outlet = create_lsl_outlet(stream_name, srate)

        self.running = False
        self.thread = None

        self.packet_count = 0
        self.checksum_fail_count = 0
        self.sync_lost_count = 0
        self.bytes_read = 0
        self.parse_fail_count = 0

        self.start_time = None
        self.last_rate_time = None
        self.last_rate_packet_count = 0
        self.recent_samples = deque(maxlen=5)

        print(f'[LSL] 已创建 EEG 流: {stream_name} ({CHANNEL_COUNT} ch, {srate} Hz, float32)')
        print('[LSL] 单位标注: microvolts')
        print(f'[参数] raw 缩放系数 uv_per_count = {uv_per_count}')
        print(f'[参数] checksum 校验: {"开启" if enable_checksum else "关闭"}')

    def open_serial(self):
        print(f'[串口] 正在打开 {self.port} @ {self.baudrate} baud ...')
        self.ser = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=0.1,
        )
        self.ser.reset_input_buffer()
        print(f'[串口] {self.port} 已打开')

    def start(self):
        if self.running:
            return
        if self.ser is None or not self.ser.is_open:
            self.open_serial()

        self.running = True
        self.start_time = time.time()
        self.last_rate_time = self.start_time
        self.last_rate_packet_count = 0

        self.thread = threading.Thread(target=self._read_loop, daemon=True)
        self.thread.start()
        print('[Bridge] 数据桥接已启动')

    def stop(self):
        self.running = False

        if self.thread is not None:
            self.thread.join(timeout=2.0)

        if self.ser is not None and self.ser.is_open:
            self.ser.close()
            print(f'[串口] {self.port} 已关闭')

        elapsed = time.time() - self.start_time if self.start_time else 0
        avg_rate = self.packet_count / elapsed if elapsed > 0 else 0

        print('\n========== 运行统计 ==========')
        print(f'运行时间:       {elapsed:.2f} s')
        print(f'有效数据包:     {self.packet_count}')
        print(f'平均接收率:     {avg_rate:.2f} pkt/s')
        print(f'读取字节数:     {self.bytes_read}')
        print(f'失步次数:       {self.sync_lost_count}')
        print(f'校验失败:       {self.checksum_fail_count}')
        print(f'解析失败:       {self.parse_fail_count}')
        print('==============================')

    def _read_loop(self):
        buf = bytearray()

        while self.running:
            try:
                waiting = self.ser.in_waiting
                if waiting > 0:
                    chunk = self.ser.read(waiting)
                    self.bytes_read += len(chunk)
                    buf.extend(chunk)
                else:
                    time.sleep(0.001)
            except serial.SerialException as e:
                print(f'[串口] 读取错误: {e}')
                time.sleep(0.5)
                continue

            while len(buf) >= PACKET_SIZE:
                idx = buf.find(SYNC_HEADER)

                if idx < 0:
                    keep = HEADER_LEN - 1
                    if len(buf) > keep:
                        buf = buf[-keep:]
                    self.sync_lost_count += 1
                    break

                if idx > 0:
                    del buf[:idx]
                    self.sync_lost_count += 1

                if len(buf) < PACKET_SIZE:
                    break

                packet = bytes(buf[:PACKET_SIZE])
                t_packet_ready = pylsl.local_clock()  # timestamp = 完整串口包到达时刻
                del buf[:PACKET_SIZE]

                sample = self._parse_packet(packet)
                if sample is None:
                    self.parse_fail_count += 1
                    continue

                # 手动传入 t_packet_ready 作为 LSL timestamp，
                # 延迟 = 上位机 _on_data 中的 pylsl.local_clock() - ts[-1]
                self.outlet.push_sample(sample, timestamp=t_packet_ready)

                self.packet_count += 1
                self.recent_samples.append(sample)

                if self.packet_count % self.print_every == 0:
                    self._print_status(sample)

            if len(buf) > PACKET_SIZE * 2000:
                print('[警告] 缓冲区异常过大，已清空。')
                buf.clear()

    def _parse_packet(self, packet: bytes):
        if len(packet) != PACKET_SIZE:
            return None

        if packet[:HEADER_LEN] != SYNC_HEADER:
            return None

        if self.enable_checksum:
            calc1, calc2 = calc_checksum(packet[:-2])
            recv1, recv2 = packet[-2], packet[-1]
            if calc1 != recv1 or calc2 != recv2:
                self.checksum_fail_count += 1
                return None

        values = []
        for ch in range(CHANNEL_COUNT):
            offset = HEADER_LEN + ch * 4
            raw = struct.unpack_from('<i', packet, offset)[0]
            value_uv = float(raw) * self.uv_per_count
            values.append(value_uv)

        return values

    def _print_status(self, sample):
        now = time.time()
        elapsed_total = now - self.start_time if self.start_time else 0

        interval = now - self.last_rate_time if self.last_rate_time else 0
        interval_packets = self.packet_count - self.last_rate_packet_count
        instant_rate = interval_packets / interval if interval > 0 else 0
        avg_rate = self.packet_count / elapsed_total if elapsed_total > 0 else 0

        self.last_rate_time = now
        self.last_rate_packet_count = self.packet_count

        sample_str = ', '.join(f'{v:.3f}' for v in sample)

        print(
            f'[状态] 总包数={self.packet_count}, '
            f'瞬时率={instant_rate:.1f} pkt/s, '
            f'平均率={avg_rate:.1f} pkt/s, '
            f'失步={self.sync_lost_count}, '
            f'校验失败={self.checksum_fail_count}, '
            f'样本=[{sample_str}]',
            flush=True
        )


def parse_args():
    parser = argparse.ArgumentParser(description='自研采集板串口数据转 LSL EEG Stream（修正版）')

    parser.add_argument(
        '--port',
        default=None,
        help='串口号，例如 COM6。若不指定，则自动扫描系统所有可用串口。'
    )
    parser.add_argument('--baudrate', type=int, default=115200, help='串口波特率')
    parser.add_argument('--name', default='selfboard_eeg', help='LSL EEG 流名称')
    parser.add_argument('--srate', type=int, default=NOMINAL_SRATE, help='LSL 标称采样率')
    parser.add_argument(
        '--uv-per-count',
        type=float,
        default=0.001,
        help='raw int32 到 microvolts 的换算系数；默认 0.001，即 raw/1000'
    )
    parser.add_argument(
        '--no-checksum',
        action='store_true',
        help='关闭包尾 checksum 校验。若开启校验后完全收不到包，可先加此参数排查。'
    )
    parser.add_argument('--print-every', type=int, default=250, help='每多少个有效包打印一次状态')

    return parser.parse_args()


def auto_detect_port() -> str:
    """
    自动扫描系统所有可用串口，返回第一个找到的端口名。
    若没有找到任何串口，则返回 None。
    """
    ports = serial.tools.list_ports.comports()
    if not ports:
        return None
    # 返回第一个可用端口
    return ports[0].device


def main():
    args = parse_args()
    enable_checksum = not args.no_checksum

    # ----- 自动检测串口（若未指定）-----
    if args.port is None:
        print('未指定串口，正在自动扫描所有可用串口 ...')
        detected = auto_detect_port()
        if detected is None:
            print('错误: 未找到任何可用串口')
            sys.exit(1)
        args.port = detected
        print(f'自动选择串口: {args.port}')
    # ----------------------------------

    print('=' * 70)
    print(' 自研采集板串口数据 -> LSL EEG Stream 桥接程序（修正版）')
    print('=' * 70)
    print(f'串口:       {args.port}')
    print(f'波特率:     {args.baudrate}')
    print(f'LSL 流名:   {args.name}')
    print(f'通道数:     {CHANNEL_COUNT}')
    print(f'采样率:     {args.srate} Hz')
    print(f'包头:       {SYNC_HEADER.hex(" ")}')
    print(f'包长度:     {PACKET_SIZE} bytes')
    print('包格式:     4B 包头 + 4*int32 + 2B checksum')
    print(f'缩放系数:   {args.uv_per_count} microvolts/count')
    print(f'校验:       {"开启" if enable_checksum else "关闭"}')
    print('=' * 70)
    print('按 Ctrl+C 退出')
    print()

    bridge = SerialToLSLBridge(
        port=args.port,
        baudrate=args.baudrate,
        stream_name=args.name,
        srate=args.srate,
        uv_per_count=args.uv_per_count,
        enable_checksum=enable_checksum,
        print_every=args.print_every,
    )

    try:
        bridge.open_serial()
        bridge.start()

        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print('\n[退出] 收到 Ctrl+C，正在停止 ...')

    except serial.SerialException as e:
        print(f'\n[错误] 串口错误: {e}')

    finally:
        bridge.stop()
        print('[完成] 程序已退出。')


if __name__ == '__main__':
    main()