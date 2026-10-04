# -*- coding: utf-8 -*-
"""
LSL stream discovery and threaded data reception.
Multi-version pylsl compatible.
"""
import time
import threading
import numpy as np
import pylsl
from PyQt5.QtCore import QObject, pyqtSignal


def _resolve_by_name(name, timeout=1.0):
    # Method 1: resolve_byprop (may not support timeout kwarg)
    try:
        streams = pylsl.resolve_byprop('name', name, timeout=timeout)
        if streams:
            return streams[0]
    except (TypeError, AttributeError):
        pass

    try:
        streams = pylsl.resolve_byprop('name', name)
        if streams:
            return streams[0]
    except (TypeError, AttributeError):
        pass

    # Method 2: resolve_streams + manual filter (always works)
    try:
        all_s = pylsl.resolve_streams(timeout=timeout)
    except TypeError:
        all_s = pylsl.resolve_streams()
    for info in all_s:
        if info.name() == name:
            return info
    return None


def _resolve_all(timeout=1.0):
    try:
        return pylsl.resolve_streams(timeout=timeout)
    except TypeError:
        return pylsl.resolve_streams()


class StreamReceiver(QObject):
    evt_data = pyqtSignal(str, np.ndarray, np.ndarray)
    evt_marker = pyqtSignal(str, np.ndarray, np.ndarray)
    evt_streams_changed = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self._inlets = {}
        self._info_map = {}
        self._running = False
        self._thread = None
        self._wanted_streams = {}

    def scan_streams(self):
        return _resolve_all(timeout=1.0)

    def subscribe(self, stream_name, stream_type='Signal'):
        print(f'[StreamReceiver] subscribe: "{stream_name}" type={stream_type}', flush=True)
        self._wanted_streams[stream_name] = stream_type
        ok = self._connect_stream(stream_name)
        if ok:
            print(f'[StreamReceiver] OK: {stream_name}', flush=True)
        else:
            print(f'[StreamReceiver] FAILED: stream "{stream_name}" not found', flush=True)
        return ok

    def subscribe_info(self, stream_name, info, stream_type='Signal'):
        """Subscribe using a *pre-resolved* StreamInfo — no re-resolution.
        Call this from the GUI thread after resolving the stream in a background
        thread, to avoid a second blocking pylsl.resolve_*() call."""
        print(f'[StreamReceiver] subscribe_info: "{stream_name}" type={stream_type}', flush=True)
        self._wanted_streams[stream_name] = stream_type
        self._info_map[stream_name] = info
        is_marker = (stream_type == 'Marker')
        flags = pylsl.proc_clocksync if is_marker else pylsl.proc_clocksync
        inlet = pylsl.StreamInlet(info, max_buflen=360, processing_flags=flags)
        self._inlets[stream_name] = inlet
        return True

    def unsubscribe(self, stream_name):
        self._wanted_streams.pop(stream_name, None)
        if stream_name in self._inlets:
            del self._inlets[stream_name]
        self._info_map.pop(stream_name, None)

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name='stream-recv')
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    def stream_info(self, name):
        return self._info_map.get(name, None)

    def _connect_stream(self, stream_name):
        info = _resolve_by_name(stream_name, timeout=2.0)
        if info is None:
            print(f'[StreamReceiver] "{stream_name}" NOT FOUND', flush=True)
            return False
        self._info_map[stream_name] = info
        is_marker = self._wanted_streams.get(stream_name) == 'Marker'
        flags = pylsl.proc_clocksync if is_marker else pylsl.proc_clocksync
        inlet = pylsl.StreamInlet(info, max_buflen=360, processing_flags=flags)
        self._inlets[stream_name] = inlet
        return True

    def _loop(self):
        while self._running:
            t0 = time.time()
            self._pull_all()
            time.sleep(max(0, 0.05 - (time.time() - t0)))

    def _pull_all(self):
        for name, inlet in list(self._inlets.items()):
            try:
                samples, timestamps = inlet.pull_chunk(timeout=0.0, max_samples=256)
            except Exception:
                continue
            if not timestamps:
                continue
            ts = np.asarray(timestamps)
            y = np.array(samples, dtype=np.float64)
            stype = self._wanted_streams.get(name, 'Signal')
            if stype == 'Marker':
                self.evt_marker.emit(name, ts, y)
            else:
                self.evt_data.emit(name, ts, y)
