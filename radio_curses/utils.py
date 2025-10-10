import io
import json
import os
import shutil
import socket
import subprocess
import time


class Mpv:
    def __init__(self):
        self.socket = os.path.expanduser('~/tmp/mpv.socket')
        mpv = shutil.which('mpv') or '/usr/bin/mpv'
        self.cmd = [mpv, '--terminal=no', f'--input-ipc-server={self.socket}']
        self.proc = None

    def stop(self):
        if self.proc is not None:
            self.proc.terminate()
            self.proc.wait()
        if os.path.exists(self.socket):
            os.remove(self.socket)
        self.proc = None

    def start(self, url: str):
        self.stop()
        if url.startswith('http://'):
            url = f'{url[:4]}s{url[4:]}'  # https://
        cmd: list[str] = self.cmd + [url]
        self.proc = subprocess.Popen(  # pylint: disable=consider-using-with
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL
        )

    def send_command(self, cmd: dict) -> dict:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        while True:
            if not os.path.exists(self.socket):
                time.sleep(2)
                continue
            try:
                client.connect(self.socket)
                break
            except ConnectionRefusedError:
                time.sleep(2)
                continue
        bytes_ = json.dumps(cmd).encode('utf-8') + b'\n'
        try:
            client.sendall(bytes_)
            return socket2json(client)
        finally:
            client.close()


def socket2json(s: socket.socket) -> dict:
    with io.BytesIO() as fp:
        while True:
            resp = s.recv(1024)
            fp.write(resp)
            if resp.endswith(b'\n'):
                break
        response = fp.getvalue().decode('utf-8')
        return json.loads(response)
