from gi.repository import Gtk

from cinnabar.bar import Bar, WidgetPlugin


class DummyModule(WidgetPlugin):
    def __init__(self, bar: Bar, config: dict) -> None:
        return

    def widget(self) -> Gtk.Widget:
        return Gtk.Label(label="Hello")
