from __future__ import annotations

from pathlib import Path

import requests  # type: ignore[import-untyped]
from lxml.etree import XML  # type: ignore[import-untyped]  # pylint: disable=no-name-in-module
from lxml.etree import Element, ElementTree, SubElement, XMLSyntaxError  # pylint: disable=no-name-in-module
from xdg_base_dirs import xdg_data_home

from .utils import RadioException


class Record:
    def __init__(self, d: dict, parent: Record | None = None):
        self.d = d
        self.parent = parent

        self.children: list[Record] = []  # to view in a window
        self.pos: tuple[int, int] = (0, 0)  # position: (cur, idx)

    def add_dict(self, d: dict) -> Record:
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

    def __delitem__(self, i: int):
        del self.children[i]

    @property
    def text(self) -> str:
        return self.d['text']

    def move_child_up(self, i: int) -> bool:
        l = self.children
        if 0 < i < len(l):
            r = l[i]
            del l[i]
            l.insert(i - 1, r)
            return True
        return False

    def move_child_down(self, i: int) -> bool:
        l = self.children
        if 0 <= i < len(l) - 1:
            r = l[i]
            del l[i]
            l.insert(i + 1, r)
            return True
        return False


def from_xml(root: Element, r: Record):
    for e in root.xpath('./outline'):
        d = dict(e.attrib)
        if 'text' not in d:
            continue
        r2 = r.add_dict(d)
        if 'URL' not in d:
            from_xml(e, r2)


def from_url(url: str, r: Record):
    if url.startswith('http://'):
        url = f'{url[:4]}s{url[4:]}'  # https://
    try:
        resp = requests.get(url)  # pylint: disable=missing-timeout
        xml = XML(resp.content)
        for e in xml.xpath('/opml/body'):
            from_xml(e, r)
    except (XMLSyntaxError, requests.RequestException) as e:
        # bad response from url
        # r.children.clear()
        raise RadioException from e


def from_file(file: Path, r: Record):
    with open(file, 'rb') as fp:
        xml = XML(fp.read())
    for e in xml.xpath('/opml/body'):
        from_xml(e, r)


class Favourites(Record):
    def __init__(self, parent: Record):
        super().__init__({'text': 'Favourites'}, parent)

    def load_from_home(self):
        for i in ('radio-curses', 'curseradio'):
            file = xdg_data_home() / i / 'favourites.opml'
            if file.is_file():
                from_file(file, self)
                return

    def save_to_home(self):
        dir_ = xdg_data_home() / 'radio-curses'
        dir_.mkdir(mode=0o755, exist_ok=True)
        file = dir_ / 'favourites.opml'

        xml = Element("opml")
        body = SubElement(xml, "body")
        for c in self.children:
            e = Element("outline", attrib=c.d)
            body.append(e)
        opml = ElementTree(xml)
        opml.write(str(file))

    def add_record(self, r: Record) -> bool:
        if r.parent == self or not r.isaudio():
            return False
        # find the same URL
        url = r.d['URL']
        for i, r2 in enumerate(self.children):
            if r2.d['URL'] == url:
                # replace
                self.children[i] = r
                return False
        self.children.append(r)
        return True
