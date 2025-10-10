from __future__ import annotations

import curses
import curses.ascii

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


def from_xml(root: Element, r: Record):
    for e in root.xpath('./outline'):
        d = dict(e.attrib)
        if 'text' not in d:
            continue
        r2 = r.add(d)
        if 'URL' not in d:
            from_xml(e, r2)


def from_url(url: str, r: Record):
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

        self.create_windows()

    def create_windows(self):
        '''
        radio-curses v...
        records ...
        '''
        maxy, maxx = self.screen_size

        rows, cols = (maxy - 2, maxx)

        win = self.screen.derwin(rows, cols, 2, 0)
        self.win = List(win, self, current_color=curses.color_pair(1) | curses.A_BOLD)

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
        radio = r.d['text']
        if r.isdir():
            return f'{radio}/'
        return radio

    def records_len(self) -> int:
        return len(self.record)

    def refresh_all(self):
        self.screen.erase()

        s = f'radio-curses v{__version__} (h - Help)'
        _, cols = self.win.win.getmaxyx()
        win_addstr(self.screen, 0, 0, s[:cols])

        self.win.refresh()
        self.screen.refresh()

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

    def start_player(self, i: int):
        if not (r := self.get_record(i)):
            return
        self.record.pos = (self.win.cur, self.win.idx)
        if r.isaudio():
            self.mpv.start(r.d['URL'])

    def run(self):
        try:
            self.refresh_all()
            self.input_loop()
        finally:
            self.mpv.stop()

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
