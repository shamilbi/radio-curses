from __future__ import annotations

import curses
import curses.ascii
import sys
from threading import Event, RLock, Thread

import requests  # type: ignore[import-untyped]
from lxml.etree import XML, Element  # type: ignore[import-untyped]  # pylint: disable=no-name-in-module

from . import __version__
from .curses_utils import App, List, win_addstr, win_help
from .utils import Mpv

HELP = [
    ("h", "This help screen"),
    ("q, Esc", "Quit the program"),
    ("j, Down", "Move selection down"),
    ("k, Up", "Move selection up"),
    ("PgUp", "Page up"),
    ("PgDown", "Page down"),
    ("g, Home", "Move to first item"),
    ("G, End", "Move to last item"),
    ("Enter", "Play audio"),
]


class Record:
    def __init__(self, d: dict, parent: Record | None = None):
        self.d = d
        self.parent = parent

        self.children: list[Record] = []  # to view in a window
        self.pos: tuple[int, int] = (0, 0)  # position: (cur, idx)

    def add(self, d: dict) -> Record:
        r = Record(d, self)
        self.children.append(r)
        return r

    def isdir(self) -> bool:
        if self.children:
            return True
        if 'URL' not in self.d:
            return True
        if self.d.get('type') == 'link':
            return True
        return False

    def isaudio(self) -> bool:
        if self.isdir():
            return False
        if self.d.get('type') == 'audio' and 'URL' in self.d:
            return True
        return False

    def __len__(self):
        return len(self.children)

    def __bool__(self):
        return True

    def __getitem__(self, i: int) -> Record:
        return self.children[i]

    @property
    def text(self) -> str:
        return self.d['text']


def from_xml(root: Element, r: Record):
    for e in root.xpath('./outline'):
        d = dict(e.attrib)
        if 'text' not in d:
            continue
        r2 = r.add(d)
        if 'URL' not in d:
            from_xml(e, r2)


def from_url(url: str, r: Record):
    if url.startswith('http://'):
        url = f'{url[:4]}s{url[4:]}'  # https://
    resp = requests.get(url)  # pylint: disable=missing-timeout
    xml = XML(resp.content)
    for e in xml.xpath('/opml/body'):
        from_xml(e, r)


class Main(App):  # pylint: disable=too-many-instance-attributes,too-many-public-methods
    def __init__(self, screen):
        super().__init__(screen)

        curses.init_pair(1, curses.COLOR_CYAN, curses.COLOR_BLACK)

        self.record = Record({})  # root record
        from_url('https://opml.radiotime.com/', self.record)

        self.mpv = Mpv()
        self.radio = ''

        self.status_lock = RLock()
        self.thread_meta = None
        self.stop_meta = Event()
        self.refresh_meta = Event()

        self.create_windows()

    def create_windows(self):
        '''
        radio-curses v...

        records ...
        ------
        status
        '''
        maxy, maxx = self.screen_size

        rows, cols = (maxy - 4, maxx)

        win = self.screen.derwin(rows, cols, 2, 0)
        self.win = List(win, self, current_color=curses.color_pair(1) | curses.A_BOLD)

        # status
        self.win3 = self.screen.derwin(2, cols, maxy - 2, 0)

    def refresh_win_deps(self):
        pass

    def get_record(self, i: int) -> Record | None:
        len_ = len(self.record)
        if not i < len_:
            return None
        return self.record[i]

    def get_record_str(self, i: int) -> str:
        if not (r := self.get_record(i)):
            return ''
        if r.isdir():
            return f'{r.text}/'
        return r.text

    def records_len(self) -> int:
        return len(self.record)

    def refresh_all(self):
        self.screen.erase()

        s = f'radio-curses v{__version__} (h - Help)'
        _, cols = self.win.win.getmaxyx()
        win_addstr(self.screen, 0, 0, s[:cols])

        self.win.refresh()

        self.screen.refresh()

        ch = curses.ACS_HLINE
        self.win3.border(' ', ' ', ch, ' ', ch, ch, ' ', ' ')
        self.win3.refresh()
        self.refresh_meta.set()

    def right(self, i: int):
        if not (r := self.get_record(i)):
            return
        self.record.pos = (self.win.cur, self.win.idx)
        if r.isdir():
            self.record = r
            if not self.record.children and 'URL' in r.d:
                from_url(r.d['URL'], self.record)
            self.win.cur, self.win.idx = self.record.pos
            self.win.refresh()

    def left(self):
        if not self.record.parent:
            return
        self.record.pos = (self.win.cur, self.win.idx)
        self.record = self.record.parent
        self.win.cur, self.win.idx = self.record.pos
        self.win.refresh()

    def poll_metadata(self, stop: Event, refresh: Event):
        prev_song = None
        while True:
            if stop.wait(5):
                return
            d = self.mpv.get_metadata(stop)
            d2 = d.get('data')
            if not d2:
                continue
            song = d2.get('icy-title')
            if song:
                song = song.rstrip()
                if prev_song != song or refresh.is_set():
                    prev_song = song
                    self.status(f'{self.radio}: {song}')
                    refresh.clear()
            elif refresh.is_set():
                prev_song = None
                self.status(f'{self.radio}')
                refresh.clear()

    def start_player(self, i: int):
        if not (r := self.get_record(i)):
            return
        self.record.pos = (self.win.cur, self.win.idx)
        if r.isaudio():
            self.radio = r.text
            self.status(f'Start {self.radio} ...')
            self.mpv.start(r.d['URL'])
            if not self.thread_meta:
                self.thread_meta = Thread(target=self.poll_metadata, args=(self.stop_meta, self.refresh_meta))
                self.thread_meta.start()

    def status(self, s: str):
        with self.status_lock:
            _, cols = self.win3.getmaxyx()
            win = self.win3.derwin(1, cols, 1, 0)
            win.erase()
            win_addstr(win, 0, 0, s)
            win.refresh()

    def shutdown(self, *_):
        self.status('Closing ...')
        if self.thread_meta and self.thread_meta.is_alive():
            self.stop_meta.set()
            self.thread_meta.join()
        self.mpv.stop()
        sys.exit(0)

    def run(self):
        self.refresh_all()
        self.input_loop()

    def input_loop(self):  # pylint: disable=too-many-branches,too-many-statements
        for char_ord in self.getch():
            char = chr(char_ord)

            if self.win.handle_input(char_ord):
                pass
            elif char_ord == curses.KEY_RIGHT:
                self.right(self.win.idx)
            elif char_ord == curses.KEY_LEFT:
                self.left()
            elif char_ord == curses.ascii.LF:  # Enter
                self.start_player(self.win.idx)
            elif char.upper() == 'H':  # Print help screen
                win_help(self.screen, HELP)
                self.refresh_all()


def main2(screen):
    app = Main(screen)
    app.run()


def main():
    curses.wrapper(main2)


if __name__ == '__main__':
    main()
