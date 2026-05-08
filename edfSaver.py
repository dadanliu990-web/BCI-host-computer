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
    def _write_row(dest, idx, ts, d):
        dest[idx, 0] = ts[0]
        dest[idx, 1:] = d[0]

    def _grow(self, arr, count, new_cap):
        """扩容数组，返回新数组"""
        new_arr = np.empty((new_cap, arr.shape[1]), dtype=arr.dtype)
        new_arr[:count] = arr[:count]
        return new_arr

    def new_data(self, s, ts, d):
        if not self.save_on:
            return
        if s == 'eeg':
            if self._eeg_cnt >= self.data.shape[0]:
                self.data = self._grow(self.data, self._eeg_cnt, self.data.shape[0] * 2)
            self._write_row(self.data, self._eeg_cnt, ts, d)
            self._eeg_cnt += 1
        elif s == 'acc':
            if self._acc_cnt >= self.data_acc.shape[0]:
                self.data_acc = self._grow(self.data_acc, self._acc_cnt, self.data_acc.shape[0] * 2)
            self._write_row(self.data_acc, self._acc_cnt, ts, d)
            self._acc_cnt += 1
        elif s == 'mar':
            if self._mar_cnt >= self.data_marker.shape[0]:
                self.data_marker = self._grow(self.data_marker, self._mar_cnt, self.data_marker.shape[0] * 2)
            self._write_row(self.data_marker, self._mar_cnt, ts, d)
            self._mar_cnt += 1

    def new_data_1ch(self, s, ts, d):
        if not self.save_on:
            return
        if s == 'eeg':
            if self._eeg_1ch_cnt >= self.data_1ch.shape[0]:
                self.data_1ch = self._grow(self.data_1ch, self._eeg_1ch_cnt, self.data_1ch.shape[0] * 2)
            self._write_row(self.data_1ch, self._eeg_1ch_cnt, ts, d)
            self._eeg_1ch_cnt += 1
        elif s == 'mar':
            if self._mar_cnt >= self.data_marker.shape[0]:
                self.data_marker = self._grow(self.data_marker, self._mar_cnt, self.data_marker.shape[0] * 2)
            self._write_row(self.data_marker, self._mar_cnt, ts, d)
            self._mar_cnt += 1

    def setup(self,file_path_str,file_name_str):
        # ch_dict = {'label': 'lslts', 'dimension': 'ms', 'sample_frequency': FS}
        # self.channel_info.append(ch_dict)

        import os
        os.makedirs(file_path_str, exist_ok=True)

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
        

    def get_current_name(self):
        return self.filePathName

    def flush_data(self):
        if self.data is None:
            return  # setup() never called, nothing to flush
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

        data_list = []
        for i in range(data_save.shape[1] - 1):
            data_list.append(data_save[:, i + 1].copy())

        # 标记数据
        if mar_data.shape[0] > 0:
            m_arr = mar_data[:, 0]
            m_index = np.searchsorted(t_arr, m_arr)
            m_t = m_index / self.fs_eeg
            for i, m in enumerate(m_t):
                self.f.writeAnnotation(m, -1, str(mar_data[i, 1]))

        self.f.writeSamples(data_list)
        self.f.close()
        print('data saved')




