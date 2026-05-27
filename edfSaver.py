# -*- coding: utf-8 -*-
import numpy as np
from pathlib import Path
from datetime import datetime
import pyedflib
import debugPrinter as dp
from lsl_config import FS

class FileNameGenerator(object):
    def __init__(self, path_str_root):
        super(FileNameGenerator, self).__init__()
        self.fileNameCounter = 0
        self.path_str_root = path_str_root

    def generate_name(self):
        now = datetime.now()
        str_dateTime = now.strftime("%Y%m%d_%H%M%S")
        path_str = self.path_str_root + "/Session_" + str_dateTime
        if Path(path_str).exists():
            num = 1
            path_str_origin = path_str
            path_str = path_str_origin + "(" + str(num) + ")"
            while Path(path_str).exists():
                num = num + 1
                path_str = path_str_origin + "(" + str(num) + ")"

        return path_str

    def get_file_name(self,path_str):
        txtName=self.fileName_first_letter+str(self.fileNameCounter)+self.extended_str
        self.fileNameCounter = self.fileNameCounter+1
        filePathName = path_str+"/"+txtName
        return filePathName

class EDFSaver(object):
    """docstring for FileSaver"""

    _INIT_CAP_EEG = 60000     # ~4 min @ 250Hz
    _INIT_CAP_ACC = 60000
    _INIT_CAP_MARKER = 512

    def __init__(self, path_str):
        super(EDFSaver, self).__init__()
        self.fng = FileNameGenerator(path_str)
        self.path_str = None
        self.data = None
        self.data_1ch = None
        self.data_acc = None
        self.channel_info = []
        self.channel_info_1ch = []

        self.save_on = 0
        self.f = None
        self.fs_eeg = FS
        self.ch_8_1 = True
        self.filePathName = ''
        self._flushed = False

        # 预分配写指针
        self._eeg_cnt = 0
        self._acc_cnt = 0
        self._mar_cnt = 0
        self._eeg_1ch_cnt = 0

    def use_one_channel(self):
        self.ch_8_1 = False

    def use_eight_channels(self):
        self.ch_8_1 = True

    def make_path(self, path_str):
        if Path(path_str).exists():
            return 1
        Path(path_str).mkdir()
        self.path_str = path_str
        return 0

    def get_name(self):
        return self.fng.generate_name()

    @staticmethod
    def _write_row(dest, idx, ts_val, d_row):
        dest[idx, 0] = ts_val
        dest[idx, 1:] = d_row

    def _grow(self, arr, count, new_cap):
        """扩容数组，返回新数组"""
        new_arr = np.empty((new_cap, arr.shape[1]), dtype=arr.dtype)
        new_arr[:count] = arr[:count]
        return new_arr

    def new_data(self, s, ts, d):
        if not self.save_on:
            return
        n = len(ts)
        if s == 'eeg':
            if d.ndim != 2 or d.shape[1] != 64:
                print(f'[EDFSaver] 警告: EEG 数据形状错误 {d.shape}，期望 (n, 64)，已跳过')
                return
            for i in range(n):
                if self._eeg_cnt >= self.data.shape[0]:
                    self.data = self._grow(self.data, self._eeg_cnt, self.data.shape[0] * 2)
                self._write_row(self.data, self._eeg_cnt, ts[i], d[i])
                self._eeg_cnt += 1
        elif s == 'acc':
            for i in range(n):
                if self._acc_cnt >= self.data_acc.shape[0]:
                    self.data_acc = self._grow(self.data_acc, self._acc_cnt, self.data_acc.shape[0] * 2)
                self._write_row(self.data_acc, self._acc_cnt, ts[i], d[i])
                self._acc_cnt += 1
        elif s == 'mar':
            for i in range(n):
                if self._mar_cnt >= self.data_marker.shape[0]:
                    self.data_marker = self._grow(self.data_marker, self._mar_cnt, self.data_marker.shape[0] * 2)
                self._write_row(self.data_marker, self._mar_cnt, ts[i], d[i])
                self._mar_cnt += 1

    def new_data_1ch(self, s, ts, d):
        if not self.save_on:
            return
        n = len(ts)
        if s == 'eeg':
            for i in range(n):
                if self._eeg_1ch_cnt >= self.data_1ch.shape[0]:
                    self.data_1ch = self._grow(self.data_1ch, self._eeg_1ch_cnt, self.data_1ch.shape[0] * 2)
                self._write_row(self.data_1ch, self._eeg_1ch_cnt, ts[i], d[i])
                self._eeg_1ch_cnt += 1
        elif s == 'mar':
            for i in range(n):
                if self._mar_cnt >= self.data_marker.shape[0]:
                    self.data_marker = self._grow(self.data_marker, self._mar_cnt, self.data_marker.shape[0] * 2)
                self._write_row(self.data_marker, self._mar_cnt, ts[i], d[i])
                self._mar_cnt += 1

    def setup(self,file_path_str,file_name_str):
        import os
        os.makedirs(file_path_str, exist_ok=True)

        # 每次 setup 前重置 channel_info，防止多次录制时 header 累积导致数量不匹配
        self.channel_info = []
        self.channel_info_1ch = []

        '''ch_dict = {'label': 'F4', 'dimension': 'uV', 'sample_frequency': FS,'physical_max': 6553.6, 'physical_min': -6553.6,
            'digital_max': 32767, 'digital_min': -32768, 'transducer': '', 'prefilter':''}
        self.channel_info.append(ch_dict)
        ch_dict = {'label': 'C4', 'dimension': 'uV', 'sample_frequency': FS,'physical_max': 6553.6, 'physical_min': -6553.6,
            'digital_max': 32767, 'digital_min': -32768, 'transducer': '', 'prefilter':''}
        self.channel_info.append(ch_dict)
        ch_dict = {'label': 'P4', 'dimension': 'uV', 'sample_frequency': FS,'physical_max': 6553.6, 'physical_min': -6553.6,
            'digital_max': 32767, 'digital_min': -32768, 'transducer': '', 'prefilter':''}
        self.channel_info.append(ch_dict)
        ch_dict = {'label': 'Fz', 'dimension': 'uV', 'sample_frequency': FS,'physical_max': 6553.6, 'physical_min': -6553.6,
            'digital_max': 32767, 'digital_min': -32768, 'transducer': '', 'prefilter':''}
        self.channel_info.append(ch_dict)
        ch_dict = {'label': 'Cz', 'dimension': 'uV', 'sample_frequency': FS,'physical_max': 6553.6, 'physical_min': -6553.6,
            'digital_max': 32767, 'digital_min': -32768, 'transducer': '', 'prefilter':''}
        self.channel_info.append(ch_dict)
        ch_dict = {'label': 'F3', 'dimension': 'uV', 'sample_frequency': FS,'physical_max': 6553.6, 'physical_min': -6553.6,
            'digital_max': 32767, 'digital_min': -32768, 'transducer': '', 'prefilter':''}
        self.channel_info.append(ch_dict)
        ch_dict = {'label': 'C3', 'dimension': 'uV', 'sample_frequency': FS,'physical_max': 6553.6, 'physical_min': -6553.6,
            'digital_max': 32767, 'digital_min': -32768, 'transducer': '', 'prefilter':''}
        self.channel_info.append(ch_dict)
        ch_dict = {'label': 'P3', 'dimension': 'uV', 'sample_frequency': FS,'physical_max': 6553.6, 'physical_min': -6553.6,
            'digital_max': 32767, 'digital_min': -32768, 'transducer': '', 'prefilter':''}'''
        for i in range(64):
            ch_dict = {
                'label': f'EEG{i + 1}',
                'dimension': 'uV',
                'sample_frequency': FS,
                'physical_max': 6553.6,
                'physical_min': -6553.6,
                'digital_max': 32767,
                'digital_min': -32768,
                'transducer': '',
                'prefilter': ''
            }
            self.channel_info.append(ch_dict)

        '''ch_dict = {'label': 'Fp1', 'dimension': 'uV', 'sample_frequency': FS,'physical_max': 6553.6, 'physical_min': -6553.6, 
            'digital_max': 32767, 'digital_min': -32768, 'transducer': '', 'prefilter':''}'''
        ch_dict = {
            'label': 'Fp1',
            'dimension': 'uV',
            'sample_frequency': FS,
            'physical_max': 6553.6,
            'physical_min': -6553.6,
            'digital_max': 32767,
            'digital_min': -32768,
            'transducer': '',
            'prefilter': ''
        }
        self.channel_info_1ch.append(ch_dict)

        self.data = np.empty(shape=(self._INIT_CAP_EEG, 65))
        self.data_1ch = np.empty(shape=(self._INIT_CAP_EEG, 2))
        self.data_acc = np.empty(shape=(self._INIT_CAP_ACC, 5))
        self.data_marker = np.empty(shape=(self._INIT_CAP_MARKER, 2), dtype=object)
        self._eeg_cnt = 0
        self._acc_cnt = 0
        self._mar_cnt = 0
        self._eeg_1ch_cnt = 0

        self.filePathName = file_path_str+'/'+file_name_str+'_.edf'

        self.save_on = 1
        self._flushed = False
        

    def get_current_name(self):
        return self.filePathName

    def flush_data(self):
        if self.data is None:
            return  # setup() never called, nothing to flush
        if self._flushed:
            return  # 避免重复 flush 覆盖已有数据（stop_recording + win_evt QUIT 双重触发）
        # 切片到实际记录数量
        if self.ch_8_1:
            eeg_data = self.data[:self._eeg_cnt, :]
        else:
            eeg_data = self.data_1ch[:self._eeg_1ch_cnt, :]
        acc_data = self.data_acc[:self._acc_cnt, :]
        mar_data = self.data_marker[:self._mar_cnt, :]

        if self.ch_8_1:
            num_channels = eeg_data.shape[1] - 1
            self.f = pyedflib.EdfWriter(self.filePathName, num_channels, file_type=pyedflib.FILETYPE_EDFPLUS)
            self.f.setSignalHeaders(self.channel_info)
        else:
            self.f = pyedflib.EdfWriter(self.filePathName, 1, file_type=pyedflib.FILETYPE_EDFPLUS)
            self.f.setSignalHeaders(self.channel_info_1ch)

        data_save = eeg_data.astype(np.float64)
        t_arr = data_save[:, 0]

        # 转换为 2D 数组 (n_channels, n_samples)，pyedflib 要求此格式
        data_2d = np.ascontiguousarray(data_save[:, 1:].T)

        # 自动检测数据范围，设置合适的 physical_min/max 以避免量化精度损失
        dmin = float(data_2d.min())
        dmax = float(data_2d.max())
        margin = max((dmax - dmin) * 0.1, 1.0)
        phys_min = dmin - margin
        phys_max = dmax + margin
        print(f'[EDF] 数据范围: [{dmin:.4f}, {dmax:.4f}], 物理范围: [{phys_min:.4f}, {phys_max:.4f}]')

        # 更新 channel_info 中的物理范围并重新设置信号头
        if self.ch_8_1:
            for ch_dict in self.channel_info:
                ch_dict['physical_min'] = phys_min
                ch_dict['physical_max'] = phys_max
            self.f.setSignalHeaders(self.channel_info)
        else:
            for ch_dict in self.channel_info_1ch:
                ch_dict['physical_min'] = phys_min
                ch_dict['physical_max'] = phys_max
            self.f.setSignalHeaders(self.channel_info_1ch)

        # 数据验证日志：打印每个通道的 min/max，便于诊断信号是否正常写入
        for ch in range(data_2d.shape[0]):
            ch_min = data_2d[ch, :].min()
            ch_max = data_2d[ch, :].max()
            ch_std = float(data_2d[ch, :].std())
            if ch < 8:
                print(f'[EDF] ch{ch+1} min={ch_min:.4f} max={ch_max:.4f} std={ch_std:.4f}')

        # 标记数据：过滤超出 EEG 数据时间范围的无效 marker
        if mar_data.shape[0] > 0:
            m_arr = mar_data[:, 0]
            max_eeg_time = t_arr[-1]
            valid_mask = m_arr <= max_eeg_time
            n_dropped = (~valid_mask).sum()
            if n_dropped > 0:
                print(f'[EDF] 丢弃 {n_dropped} 个超出 EEG 时间范围的 marker (max_eeg={max_eeg_time:.3f}s)')
            m_arr = m_arr[valid_mask]
            m_labels = mar_data[valid_mask, 1]
            if len(m_arr) > 0:
                m_index = np.searchsorted(t_arr, m_arr)
                m_index = np.clip(m_index, 0, len(t_arr) - 1)
                m_t = m_index / self.fs_eeg
                for i, m in enumerate(m_t):
                    self.f.writeAnnotation(m, -1, str(m_labels[i]))

        self.f.writeSamples(data_2d)
        self.f.close()
        self.save_on = 0
        self._eeg_cnt = 0
        self._flushed = True
        self._acc_cnt = 0
        self._mar_cnt = 0
        self._eeg_1ch_cnt = 0
        print('data saved')




