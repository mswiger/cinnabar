from gi.repository import Gtk

from cinnabar.application import Configuration
from cinnabar.plugin import WidgetPlugin


class DummyModule(WidgetPlugin):
    def __init__(self, config: Configuration):
        return

    def widget(self) -> Gtk.Widget:
        return Gtk.Label(label="Hello")
