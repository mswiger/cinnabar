from cinnabar.application import Configuration
from cinnabar.module import Module
from gi.repository import Gtk


class DummyModule(Module):
    def __init__(self, config: Configuration):
        return

    def widget(self) -> Gtk.Widget:
        return Gtk.Label(label="Hello")
