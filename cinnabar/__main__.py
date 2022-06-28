from cinnabar.application import Application
import gi
import sys

gi.require_version("Gtk", "3.0")
gi.require_version("GtkLayerShell", "0.1")

app = Application()
app.run(sys.argv)
