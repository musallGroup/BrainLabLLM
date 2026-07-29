"""Centralized color palette and ttk style setup for a modern, colorful look.

Supports a live-switchable light/dark palette: module-level color names
(BG_APP, TEXT_PRIMARY, etc.) are mutable globals reassigned by set_mode(),
not fixed constants - main.py's widget-construction code reads them exactly
as before, and ChatApp._apply_theme() re-pushes the current values into
already-built widgets after a toggle. The sidebar stays visually similar
across both modes (it's already a dark panel by design in this app), so
only BG_SIDEBAR_* / TEXT_ON_DARK_* are shared between the two palettes.
"""

from tkinter import ttk

FONT_FAMILY = "Segoe UI"
FONT_MONO = "Consolas"

# Shared across both modes - the sidebar is always a dark panel regardless
# of overall app light/dark mode, so it doesn't need two variants.
BG_SIDEBAR = "#1E1B2E"
BG_SIDEBAR_ITEM_HOVER = "#2A2640"
BG_SIDEBAR_ITEM_SELECTED = "#342F55"
TEXT_ON_DARK = "#E8E9F3"
TEXT_ON_DARK_MUTED = "#9391AC"
GHOST_BORDER = "#3A3656"

_LIGHT = {
    "BG_APP": "#F5F6FA",
    "BG_CARD": "#FFFFFF",
    "BUBBLE_ASSISTANT_BG": "#F0F1F6",
    "BORDER": "#E3E5EC",
    "TEXT_PRIMARY": "#1A1D29",
    "TEXT_SECONDARY": "#6B7080",
    "TEXT_DISABLED": "#B5B8C4",
    "ACCENT": "#6C5CE7",
    "ACCENT_HOVER": "#5A4BD4",
    "ACCENT_LIGHT": "#EEEBFF",
    "ACCENT_TEXT": "#4B3FC4",
    "ACCENT_DISABLED_BG": "#D3CDF7",
    "SUCCESS": "#00B894",
    "SUCCESS_LIGHT": "#E4F9F3",
    "SUCCESS_TEXT": "#087F5B",
    "DANGER": "#EB4D6B",
    "DANGER_HOVER": "#D43958",
    "DANGER_LIGHT": "#FDEAEE",
    "DANGER_TEXT": "#C22B49",
    "DANGER_DISABLED_BG": "#F5C2CD",
    "WARNING": "#FDA23A",
    "WARNING_LIGHT": "#FFF3E1",
    "CODE_BG": "#282A3A",
    "CODE_TEXT": "#E8E9F3",
    "INLINE_CODE_BG": "#EEF0F5",
    "INLINE_CODE_TEXT": "#B8306B",
    "BUTTON_ACTIVE_BG": "#EFF0F5",
    "BUTTON_DISABLED_BG": "#F5F6FA",
}

_DARK = {
    "BG_APP": "#15131F",
    "BG_CARD": "#1E1B2E",
    "BUBBLE_ASSISTANT_BG": "#282540",
    "BORDER": "#332F4A",
    "TEXT_PRIMARY": "#EDEDF5",
    "TEXT_SECONDARY": "#9B98B5",
    "TEXT_DISABLED": "#5A5770",
    "ACCENT": "#8B7CF6",
    "ACCENT_HOVER": "#9D8FF7",
    "ACCENT_LIGHT": "#2E2A4A",
    "ACCENT_TEXT": "#B8ADFA",
    "ACCENT_DISABLED_BG": "#453D6B",
    "SUCCESS": "#2DD4A8",
    "SUCCESS_LIGHT": "#1B3B34",
    "SUCCESS_TEXT": "#5EEAC5",
    "DANGER": "#F26E89",
    "DANGER_HOVER": "#F58AA0",
    "DANGER_LIGHT": "#3B2029",
    "DANGER_TEXT": "#F7A3B5",
    "DANGER_DISABLED_BG": "#4A2830",
    "WARNING": "#FDB25C",
    "WARNING_LIGHT": "#3B2E17",
    "CODE_BG": "#0F0D18",
    "CODE_TEXT": "#E8E9F3",
    "INLINE_CODE_BG": "#2E2A4A",
    "INLINE_CODE_TEXT": "#F0A8C8",
    "BUTTON_ACTIVE_BG": "#282440",
    "BUTTON_DISABLED_BG": "#1A1826",
}

is_dark = False


def _install(palette):
    globals().update(palette)


_install(_LIGHT)


def set_mode(dark):
    """Switches the module-level color names to the light or dark palette.
    Does not touch any already-built widget - callers must re-apply colors
    to existing widgets themselves (see ChatApp._apply_theme)."""
    global is_dark
    is_dark = dark
    _install(_DARK if dark else _LIGHT)


def setup_style(root):
    style = ttk.Style(root)
    style.theme_use("clam")

    style.configure(".", background=BG_APP, foreground=TEXT_PRIMARY, font=(FONT_FAMILY, 10))
    style.configure("TFrame", background=BG_APP)
    style.configure("TLabel", background=BG_APP, foreground=TEXT_PRIMARY)
    style.configure("Secondary.TLabel", background=BG_APP, foreground=TEXT_SECONDARY)
    style.configure("Heading.TLabel", background=BG_APP, foreground=TEXT_PRIMARY, font=(FONT_FAMILY, 12, "bold"))
    style.configure("SectionTitle.TLabel", background=BG_APP, foreground=TEXT_SECONDARY, font=(FONT_FAMILY, 9, "bold"))

    style.configure("Card.TFrame", background=BG_CARD)
    style.configure("Card.TLabel", background=BG_CARD, foreground=TEXT_PRIMARY)

    style.configure("Sidebar.TFrame", background=BG_SIDEBAR)
    style.configure("Sidebar.TLabel", background=BG_SIDEBAR, foreground=TEXT_ON_DARK, font=(FONT_FAMILY, 11, "bold"))
    style.configure("SidebarMuted.TLabel", background=BG_SIDEBAR, foreground=TEXT_ON_DARK_MUTED, font=(FONT_FAMILY, 8))

    style.configure(
        "TButton",
        background=BG_CARD,
        foreground=TEXT_PRIMARY,
        borderwidth=1,
        bordercolor=BORDER,
        relief="flat",
        padding=(12, 7),
        font=(FONT_FAMILY, 10),
    )
    style.map(
        "TButton",
        background=[("active", BUTTON_ACTIVE_BG), ("disabled", BUTTON_DISABLED_BG)],
        foreground=[("disabled", TEXT_DISABLED)],
    )

    style.configure(
        "Accent.TButton",
        background=ACCENT,
        foreground="#FFFFFF",
        borderwidth=0,
        padding=(16, 8),
        font=(FONT_FAMILY, 10, "bold"),
    )
    style.map(
        "Accent.TButton",
        background=[("active", ACCENT_HOVER), ("disabled", ACCENT_DISABLED_BG)],
        foreground=[("disabled", "#FFFFFF")],
    )

    style.configure(
        "Danger.TButton",
        background=DANGER,
        foreground="#FFFFFF",
        borderwidth=0,
        padding=(16, 8),
        font=(FONT_FAMILY, 10, "bold"),
    )
    style.map(
        "Danger.TButton",
        background=[("active", DANGER_HOVER), ("disabled", DANGER_DISABLED_BG)],
        foreground=[("disabled", "#FFFFFF")],
    )

    style.configure(
        "Ghost.TButton",
        background=BG_SIDEBAR,
        foreground=TEXT_ON_DARK,
        borderwidth=1,
        bordercolor=GHOST_BORDER,
        relief="flat",
        padding=(10, 7),
        font=(FONT_FAMILY, 9),
    )
    style.map(
        "Ghost.TButton",
        background=[("active", BG_SIDEBAR_ITEM_HOVER)],
        foreground=[("disabled", TEXT_ON_DARK_MUTED)],
    )

    style.configure("TNotebook", background=BG_APP, borderwidth=0, tabmargins=(0, 8, 0, 0))
    style.configure(
        "TNotebook.Tab",
        background=BG_APP,
        foreground=TEXT_SECONDARY,
        padding=(20, 10),
        font=(FONT_FAMILY, 10, "bold"),
        borderwidth=0,
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", BG_APP)],
        foreground=[("selected", ACCENT)],
    )

    style.configure("TCombobox", fieldbackground=BG_CARD, background=BG_CARD, bordercolor=BORDER, padding=6)
    style.map("TCombobox", fieldbackground=[("readonly", BG_CARD)], foreground=[("readonly", TEXT_PRIMARY)])

    style.configure("TEntry", fieldbackground=BG_CARD, bordercolor=BORDER, padding=6)
    style.map("TEntry", selectbackground=[("!disabled", ACCENT)], selectforeground=[("!disabled", "#FFFFFF")])

    style.configure("TPanedwindow", background=BG_APP)
    style.configure("TScrollbar", background=BG_APP, troughcolor=BG_APP, bordercolor=BG_APP, arrowsize=12)

    style.configure("TSeparator", background=BORDER)

    style.configure("TCheckbutton", background=BG_APP, foreground=TEXT_PRIMARY)
    style.configure("TRadiobutton", background=BG_APP, foreground=TEXT_PRIMARY)
    style.configure("TProgressbar", background=ACCENT, troughcolor=BG_APP, bordercolor=BG_APP)

    return style
