from __future__ import annotations

import json
from pathlib import Path

import requests  # type: ignore[import-untyped]

# pylint: disable=no-name-in-module
from lxml.etree import (  # type: ignore[import-untyped]
    XML,
    Element,
    ElementTree,
    SubElement,
    XMLSyntaxError,
)
from platformdirs import user_data_dir

from . import __project_name__
from .utils import RadioException, glob_file

USER_DATA_DIR = Path(user_data_dir(), __project_name__)
USER_DATA_DIR.mkdir(mode=0o755, exist_ok=True)


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
        return self.d.get('type') == 'link'

    def isaudio(self) -> bool:
        if self.isdir():
            return False
        return self.d.get('type') == 'audio' and 'URL' in self.d

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
        resp = requests.get(url, timeout=5)
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


def from_json(file: Path, r: Record):
    '''
    from Radio Catalog json:
        "source": "radio_browser_github",
        "name": "MANGORADIO",
        "url": "https://mangoradio.stream.laut.fm/mangoradio",
        "url_resolved": "https://mangoradio.stream.laut.fm/mangoradio",
        "homepage": "https://mangoradio.de/",
        "favicon": "https://mangoradio.de/wp-content/uploads/cropped-Logo-192x192.webp",
        "countrycode": "DE",
        "state": "Rheinland-Pfalz",
        "language": "english,german",
        "tags": "music,variety",
        "codec": "MP3",
        "bitrate": 128,
    '''
    l = []
    with open(file, 'r', encoding='utf-8') as fp:
        l = json.load(fp)  # list of dict
    for d in l:
        name = d.get('name')
        url = d.get('url')
        if not name or not url:
            continue
        # name
        cc = d.get('countrycode')
        state = d.get('state')
        if cc and state:
            name += f' ({cc}, {state})'
        elif cc:
            name += f' ({cc})'
        elif state:
            name += f' ({state})'
        d2 = {
            'text': name,
            'URL': d['url'],
            'type': 'audio',
        }
        r.add_dict(d2)


def from_m3u(file: Path, r: Record):
    '''
    #EXTURL:http://relay.181.fm:8072/;
    #EXTINF: Studio 181
    http://relay.181.fm:8072/;
    '''
    extinf_prefix = '#EXTINF:'
    with open(file, 'r', encoding='utf-8') as fp:
        find_extinf = True
        name = ''
        for line in fp:
            if not find_extinf:
                if line.startswith('#'):
                    # bad format
                    find_extinf = True
                    continue
                url = line.strip().rstrip(';')
                d = {
                    'text': name,
                    'URL': url,
                    'type': 'audio',
                }
                r2 = Record(d, r)
                r.children.append(r2)
            if not line.startswith(extinf_prefix):
                continue
            name = line[len(extinf_prefix) :].strip()
            if name.startswith('-1'):
                # -1....,name
                i = name.rfind(',')
                if i != -1:
                    name = name[i + 1 :]
                else:
                    name = name[2:]
            find_extinf = False


def load_dir(dir_: Path, r: Record):
    def add_child(d: dict, r: Record):
        r2 = Record(d, r)
        r.children.append(r2)

    # json
    for fpath in glob_file(dir_, '*.json'):
        d = {
            'text': fpath.name,
            'type': 'json',
            'fpath': fpath,
        }
        add_child(d, r)

    # m3u
    for fpath in glob_file(dir_, '*.m3u'):
        d = {
            'text': fpath.name,
            'type': 'm3u',
            'fpath': fpath,
        }
        add_child(d, r)

    # dirs
    for fpath in (x for x in dir_.iterdir() if x.is_dir()):
        d = {
            'text': fpath.name,
            'type': 'dir',
            'fpath': fpath,
        }
        add_child(d, r)


class Favourites(Record):
    def __init__(self, parent: Record):
        super().__init__({'text': 'Favourites'}, parent)

    def load_from_home(self):
        for i in (__project_name__, 'curseradio'):
            file = Path(user_data_dir(), i, 'favourites.opml')
            if file.is_file():
                from_file(file, self)
                return

    def save_to_home(self):
        file = USER_DATA_DIR / 'favourites.opml'

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
