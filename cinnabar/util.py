from typing import Callable

from gi.repository import GLib


def glib_call_in_main(fn: Callable):
    # Wrap callable in a method that returns False to make it be removed from
    # event sources after being called by main thread.
    def inner(*args, **kwargs):
        fn(*args, **kwargs)
        return False

    # The actual wrapper to be called returned by the decorator.
    def wrapper(*args, **kwargs):
        GLib.idle_add(inner, *args, **kwargs)

    return wrapper
