# -*- coding: utf-8 -*-
"""
LabRecorder RCS (Remote Control Server) client.

LabRecorder exposes a TCP-based RCS on port 22345 (default) that accepts
text commands (one per line, newline-terminated) and returns JSON status.

Command set:
    select_all               - select all visible streams
    select "stream_name"     - select a specific stream
    filename <study_name>    - set study/filename
    path <root_directory>    - set save directory
    start                    - start recording
    stop                     - stop recording
    update                   - request status JSON
    exit                     - close LabRecorder
"""
import json
import os
import socket
import subprocess
import sys
import time
import threading

# Defaults
RCS_HOST = '127.0.0.1'
RCS_PORT = 22345
CONNECT_TIMEOUT = 5.0
RECV_BUFSIZE = 4096


class LabRecorderController:
    """Launch LabRecorder and control recording via RCS TCP commands."""

    def __init__(self, labrecorder_exe, rcs_port=RCS_PORT):
        self._exe = labrecorder_exe
        self._rcs_port = rcs_port
        self._proc = None            # subprocess.Popen
        self._sock = None            # socket to RCS
        self._connected = False
        self._recording = False
        self._last_status = {}

    # ==================================================================
    # Process management
    # ==================================================================

    @property
    def running(self):
        return self._proc is not None and self._proc.poll() is None

    def launch(self, study_name=None, save_path=None):
        """Launch LabRecorder.exe as a separate process."""
        if self.running:
            return True

        if not os.path.exists(self._exe):
            raise FileNotFoundError(f'LabRecorder not found: {self._exe}')

        cmd = [self._exe]
        # RCS is on by default; use --rcs-port to be explicit
        cmd += ['--rcs-port', str(self._rcs_port)]

        try:
            creationflags = 0
            if sys.platform == 'win32':
                creationflags = subprocess.CREATE_NEW_CONSOLE
            self._proc = subprocess.Popen(
                cmd,
                cwd=os.path.dirname(self._exe),
                creationflags=creationflags if sys.platform == 'win32' else 0,
            )
        except Exception as e:
            print(f'[LabRecorder] failed to launch: {e}', flush=True)
            return False

        print(f'[LabRecorder] launched (PID={self._proc.pid})', flush=True)

        # Wait for RCS to become available
        if not self._wait_for_rcs():
            print('[LabRecorder] RCS not available after launch', flush=True)
            return True  # still launched, just not yet connected

        # Apply initial parameters
        if save_path:
            self.set_path(save_path)
        if study_name:
            self.set_filename(study_name)
        self.select_all()

        return True

    def terminate(self):
        """Gracefully close LabRecorder."""
        self.stop_recording()
        self._disconnect()
        if self._proc and self._proc.poll() is None:
            try:
                self._send_cmd('exit')
                time.sleep(0.5)
            except Exception:
                pass
            if self._proc.poll() is None:
                self._proc.terminate()
                self._proc.wait(timeout=5)
        print('[LabRecorder] terminated', flush=True)

    # ==================================================================
    # RCS connection
    # ==================================================================

    def _connect(self):
        """Connect to the LabRecorder RCS socket."""
        if self._sock is not None:
            return True
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(CONNECT_TIMEOUT)
            s.connect((RCS_HOST, self._rcs_port))
            s.settimeout(2.0)
            self._sock = s
            self._connected = True
            return True
        except (ConnectionRefusedError, OSError) as e:
            return False

    def _disconnect(self):
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        self._connected = False

    def _wait_for_rcs(self, max_wait=15.0):
        """Poll until RCS socket is available."""
        start = time.time()
        while time.time() - start < max_wait:
            if self._connect():
                print(f'[LabRecorder] RCS connected (port {self._rcs_port})', flush=True)
                return True
            time.sleep(0.5)
        return False

    def _send_cmd(self, cmd):
        """Send a command string and return the response (str or None)."""
        if not self._connected and not self._connect():
            return None
        try:
            self._sock.sendall((cmd + '\n').encode('utf-8'))
            resp = self._sock.recv(RECV_BUFSIZE)
            return resp.decode('utf-8').strip()
        except (OSError, socket.timeout) as e:
            self._disconnect()
            return None

    # ==================================================================
    # RCS Commands
    # ==================================================================

    def select_all(self):
        return self._send_cmd('select_all')

    def select_stream(self, name):
        return self._send_cmd(f'select "{name}"')

    def set_filename(self, study_name):
        return self._send_cmd(f'filename {study_name}')

    def set_path(self, root_path):
        # Normalize backslashes for LabRecorder
        p = root_path.replace('\\', '/')
        os.makedirs(p, exist_ok=True)
        return self._send_cmd(f'path "{p}"')

    def start_recording(self):
        """Start recording. Returns True on success."""
        resp = self._send_cmd('start')
        if resp is not None:
            self._recording = True
        return resp

    def stop_recording(self):
        """Stop recording. Returns True on success."""
        resp = self._send_cmd('stop')
        if resp is not None:
            self._recording = False
        return resp

    def update(self):
        """Request status update. Returns parsed JSON dict or {}."""
        resp = self._send_cmd('update')
        if resp is None:
            return {}
        try:
            status = json.loads(resp)
        except json.JSONDecodeError:
            status = {}
        self._last_status = status
        self._recording = status.get('isRecording', False)
        return status
