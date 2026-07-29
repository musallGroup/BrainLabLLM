"""Centralized color palette and ttk style setup for a modern, colorful look."""

from tkinter import ttk

BG_APP = "#F5F6FA"
BG_SIDEBAR = "#1E1B2E"
BG_SIDEBAR_ITEM_HOVER = "#2A2640"
BG_SIDEBAR_ITEM_SELECTED = "#342F55"
BG_CARD = "#FFFFFF"
BORDER = "#E3E5EC"

TEXT_PRIMARY = "#1A1D29"
TEXT_SECONDARY = "#6B7080"
TEXT_ON_DARK = "#E8E9F3"
TEXT_ON_DARK_MUTED = "#9391AC"

ACCENT = "#6C5CE7"
ACCENT_HOVER = "#5A4BD4"
ACCENT_LIGHT = "#EEEBFF"
ACCENT_TEXT = "#4B3FC4"

SUCCESS = "#00B894"
SUCCESS_LIGHT = "#E4F9F3"
SUCCESS_TEXT = "#087F5B"

DANGER = "#EB4D6B"
DANGER_HOVER = "#D43958"
DANGER_LIGHT = "#FDEAEE"
DANGER_TEXT = "#C22B49"

WARNING = "#FDA23A"
WARNING_LIGHT = "#FFF3E1"

CODE_BG = "#282A3A"
CODE_TEXT = "#E8E9F3"
INLINE_CODE_BG = "#EEF0F5"
INLINE_CODE_TEXT = "#B8306B"

FONT_FAMILY = "Segoe UI"
FONT_MONO = "Consolas"


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
        background=[("active", "#EFF0F5"), ("disabled", "#F5F6FA")],
        foreground=[("disabled", "#B5B8C4")],
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
        background=[("active", ACCENT_HOVER), ("disabled", "#D3CDF7")],
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
        background=[("active", DANGER_HOVER), ("disabled", "#F5C2CD")],
        foreground=[("disabled", "#FFFFFF")],
    )

    style.configure(
        "Ghost.TButton",
        background=BG_SIDEBAR,
        foreground=TEXT_ON_DARK,
        borderwidth=1,
        bordercolor="#3A3656",
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
    style.configure("TProgressbar", background=ACCENT, troughcolor=BG_APP, bordercolor=BG_APP)

    return style
