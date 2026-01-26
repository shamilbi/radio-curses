from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
from contextlib import contextmanager
from subprocess import PIPE, Popen
from threading import Event


@contextmanager
def unix_socket(timeout: float = 2.0):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        yield s
    finally:
        s.close()


class Mpv:
    def __init__(self):
        self.socket = os.path.expanduser('~/tmp/mpv.socket')
        mpv = shutil.which('mpv') or '/usr/bin/mpv'
        self.cmd = [mpv, '--terminal=no', f'--input-ipc-server={self.socket}']
        self.proc = None
        self.url = None

    def stop(self):
        if self.proc is not None:
            self.proc.terminate()
            self.proc.wait()
        if os.path.exists(self.socket):
            os.remove(self.socket)
        self.proc = None

    def start(self, url: str):
        if not url:
            return
        self.stop()
        if url.startswith('http://'):
            url = f'{url[:4]}s{url[4:]}'  # https://
        cmd: list[str] = self.cmd + [url]
        self.proc = subprocess.Popen(  # pylint: disable=consider-using-with
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL
        )
        self.url = url

    def toggle(self) -> int:
        # -1: stop, 0: nothing, 1: start
        rt = 0
        if self.proc:
            self.stop()
            rt = -1
        elif self.url:
            self.start(self.url)
            rt = 1
        return rt

    def send_command(self, cmd: dict, stop: Event) -> dict:
        with unix_socket() as client:
            while True:
                if not os.path.exists(self.socket):
                    if stop.wait(2):
                        return {}
                    continue
                try:
                    client.connect(self.socket)
                    break
                except (ConnectionError, socket.timeout):
                    if stop.wait(2):
                        return {}
                    continue
            bytes_ = json.dumps(cmd).encode('utf-8') + b'\n'
            try:
                client.sendall(bytes_)
                return socket2json(client)
            except (socket.timeout, UnicodeDecodeError):
                return {}

    def get_metadata(self, stop: Event) -> dict:
        return self.send_command({'command': ['get_property', 'metadata']}, stop)


def socket2json(s: socket.socket) -> dict:
    try:
        with s.makefile(encoding='utf-8', errors='replace') as fp:
            return json.loads(fp.readline())
    except (ConnectionResetError, json.JSONDecodeError):
        return {}


def str2clipboard(s: str):
    with Popen(['xsel', '-b', '-i'], stdout=PIPE, stdin=PIPE, stderr=PIPE, text=True) as p:
        p.communicate(input=s)
