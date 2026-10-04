"""Assigning roles by pressing buttons on the OGs themselves. Pure logic: no serial, no drawing.

The questions are shown on the OGs' own screens (og_setup draws `card()`), and the answers are
button presses, so nothing has to be typed or matched up by COM port:

    1. Every OG asks "Which OG is the SCREEN?". Press GRAY on the one that should be the screen.
    2. That OG now asks the rest. Press GRAY on the OG that is the LEFT hand, then the RIGHT hand.
       Each OG that has no role yet also shows "Is this the LEFT HAND OG?" so you can see which
       question is being asked while you hold it.
    Yellow, on any OG, skips the role being asked (for example a setup with only one hand).
    Red, on any OG, starts again. When every OG has a role (or every role was asked) it is done.

An OG is identified by its USB serial number, which is what devices.json stores.
"""
from __future__ import annotations

STEPS = ("screen", "left_hand", "right_hand")
NAMES = {"screen": "SCREEN", "left_hand": "LEFT HAND", "right_hand": "RIGHT HAND"}


def needs_setup(found: list, saved: dict, explicit_ports: bool, force: bool = False) -> bool:
    """Should the shell ask for roles before starting?

    Yes when asked to (--setup), or when several OGs are plugged in, no roles are saved, and the
    ports were not given on the command line: there is no safe way to guess which is which. A
    single OG needs no roles, and saved roles are used as they are."""
    if not found:
        return False
    if force:
        return True
    return not explicit_ports and not saved and len(found) >= 2


class RoleSetup:
    def __init__(self, serials, order=STEPS):
        self.serials = list(serials)
        self.order = list(order)
        self.assigned: dict = {}           # role -> usb serial
        self.step = 0
        self.message = ""

    # ---- state ----------------------------------------------------------

    @property
    def role(self):
        """The role being asked about, or None when setup is finished."""
        return None if self.done else self.order[self.step]

    @property
    def done(self) -> bool:
        return self.step >= len(self.order) or not self.unassigned()

    def unassigned(self) -> list:
        return [s for s in self.serials if s not in self.assigned.values()]

    def mapping(self) -> dict:
        """role -> serial for the roles that were assigned."""
        return dict(self.assigned)

    def role_of(self, serial):
        for role, s in self.assigned.items():
            if s == serial:
                return role
        return None

    # ---- input ----------------------------------------------------------

    def on_press(self, serial: str, button: str) -> str:
        """A button went down on the OG with this serial. Returns a short message for the screen."""
        if self.done or serial not in self.serials:
            return ""
        if button == "red":
            self.assigned.clear()
            self.step = 0
            self.message = "Starting again."
        elif button == "yellow":
            self.message = f"Skipped the {NAMES[self.role].lower()}."
            self.step += 1
        elif button == "gray":
            if serial in self.assigned.values():
                self.message = f"That OG is already the {NAMES[self.role_of(serial)].lower()}."
            else:
                role = self.role
                self.assigned[role] = serial
                self.message = f"This OG is the {NAMES[role].lower()}."
                self.step += 1
        else:
            self.message = "Press GRAY to choose."
        return self.message


def card(setup: RoleSetup, serial: str):
    """What the OG with this serial should show: (title, lines, legend), legend = button -> label."""
    if setup.done:
        # Every OG ends up titled with its own role, and keeps that screen until a game starts.
        done_mine = setup.role_of(serial)
        if not setup.assigned:
            return "Setup done", ["No roles chosen."], {}
        if done_mine == "screen":
            return NAMES["screen"], ["Setup done.", "Starting Orca..."], {}
        if done_mine:
            return NAMES[done_mine], ["Setup done.", "Roles are saved."], {}
        return "No role", ["This OG was not given a role."], {}
    role, mine = setup.role, setup.role_of(serial)
    screen = setup.assigned.get("screen")
    if serial == screen:
        # The screen OG asks the questions for everyone.
        title = f"Pick the {NAMES[role]} OG"
        lines = ["Press GRAY on that OG.", "", setup.message or "Yellow skips, red restarts."]
        return title, lines, {"yellow": "Skip", "red": "Restart"}
    if mine:
        return (NAMES[mine], ["Chosen. Leave it as it is."], {"red": "Restart"})
    if role == "screen":
        return ("Which OG is the SCREEN?",
                ["Press GRAY on the OG that", "will show the menu and games.", "",
                 setup.message or ""], {"gray": "This one", "yellow": "Skip", "red": "Restart"})
    return (f"Is this the {NAMES[role]} OG?", ["Press GRAY here if it is.", "", setup.message or ""],
            {"gray": "This one", "yellow": "Skip", "red": "Restart"})
