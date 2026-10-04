# -*- coding: utf-8 -*-
"""Digital filter design and per-sample IIR filtering (SOS-based, scipy)."""
import numpy as np
from scipy.signal import butter, iirnotch, sosfilt


class FilterController:
    def __init__(self, n_channels=8, fs=250):
        self.n_channels = n_channels
        self.fs = fs
        self.hp_enabled = False
        self.lp_enabled = False
        self.notch_enabled = False
        self.hp_cutoff = 1.0
        self.lp_cutoff = 40.0
        self.notch_freq = 50.0
        self.notch_q = 30.0
        self._hp_sos = None
        self._lp_sos = None
        self._notch_sos = None
        self._hp_zi = None
        self._lp_zi = None
        self._notch_zi = None
        self._rebuild_all()

    def set_hp(self, enabled, cutoff=None):
        self.hp_enabled = enabled
        if cutoff is not None:
            self.hp_cutoff = cutoff
        self._rebuild_all()

    def set_lp(self, enabled, cutoff=None):
        self.lp_enabled = enabled
        if cutoff is not None:
            self.lp_cutoff = cutoff
        self._rebuild_all()

    def set_notch(self, enabled, freq=None, q=None):
        self.notch_enabled = enabled
        if freq is not None:
            self.notch_freq = freq
        if q is not None:
            self.notch_q = q
        self._rebuild_all()

    def _rebuild_all(self):
        nyq = self.fs / 2.0
        if self.hp_enabled and self.hp_cutoff > 0:
            try:
                self._hp_sos = butter(4, self.hp_cutoff / nyq, 'highpass', output='sos')
            except Exception:
                self._hp_sos = None
        else:
            self._hp_sos = None
        if self.lp_enabled and self.lp_cutoff > 0:
            try:
                self._lp_sos = butter(4, self.lp_cutoff / nyq, 'lowpass', output='sos')
            except Exception:
                self._lp_sos = None
        else:
            self._lp_sos = None
        if self.notch_enabled and self.notch_freq > 0:
            try:
                b, a = iirnotch(self.notch_freq / nyq, self.notch_q)
                sos = np.zeros((1, 6))
                sos[0, :3] = b
                sos[0, 3:] = a
                self._notch_sos = sos
            except Exception:
                self._notch_sos = None
        else:
            self._notch_sos = None
        self.reset_state()

    def reset_state(self):
        n = self.n_channels
        self._hp_zi = np.zeros((self._hp_sos.shape[0], 2, n)) if self._hp_sos is not None else None
        self._lp_zi = np.zeros((self._lp_sos.shape[0], 2, n)) if self._lp_sos is not None else None
        self._notch_zi = np.zeros((self._notch_sos.shape[0], 2, n)) if self._notch_sos is not None else None

    def apply(self, x):
        """Apply enabled filters.  Vectorised across channels via axis=0 — one
        C-level sosfilt call per filter stage instead of a Python for-loop."""
        if x.size == 0:
            return x
        n_ch = min(x.shape[1], self.n_channels)
        y = x.copy()
        if self._hp_sos is not None:
            y[:, :n_ch], self._hp_zi[:, :, :n_ch] = sosfilt(
                self._hp_sos, y[:, :n_ch], axis=0, zi=self._hp_zi[:, :, :n_ch])
        if self._lp_sos is not None:
            y[:, :n_ch], self._lp_zi[:, :, :n_ch] = sosfilt(
                self._lp_sos, y[:, :n_ch], axis=0, zi=self._lp_zi[:, :, :n_ch])
        if self._notch_sos is not None:
            y[:, :n_ch], self._notch_zi[:, :, :n_ch] = sosfilt(
                self._notch_sos, y[:, :n_ch], axis=0, zi=self._notch_zi[:, :, :n_ch])
        return y

    def set_n_channels(self, n):
        self.n_channels = n
        self.reset_state()

    def set_fs(self, fs):
        self.fs = fs
        self._rebuild_all()
