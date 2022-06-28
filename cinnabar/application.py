import gi
import signal

gi.require_version('Gtk', '3.0')
gi.require_version('GtkLayerShell', '0.1')

from gi.repository import Gio, GLib, Gtk, GtkLayerShell

class Application(Gtk.Application):
    def __init__(self, *args, **kwargs):
        super().__init__(
            *args,
            application_id="dev.swiger.Cinnabar",
            flags=Gio.ApplicationFlags.NON_UNIQUE,
            **kwargs,
        )
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, self.quit)
    
    def do_startup(self):
        Gtk.Application.do_startup(self)

    def do_activate(self):
        orientation = Gtk.Orientation.HORIZONTAL

        beginning_box = Gtk.Box(orientation=orientation, spacing=0)
        beginning_box.set_halign(Gtk.Align.START)
        beginning_box.set_valign(Gtk.Align.START)

        middle_box = Gtk.Box(orientation=orientation, spacing=0)
        middle_box.set_halign(Gtk.Align.CENTER)
        middle_box.set_valign(Gtk.Align.CENTER)

        end_box = Gtk.Box(orientation=orientation, spacing=0)
        end_box.set_halign(Gtk.Align.END)
        end_box.set_valign(Gtk.Align.END)
        
        main_box = Gtk.Box(orientation=orientation, spacing=0)
        main_box.set_homogeneous(True)
        main_box.add(beginning_box)
        main_box.add(middle_box)
        main_box.add(end_box)

        # TODO: delete
        label = Gtk.Label(label='GTK Layer Shell with Python!')
        label3 = Gtk.Label(label='this here is the middle')
        label2 = Gtk.Label(label='pizza pizza pizza')
        beginning_box.add(label)
        middle_box.add(label3)
        end_box.add(label2)

        window = Gtk.Window(application=self, decorated=False)
        window.connect("destroy", Gtk.main_quit)
        window.add(main_box)

        GtkLayerShell.init_for_window(window)
        GtkLayerShell.auto_exclusive_zone_enable(window)
        GtkLayerShell.set_anchor(window, GtkLayerShell.Edge.BOTTOM, True)
        GtkLayerShell.set_anchor(window, GtkLayerShell.Edge.LEFT, True)
        GtkLayerShell.set_anchor(window, GtkLayerShell.Edge.RIGHT, True)
        
        window.show_all()
