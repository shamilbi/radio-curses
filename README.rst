|pypi| |github|

radio-curses
=============

Internet radio in the terminal. A fork of `curseradio`_.

radio-curses is a `curses` interface for browsing and playing an `OPML`_ directory of internet radio streams.
It is designed to use the *tunein* directory found at `opml.radiotime.com`_, but could be adapted to others.

Audio playback uses `mpv`_. radio-curses requires `python3` and the libraries `requests`_, `lxml`_ and `xdg-base-dirs`_.

|demo|

The current hotkeys are:
    * h: help screen
    * q, Esc: Quit the program
    * j, Down: Move selection down
    * k, Up: Move selection up
    * PgUp: Page up
    * PgDown: Page down
    * g, Home: Move to first item
    * G, End: Move to last item
    * Shift-Up,Down: Move a record up/down
    * Insert: Add to Favourites
    * Delete: Delete from Favourites
    * Enter: Play selected radio
    * Space: Stop/Resume
    * Ctrl-L: Copy URL to clipboard

.. |pypi| image:: https://img.shields.io/pypi/v/radio-curses
          :target: https://pypi.org/project/radio-curses/
.. |github| image:: https://img.shields.io/github/v/tag/shamilbi/radio-curses?label=github
            :target: https://github.com/shamilbi/radio-curses/
.. |demo| image:: https://asciinema.org/a/NB9Gn8NcN3tKxB28ue86KJLmW.png
          :target: https://asciinema.org/a/NB9Gn8NcN3tKxB28ue86KJLmW?autoplay=1
          :width: 100%
.. _curseradio: https://github.com/chronitis/curseradio
.. _OPML: https://en.wikipedia.org/wiki/OPML
.. _opml.radiotime.com: https://opml.radiotime.com/
.. _mpv: https://github.com/mpv-player/mpv
.. _requests: https://pypi.org/project/requests/
.. _lxml: https://pypi.org/project/lxml/
.. _xdg-base-dirs: https://pypi.org/project/xdg-base-dirs/
