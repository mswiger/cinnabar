from abc import ABC, abstractmethod

from gi.repository import Gtk


class Module(ABC):
    # TODO: Should config be module-specific or full app config?
    def __init__(self, config: dict):
        """Receive Cinnabar configuration to be used for building the module"""
        self.config = config
        return

    @abstractmethod
    def widget(self) -> Gtk.Widget:
        """Return a GTK Widget representing the module"""
        return Gtk.Widget()
