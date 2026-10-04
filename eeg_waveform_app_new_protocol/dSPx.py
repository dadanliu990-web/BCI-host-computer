# -*- coding: utf-8 -*-
from filterButter import FilterButter
import numpy as np


class DSPx(object):
    def __init__(self, ch_num):
        super(DSPx, self).__init__()
        self.ch_num = ch_num
        self.fs = 250
        self._hp_freq = None
        self._lp_freq = None
        self._notch_freq = None

        self.hp = []
        self.lp = []
        self.notch = []
        for i in range(ch_num):
            self.hp.append(None)
            self.lp.append(None)
            self.notch.append(None)

    def set_highpass(self, freq):
        """Set high-pass cutoff frequency (Hz). Pass None to disable."""
        self._hp_freq = freq
        if freq is not None:
            for i in range(self.ch_num):
                self.hp[i] = FilterButter(self.fs, 4, freq, 'high')
        else:
            for i in range(self.ch_num):
                self.hp[i] = None

    def set_lowpass(self, freq):
        """Set low-pass cutoff frequency (Hz). Pass None to disable."""
        self._lp_freq = freq
        if freq is not None:
            for i in range(self.ch_num):
                self.lp[i] = FilterButter(self.fs, 4, freq, 'low')
        else:
            for i in range(self.ch_num):
                self.lp[i] = None

    def set_notch(self, freq, bandwidth=1.0):
        """Set notch frequency (Hz) with bandwidth (Hz). Pass None as freq to disable."""
        self._notch_freq = freq
        self._notch_bw = bandwidth
        if freq is not None:
            for i in range(self.ch_num):
                self.notch[i] = FilterButter(self.fs, 4, [freq - bandwidth, freq + bandwidth], 'bandstop')
        else:
            for i in range(self.ch_num):
                self.notch[i] = None

    def filter(self, arr):
        filtered_data = np.zeros(shape=(arr.shape))
        for i in range(arr.shape[0]):
            tmp = arr[i, :]
            filtered_data_one_time_point = self.filter_arr(tmp)
            filtered_data[i, :] = filtered_data_one_time_point
        return filtered_data

    def filter_arr(self, arr):
        tmp = np.zeros(shape=(arr.shape))
        for i, a in enumerate(arr):
            val = a
            if self.hp[i] is not None:
                val = self.hp[i].filter(val)
            if self.lp[i] is not None:
                val = self.lp[i].filter(val)
            if self.notch[i] is not None:
                val = self.notch[i].filter(val)
            tmp[i] = val
        return tmp
