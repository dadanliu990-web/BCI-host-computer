#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
独立运动想象刺激程序 (PsychoPy + LSL)
发送 LSL 标记：begin, left, right, end
脑电采集程序可通过 LSL 接收这些标记并与 EEG 数据同步保存。
"""

from psychopy.visual import Window, TextStim, ShapeStim
from psychopy.core import Clock, quit, wait
from psychopy import event
import pylsl
import random

# ========== 配置参数 ==========
TRIAL_NUM = 10  # 试次数
IMAGE_DURATION = 2.0  # 想象提示持续时间 (秒)
REST_DURATION = 1.0  # 试次间休息时间 (秒)

# ========== LSL 标记定义 ==========
# 您可以按照主程序需要的数值修改，此处提供默认值
MARKERS = {
    'begin': 1,
    'left': 2,
    'right': 3,
    'end': 4,
}


# ========== 辅助函数 ==========
def wait_with_escape(seconds, win):
    """等待指定秒数，期间检测 ESC 键退出（yield CPU 避免忙等）"""
    clock = Clock()
    while clock.getTime() < seconds:
        keys = event.getKeys(keyList=['escape'])
        if keys:
            win.close()
            quit()
        wait(0.05)  # 20Hz 检查，释放 CPU 给其他进程


# ========== 主实验函数 ==========
def run_stim():
    # 1. 创建 LSL 出口（outlet）
    # 使用随机流名，避免与其他程序冲突
    import uuid
    stream_name = f'psycho_marker_{uuid.uuid4().hex[:8]}'
    info = pylsl.StreamInfo(
        name=stream_name,
        type='Markers',
        channel_count=1,
        channel_format='int32',
        source_id='psycho_marker_stim'
    )
    outlet = pylsl.StreamOutlet(info)
    print(f"[LSL] 标记流已创建: {stream_name}")

    # 2. 创建实验窗口
    win = Window(size=(800, 600), fullscr=False, color='black', allowGUI=True)

    # 3. 显示指导语
    instr = TextStim(
        win,
        text='请根据高亮三角形进行左手或右手运动想象\n\n按任意键开始',
        color='white',
        wrapWidth=600,
        alignHoriz='center'
    )
    instr.draw()
    win.flip()
    event.waitKeys()

    # 发送实验开始标记
    outlet.push_sample([MARKERS['begin']])
    print("[LSL] 发送 begin 标记")

    # 4. 创建静态刺激（倒计时文本、休息文本、左右三角形）
    count_text = TextStim(win, text='', color='white')
    rest_text = TextStim(win, text='休息', color='white')

    left_tri = ShapeStim(
        win, fillColor='none',
        vertices=[(-200, 0), (-100, 50), (-120, 0), (-100, -50)],
        lineColor='white', units='pix', opacity=0.5
    )
    right_tri = ShapeStim(
        win, fillColor='none',
        vertices=[(200, 0), (100, 50), (120, 0), (100, -50)],
        lineColor='white', units='pix', opacity=0.5
    )
    highlight_color = [0.4627, 0.9333, 0.7765]  # 青绿色

    # 5. 试次循环
    for trial_idx in range(TRIAL_NUM):
        print(f"试次 {trial_idx + 1} / {TRIAL_NUM}")

        # ---- 倒计时（3,2,1）----
        for n in [3, 2, 1]:
            left_tri.draw()
            right_tri.draw()
            count_text.setText(str(n))
            count_text.draw()
            win.flip()
            wait_with_escape(1.0, win)

        # ---- 随机选择左/右 ----
        if random.choice(['left', 'right']) == 'left':
            # 高亮左侧三角形
            left_tri.fillColor = highlight_color
            left_tri.draw()
            right_tri.draw()
            win.flip()
            outlet.push_sample([MARKERS['left']])
            print("[LSL] 发送 left 标记")
        else:
            # 高亮右侧三角形
            right_tri.fillColor = highlight_color
            left_tri.draw()
            right_tri.draw()
            win.flip()
            outlet.push_sample([MARKERS['right']])
            print("[LSL] 发送 right 标记")

        # 保持高亮 IMAGE_DURATION 秒
        wait_with_escape(IMAGE_DURATION, win)

        # 清除高亮
        left_tri.fillColor = 'none'
        right_tri.fillColor = 'none'

        # ---- 试次间休息 ----
        rest_text.draw()
        win.flip()
        wait_with_escape(REST_DURATION, win)

    # 6. 实验结束
    outlet.push_sample([MARKERS['end']])
    print("[LSL] 发送 end 标记")

    # 显示结束语
    end_text = TextStim(win, text='实验完成，谢谢参与！\n按任意键退出', color='white')
    end_text.draw()
    win.flip()
    event.waitKeys()

    # 7. 清理
    win.close()
    quit()


# ========== 程序入口 ==========
if __name__ == '__main__':
    run_stim()