from typing import Callable

from gi.repository import GLib


def glib_call_in_main(fn: Callable):
    def wrapper(*args, **kwargs):
        GLib.idle_add(fn, *args, **kwargs)
    return wrapper
