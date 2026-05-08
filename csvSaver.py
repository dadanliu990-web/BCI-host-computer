# -*- coding: utf-8 -*-
import csv
import json
import os
import numpy as np
from datetime import datetime, timezone
from pathlib import Path
from lsl_config import FS


class CSVSaver:

    _INIT_CAP_EEG = 60000
    _INIT_CAP_ACC = 60000
    _INIT_CAP_MARKER = 512

    def __init__(self, path_str):
        self.path_str_root = path_str
        self.save_on = False
        self.data_eeg = None
        self.data_acc = None
        self.data_marker = None
        self.file_dir = None
        self.file_name = None
        self.metadata = {}
        self._eeg_cols = 64
        self._acc_cols = 4
        self._eeg_cnt = 0
        self._acc_cnt = 0
        self._mar_cnt = 0

    def setup(self, file_path_str, file_name_str):
        os.makedirs(file_path_str, exist_ok=True)
        self.file_dir = file_path_str
        self.file_name = file_name_str
        self.data_eeg = np.empty(shape=(self._INIT_CAP_EEG, 65))
        self.data_acc = np.empty(shape=(self._INIT_CAP_ACC, 5))
        self.data_marker = np.empty(shape=(self._INIT_CAP_MARKER, 2), dtype=object)
        self._eeg_cnt = 0
        self._acc_cnt = 0
        self._mar_cnt = 0
        self.save_on = True
        self.metadata = {
            'subject_id': '',
            'session_name': file_name_str,
            'task_type': '',
            'recording_start': datetime.now().isoformat(),
            'sample_rate': FS,
            'channel_count': 64,
            'channel_labels': [f'EEG{i+1}' for i in range(64)],
            'acc_channels': ['ACC_X', 'ACC_Y', 'ACC_Z', 'ACC_Mag'],
            'filter_settings': 'none',
            'device_info': '',
            'software_version': '1.0',
            'notes': ''
        }

    def set_metadata(self, key, value):
        self.metadata[key] = value

    def get_current_name(self):
        if self.file_dir and self.file_name:
            return os.path.join(self.file_dir, self.file_name + '_.csv')
        return ''

    @staticmethod
    def _grow(arr, count, new_cap):
        new_arr = np.empty((new_cap, arr.shape[1]), dtype=arr.dtype)
        new_arr[:count] = arr[:count]
        return new_arr

    def new_data(self, s, ts, d):
        if not self.save_on:
            return
        if s == 'eeg':
            if d.shape[1] != 64:
                print(f'CSVSaver: 警告 — 收到非64通道数据 (shape={d.shape})，已跳过')
                return
            if self._eeg_cnt >= self.data_eeg.shape[0]:
                self.data_eeg = self._grow(self.data_eeg, self._eeg_cnt, self.data_eeg.shape[0] * 2)
            self.data_eeg[self._eeg_cnt, 0] = ts[0]
            self.data_eeg[self._eeg_cnt, 1:] = d[0]
            self._eeg_cnt += 1
        elif s == 'acc':
            if self._acc_cnt >= self.data_acc.shape[0]:
                self.data_acc = self._grow(self.data_acc, self._acc_cnt, self.data_acc.shape[0] * 2)
            self.data_acc[self._acc_cnt, 0] = ts[0]
            self.data_acc[self._acc_cnt, 1:] = d[0]
            self._acc_cnt += 1
        elif s == 'mar':
            if self._mar_cnt >= self.data_marker.shape[0]:
                self.data_marker = self._grow(self.data_marker, self._mar_cnt, self.data_marker.shape[0] * 2)
            self.data_marker[self._mar_cnt, 0] = ts[0]
            self.data_marker[self._mar_cnt, 1] = d[0]
            self._mar_cnt += 1

    def flush_data(self):
        if not self.save_on:
            return
        self.save_on = False

        eeg_data = self.data_eeg[:self._eeg_cnt, :]
        acc_data = self.data_acc[:self._acc_cnt, :]
        mar_data = self.data_marker[:self._mar_cnt, :]

        self.metadata['recording_end'] = datetime.now().isoformat()
        if eeg_data.shape[0] > 0:
            self.metadata['eeg_samples'] = int(eeg_data.shape[0])
        meta_path = os.path.join(self.file_dir, self.file_name + '_metadata.json')
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(self.metadata, f, indent=2, ensure_ascii=False)

        csv_path = os.path.join(self.file_dir, self.file_name + '_.csv')
        with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)

            # 元数据注释行
            writer.writerow(['% subject_id', self.metadata.get('subject_id', '')])
            writer.writerow(['% session_name', self.metadata.get('session_name', '')])
            writer.writerow(['% sample_rate', FS])
            writer.writerow(['% recording_start', self.metadata.get('recording_start', '')])
            writer.writerow(['% recording_end', self.metadata.get('recording_end', '')])

            # 列头
            header = ['Sample_Index', 'Timestamp_Unix', 'Timestamp_Formatted']
            for i in range(self._eeg_cols):
                header.append(f'EEG{i+1}')
            for i in range(self._acc_cols):
                header.append(['ACC_X', 'ACC_Y', 'ACC_Z', 'ACC_Mag'][i])
            header.append('Marker')
            writer.writerow(header)

            # 合并数据：EEG 为主时间轴，ACC 和 Marker 按最近邻时间戳对齐
            if eeg_data.shape[0] == 0:
                print('CSV: no EEG data to save')
                return

            eeg_ts = eeg_data[:, 0]
            eeg_vals = eeg_data[:, 1:]

            # ACC 插值到 EEG 时间轴
            acc_interp = np.zeros((eeg_ts.shape[0], self._acc_cols))
            if acc_data.shape[0] > 0:
                acc_ts = acc_data[:, 0]
                acc_vals = acc_data[:, 1:]
                for j in range(self._acc_cols):
                    acc_interp[:, j] = np.interp(eeg_ts, acc_ts, acc_vals[:, j])

            # Marker 最近邻对齐
            markers = [''] * eeg_ts.shape[0]
            if mar_data.shape[0] > 0:
                marker_ts = mar_data[:, 0]
                marker_labels = mar_data[:, 1]
                for m_ts, m_label in zip(marker_ts, marker_labels):
                    idx = np.argmin(np.abs(eeg_ts - m_ts))
                    if markers[idx]:
                        markers[idx] += ';' + str(m_label)
                    else:
                        markers[idx] = str(m_label)

            # 逐行写入
            base_unix = datetime.now(timezone.utc).timestamp()
            for i in range(eeg_ts.shape[0]):
                ts_unix = base_unix + eeg_ts[i]
                ts_formatted = datetime.fromtimestamp(ts_unix).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3]
                row = [i, f'{ts_unix:.6f}', ts_formatted]
                for j in range(eeg_vals.shape[1]):
                    row.append(f'{eeg_vals[i, j]:.2f}')
                for j in range(self._acc_cols):
                    row.append(f'{acc_interp[i, j]:.4f}')
                row.append(markers[i])
                writer.writerow(row)

        print(f'CSV saved: {csv_path}')
        print(f'Metadata saved: {meta_path}')
