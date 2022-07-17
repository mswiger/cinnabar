from typing import Any, Callable, Iterable, Optional

from gi.repository import GLib


def find(fn: Callable, iterable: Iterable) -> Optional[Any]:
    for i in iterable:
        if fn(i):
            return i
    return None

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


def str_to_bool(string: str) -> bool:
    if string.lower() == "true":
        return True
    return False
