from typing import Callable

from gi.repository import Gtk

from cinnabar.bar import Bar, WidgetPlugin
from cinnabar.sway import SwayClient, SwayEvent, SwayMessage, SwayResPayload
from cinnabar.util import find, glib_call_in_main, str_to_bool


class Workspace:
    FOCUSED_CLASS = "focused"
    PERSISTENT_CLASS = "persistent"
    URGENT_CLASS = "urgent"

    _button: Gtk.Button
    _name: str

    def __init__(
        self,
        name: str,
        on_press: Callable[[str], None],
        focused=False,
        persistent=False,
        urgent=False,
    ) -> None:
        self._name = name
        self._button = Gtk.Button(label=name, visible=True)
        self._button.set_relief(Gtk.ReliefStyle.NONE)
        self._button.connect("pressed", lambda _, n=name: on_press(n))

        self.focused = focused
        self.persistent = persistent
        self.urgent = urgent

    @property
    def button(self) -> Gtk.Button:
        return self._button

    @property
    def name(self) -> str:
        return self._name

    @property
    def focused(self) -> bool:
        return self.style_context.has_class(Workspace.FOCUSED_CLASS)

    @focused.setter
    def focused(self, new_val: bool) -> None:
        self._set_has_class(Workspace.FOCUSED_CLASS, new_val)

    @property
    def persistent(self) -> bool:
        return self.style_context.has_class(Workspace.PERSISTENT_CLASS)

    @persistent.setter
    def persistent(self, new_val: bool) -> None:
        self._set_has_class(Workspace.PERSISTENT_CLASS, new_val)

    @property
    def urgent(self) -> bool:
        return self.style_context.has_class(Workspace.URGENT_CLASS)

    @urgent.setter
    def urgent(self, new_val: bool) -> None:
        self._set_has_class(Workspace.URGENT_CLASS, new_val)

    @property
    def style_context(self) -> Gtk.StyleContext:
        return self._button.get_style_context()

    def _set_has_class(self, class_name: str, val: bool) -> None:
        if not self.style_context.has_class(class_name) and val is True:
            self.style_context.add_class(class_name)
        elif self.style_context.has_class(class_name) and val is False:
            self.style_context.remove_class(class_name)


class SwayWorkspaces(WidgetPlugin):
    _workspaces: list[Workspace] = []

    def __init__(self, bar: Bar, config: dict) -> None:
        self._bar = bar

        self._all_outputs = str_to_bool(config.get("all_outputs", ""))
        self._persistent_workspaces = config.get("persistent_workspaces", {})

        self._sway_client = SwayClient()
        self._button_box = Gtk.Box()
        self._sway_client.send(
            SwayMessage.GET_WORKSPACES,
            "",
            self._init_workspaces,
        )
        self._sway_client.subscribe(
            [SwayEvent.WORKSPACE],
            self._handle_sway_event,
        )

    def widget(self) -> Gtk.Widget:
        return self._button_box

    @glib_call_in_main
    def _init_workspaces(self, _, payload: SwayResPayload) -> None:
        # TODO: This is kind of clunky...
        if not isinstance(payload, list):
            return

        for workspace in payload:
            name = workspace.get("name", "")
            outputs = self._validate_outputs(workspace.get("output", []))

            if self._in_bar_output(outputs):
                self._add_workspace(
                    name=name,
                    focused=bool(workspace.get("focused", None)),
                    urgent=bool(workspace.get("urgent", None))
                )

        for name, outputs in self._persistent_workspaces.items():
            outputs = self._validate_outputs(outputs)
            if self._in_bar_output(outputs):
                existing = find(lambda w: w.name == name, self._workspaces)
                if existing:
                    existing.persistent = True
                else:
                    self._add_workspace(name=name, persistent=True)

    @glib_call_in_main
    def _handle_sway_event(
        self,
        _: SwayEvent,
        payload: SwayResPayload,
    ) -> None:
        if not isinstance(payload, dict):
            return

        change = payload.get("change", "")
        match(change):
            case "init":
                workspace = payload.get("current", {})
                name = workspace.get("name", None)
                if name is not None:
                    self._add_workspace(name)
            case "empty":
                workspace = payload.get("current", {})
                name = workspace.get("name", None)
                if name is not None:
                    self._remove_workspace(name)

    def _add_workspace(
        self,
        name: str,
        focused=False,
        persistent=False,
        urgent=False,
    ) -> None:
        for workspace in self._workspaces:
            if workspace.name == name:
                return

        new_workspace = Workspace(
            name=name,
            on_press=self._button_pressed,
            focused=focused,
            persistent=persistent,
            urgent=urgent,
        )

        self._workspaces.append(new_workspace)
        self._workspaces = sort_workspaces(self._workspaces)

        position = self._workspaces.index(new_workspace)
        self._button_box.pack_start(new_workspace.button, False, False, 0)
        self._button_box.reorder_child(new_workspace.button, position)

    def _remove_workspace(self, name: str) -> None:
        for i in range(0, len(self._workspaces)):
            workspace = self._workspaces[i]
            if workspace.name == name:
                if workspace.persistent:
                    return
                else:
                    self._button_box.remove(workspace.button)
                    del self._workspaces[i]
                    return

    def _button_pressed(self, name: str) -> None:
        payload = "workspace {}".format(name)
        self._sway_client.send(SwayMessage.RUN_COMMAND, payload)

    def _validate_outputs(self, outputs: str | list[str]) -> list[str]:
        if not outputs:
            return []
        elif isinstance(outputs, str):
            return [outputs]
        else:
            return outputs

    def _in_bar_output(self, outputs: list[str]) -> bool:
        return self._all_outputs or self._bar.output in outputs or not outputs


def name_is_number(name: str) -> bool:
    try:
        int(name)
        return True
    except ValueError:
        return False


def sort_workspaces(workspaces: list[Workspace]) -> list[Workspace]:
    numbered = []
    unnumbered = []

    for workspace in workspaces:
        if name_is_number(workspace.name):
            numbered.append(workspace)
        else:
            unnumbered.append(workspace)

    numbered.sort(key=lambda w: int(w.name))
    return numbered + unnumbered
