# -*- coding=utf-8 -*-
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UDP 接收速率检测工具
功能：监听指定 UDP 端口，每秒统计收到的数据包数量，并显示速率。
适用于检测脑电采集板发送的 UDP 数据包（每包 262 字节，头 0xAA，尾 0xEE，含 4 字节序列号）。
"""

import socket
import time
import threading

# ========== 配置参数 ==========
UDP_IP = "0.0.0.0"          # 监听所有网卡
UDP_PORT = 8080              # 与采集板发送端口一致
BUFFER_SIZE = 4096           # 接收缓冲区大小
CHECK_HEADER_FOOTER = True   # 是否校验包头(0xAA)和包尾(0xEE)，只统计有效数据包
PACKET_HEADER = 0xAA
PACKET_FOOTER = 0xEE

# ========== 全局计数器 ==========
packet_count = 0
count_lock = threading.Lock()
running = True

def udp_listener():
    """UDP 接收线程，持续接收并计数"""
    global packet_count, running
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(1.0)          # 设置超时以便周期性检查 running 标志
    sock.bind((UDP_IP, UDP_PORT))
    print(f"[监听] 已启动，端口 {UDP_PORT}，开始统计...")

    while running:
        try:
            data, addr = sock.recvfrom(BUFFER_SIZE)
            # 可选：校验包格式
            if CHECK_HEADER_FOOTER:
                if len(data) < 2:
                    continue
                if data[0] != PACKET_HEADER or data[-1] != PACKET_FOOTER:
                    continue   # 不符合格式，不计入
            with count_lock:
                packet_count += 1
        except socket.timeout:
            continue
        except Exception as e:
            print(f"[错误] {e}")
            break
    sock.close()

def rate_printer():
    """每秒打印一次速率"""
    global packet_count, running
    last_count = 0
    while running:
        time.sleep(1.0)
        with count_lock:
            current = packet_count
        rate = current - last_count
        print(f"[速率] {rate} 包/秒   (累计: {current})")
        last_count = current

if __name__ == "__main__":
    # 启动接收线程
    listener_thread = threading.Thread(target=udp_listener, daemon=True)
    listener_thread.start()

    # 启动速率打印（在主线程中运行，也可另起线程）
    try:
        rate_printer()
    except KeyboardInterrupt:
        print("\n[结束] 用户中断")
    finally:
        running = False
        listener_thread.join(timeout=2)
        print("程序退出")