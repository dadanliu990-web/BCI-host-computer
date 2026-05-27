# -*- coding: utf-8 -*-
from filterButter import FilterButter
import numpy as np
import json
import os


class DSPx(object):
	"""docstring for DSPx"""
	def __init__(self, ch_num):
		super(DSPx, self).__init__()
		self.ch_num = ch_num
		self.fs = 250
		self.current_preset = 'RAW'
		self.hp_p3 = []
		self.lp_40 = []
		self.notch = []
		for i in range(ch_num):
			self.hp_p3.append(FilterButter(250, 3, 0.3, 'high'))
			self.lp_40.append(FilterButter(250, 3, 40, 'low'))
			self.notch.append(None)

	def load_preset(self, preset_name):
		"""从 filter_presets.json 加载指定的预设"""
		preset_file = os.path.join(os.path.dirname(__file__), "ui_config", "filter_presets.json")
		if not os.path.exists(preset_file):
			return False
		with open(preset_file, 'r') as f:
			presets = json.load(f)['presets']
		if preset_name not in presets:
			return False
		p = presets[preset_name]
		self._apply_config(p)
		self.current_preset = preset_name
		return True

	def _apply_config(self, config):
		lowcut = config.get('lowcut')
		highcut = config.get('highcut')
		notch_freq = config.get('notch')
		order = config.get('order', 4)

		for i in range(self.ch_num):
			if lowcut is not None:
				self.hp_p3[i] = FilterButter(self.fs, order, lowcut, 'high')
			else:
				self.hp_p3[i] = None
			if highcut is not None:
				self.lp_40[i] = FilterButter(self.fs, order, highcut, 'low')
			else:
				self.lp_40[i] = None
			if notch_freq is not None:
				# 标量 → ±1Hz 窄带阻，兼容 scipy butter bandstop 需要两个频率的要求
				if isinstance(notch_freq, (int, float)):
					notch_fc = [notch_freq - 1.0, notch_freq + 1.0]
				else:
					notch_fc = list(notch_freq)
				self.notch[i] = FilterButter(self.fs, order, notch_fc, 'bandstop')
			else:
				self.notch[i] = None

	def get_preset_list(self):
		"""返回所有可用预设名称"""
		preset_file = os.path.join(os.path.dirname(__file__), "ui_config", "filter_presets.json")
		if not os.path.exists(preset_file):
			return ['RAW']
		with open(preset_file, 'r') as f:
			presets = json.load(f)['presets']
		return list(presets.keys())

	def set_highpass(self, freq):
		"""设置高通截止频率，freq=None 或 <=0 则禁用"""
		if freq is None or freq <= 0:
			for i in range(self.ch_num):
				self.hp_p3[i] = None
		else:
			for i in range(self.ch_num):
				self.hp_p3[i] = FilterButter(self.fs, 4, freq, 'high')

	def set_lowpass(self, freq):
		"""设置低通截止频率，freq=None 或 <=0 则禁用"""
		if freq is None or freq <= 0:
			for i in range(self.ch_num):
				self.lp_40[i] = None
		else:
			for i in range(self.ch_num):
				self.lp_40[i] = FilterButter(self.fs, 4, freq, 'low')

	def set_notch(self, freq):
		"""设置陷波频率，freq=None 或 <=0 则禁用"""
		if freq is None or freq <= 0:
			for i in range(self.ch_num):
				self.notch[i] = None
		else:
			notch_fc = [freq - 1.0, freq + 1.0]
			for i in range(self.ch_num):
				self.notch[i] = FilterButter(self.fs, 4, notch_fc, 'bandstop')

	def filter_dummy(self, arr):
		return arr

	def filter(self, arr):
		# arr should be 2 dimensional array, for example shape = (6,8), means 8 channels, 6 time points
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
			if self.hp_p3[i] is not None:
				val = self.hp_p3[i].filter(val)
			if self.lp_40[i] is not None:
				val = self.lp_40[i].filter(val)
			if self.notch[i] is not None:
				val = self.notch[i].filter(val)
			tmp[i] = val
		return tmp




