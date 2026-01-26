from __future__ import annotations

import curses
import curses.ascii
import sys
from threading import Event, RLock, Thread

from . import __version__
from .curses_utils import App, win_addstr, win_help
from .curses_utils.list1m import List1m, ListProto1m
from .db import Favourites, Record, from_url
from .utils import Mpv, str2clipboard

HELP = [
    ("h", "This help screen"),
    ("q, Esc", "Quit the program"),
    ("j, Down", "Move selection down"),
    ("k, Up", "Move selection up"),
    ("PgUp", "Page up"),
    ("PgDown", "Page down"),
    ("g, Home", "Move to first item"),
    ("G, End", "Move to last item"),
    ("Right, Left", "Move to/from a directory"),
    ("Shift-{Up,Down}", "Move a record up/down"),
    ("Insert", "Add to Favourites"),
    ("Delete", "Delete from Favourites"),
    ("Enter", "Play selected radio"),
    ("Space", "Stop/Resume"),
    ("Ctrl-L", "Copy URL to clipboard"),
]


class Main(App, ListProto1m):  # pylint: disable=too-many-instance-attributes,too-many-public-methods
    def __init__(self, screen):
        super().__init__(screen)

        curses.init_pair(1, curses.COLOR_CYAN, curses.COLOR_BLACK)

        self.record = Record({})  # root record
        self.fav = Favourites(self.record)
        self.fav.load_from_home()
        self.record.children.append(self.fav)
        from_url('https://opml.radiotime.com/', self.record)

        self.mpv = Mpv()
        self.radio = ''

        self.status_lock = RLock()
        self.thread_meta = None
        self.stop_meta = Event()
        self.status_str = ''

        self.create_windows()

    def create_windows(self):
        '''
        radio-curses v...

        records ...
        ------
        status
        '''
        maxy, maxx = self.screen_size

        rows, cols = (maxy - 4, maxx - 2)

        win = self.screen.derwin(rows, cols, 2, 1)
        self.win = List1m(win, self, current_color=curses.color_pair(1) | curses.A_BOLD)

        # status
        self.win3 = self.screen.derwin(1, maxx, maxy - 1, 0)

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
        win_addstr(self.screen, 0, 1, s)
        self.screen.refresh()

        maxy, maxx = self.screen_size
        win = self.screen.derwin(maxy - 2, maxx, 1, 0)
        win.erase()
        win.box()
        win.refresh()

        self.win.refresh()

        self.status(self.status_str, force=True)

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

    def poll_metadata(self, stop: Event):
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
                s = f'{self.radio}: {song}'
            else:
                s = f'{self.radio}'
            self.status(s)

    def start_player(self, i: int):
        if not (r := self.get_record(i)):
            return
        self.record.pos = (self.win.cur, self.win.idx)
        if r.isaudio():
            self.radio = r.text
            self.status(f'Start {self.radio} ...')
            self.mpv.start(r.d['URL'])
            if not self.thread_meta:
                self.thread_meta = Thread(target=self.poll_metadata, args=(self.stop_meta,))
                self.thread_meta.start()

    def record_move_up(self, i: int) -> bool:
        return self.record.move_child_up(i)

    def record_move_down(self, i: int) -> bool:
        return self.record.move_child_down(i)

    def add_to_favourites(self, i: int):
        if not (r := self.get_record(i)):
            return
        if self.fav.add_record(r):
            self.status('Added to Favourites')

    def del_favourite(self, i: int):
        if self.record != self.fav or not self.get_record(i):
            return
        del self.fav[i]
        self.win.refresh()

    def url2clipboard(self):
        if not (r := self.get_record(self.win.idx)):
            return
        if url := r.d.get('URL', None):
            str2clipboard(url)
            self.status(f'URL copied: {url}')
        else:
            self.status('URL is empty')

    def status(self, s: str, force=False):
        if force or self.status_str != s:
            with self.status_lock:
                self.win3.erase()
                win_addstr(self.win3, 0, 1, s)
                self.win3.refresh()
                self.status_str = s

    def shutdown(self, *_):
        self.status('Closing ...')
        self.fav.save_to_home()
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
            elif char_ord == curses.ascii.SP:  # Space
                rt = self.mpv.toggle()
                if rt > 0:
                    self.status(f'Start {self.radio} ...')
                elif rt < 0:
                    self.status(f'Stop {self.radio} ...')
            elif char_ord == curses.KEY_IC:  # insert
                self.add_to_favourites(self.win.idx)
            elif char_ord == curses.KEY_DC:  # delete
                self.del_favourite(self.win.idx)
            elif char.upper() == 'H':  # Print help screen
                win_help(self.screen, HELP)
                self.refresh_all()
            elif char_ord == 12:  # ^L
                self.url2clipboard()


def main2(screen):
    app = Main(screen)
    app.run()


def main():
    curses.wrapper(main2)


if __name__ == '__main__':
    main()
