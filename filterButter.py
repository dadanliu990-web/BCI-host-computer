# -*- coding: utf-8 -*-
from collections import deque
import numpy as np

from scipy import signal

class FilterButter(object):
	"""docstring for FilterButter"""
	def __init__(self,fs,order,fc,s): #s is 'high' or 'low' or ...
		super(FilterButter, self).__init__()
		self.fs = fs
		self.order = order
		# 兼容 list/tuple 类型的 fc（bandpass/bandstop 需要两个频率）
		fc_arr = np.array(fc, dtype=float) if isinstance(fc, (list, tuple)) else fc
		self.b, self.a = signal.butter(order, fc_arr/(fs/2), s)
		# bandpass/bandstop 的系数长度是 2*order+1，lowpass/highpass 是 order+1
		self.arr_len = len(self.b)

		self.x = deque(self.arr_len*[0.0],self.arr_len)
		self.y = deque(self.arr_len*[0.0],self.arr_len)

	def filter_dummy(self,f):
		return f

	def filter(self,f):
		self.x.append(f)
		tmp = 0
		for i in range(self.arr_len):
			t = self.b[i]*self.x[self.arr_len-1-i]
			tmp = t+tmp

		for i in range(self.arr_len-1):
			t = -self.a[i+1]*self.y[self.arr_len-1-i]
			tmp = t+tmp
		
		self.y.append(tmp)
		return tmp

	# def filter(self,f,a,b):
			
	# 		tmp= b[0]*self.x[3] \
	# 			+b[1]*self.x[2] \
	# 			+b[2]*self.x[1] \
	# 			+b[3]*self.x[0] \
	# 			-a[0]*self.y[3] \
	# 			-a[1]*self.y[2] \
	# 			-a[2]*self.y[1]
	# 		self.y.append(tmp)
	# 		return tmp




