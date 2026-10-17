"""Tk widget helpers in the RhinoData colours, shared by scan.py and main.py."""

import tkinter as tk

from rs_core import palette

BG = palette.BG
PANEL = palette.PANEL
FG = palette.FG
DIM = palette.MUTED
ACCENT = palette.ACCENT
RULE = palette.RULE

TOOLTIP_MS = 500


def button(parent, text, command=None, active=ACCENT):
    """The one button style. No command: disabled. `active`: foreground under the pointer."""
    return tk.Button(parent, text=text, command=command,
                     bg=BG, fg=FG, activebackground=BG,
                     activeforeground=active, disabledforeground=DIM,
                     relief="solid", borderwidth=1, highlightthickness=0,
                     padx=8, pady=1, font=("Segoe UI", 8),
                     cursor="hand2" if command else "arrow",
                     state="normal" if command else "disabled")


def style_field(widget):
    """Entry, Spinbox or Menubutton (and its Menu) in the window's colours.

    Tk draws them in the system theme otherwise; Menu entries live on the Menu,
    not the Menubutton.
    """
    widget.config(bg=PANEL, fg=FG, relief="solid", borderwidth=1,
                  highlightthickness=0, font=("Consolas", 9))
    if isinstance(widget, tk.Menubutton):
        widget.config(anchor="w", padx=6, pady=2, indicatoron=True,
                      activebackground=PANEL, activeforeground=ACCENT)
        widget["menu"].config(bg=PANEL, fg=FG, activebackground=BG,
                              activeforeground=ACCENT, borderwidth=1,
                              activeborderwidth=0, tearoff=False)
        return
    widget.config(insertbackground=FG, disabledbackground=PANEL,
                  readonlybackground=PANEL, selectbackground=RULE,
                  selectforeground=FG)
    if isinstance(widget, tk.Spinbox):
        widget.config(buttonbackground=PANEL)


def restyle(widget):
    """`widget` and its children in the RhinoData colours; a 'System*' foreground becomes FG."""
    for child in widget.winfo_children():
        restyle(child)
    if isinstance(widget, (tk.Entry, tk.Spinbox, tk.Menubutton)):
        style_field(widget)
        return
    options = widget.keys()
    widget.config(bg=BG)
    if "fg" in options and str(widget.cget("fg")).startswith("System"):
        widget.config(fg=FG)
    if isinstance(widget, tk.Button):
        widget.config(bg=PANEL, activebackground=PANEL, activeforeground=ACCENT,
                      relief="solid", borderwidth=1)


NO_MATERIALS = "No materials - pick them: File > Settings > RhinoSpotter > Select..."


def no_materials_hint(option_menu):
    """A disabled NO_MATERIALS entry at the end of the menu: the materials pick is empty or broken."""
    option_menu["menu"].add_command(label=NO_MATERIALS, state="disabled")


def letter_jump(option_menu, skip=()):
    """First letter of each entry as its Windows menu mnemonic; `skip`: labels left without one.

    With the menu open, a letter highlights the first entry starting with it,
    or picks it when only one does.
    """
    menu = option_menu["menu"]
    last = menu.index("end")
    for i in range(0 if last is None else last + 1):
        label = str(menu.entrycget(i, "label")) if menu.type(i) == "command" else ""
        if label[:1].isalnum() and label not in skip:
            menu.entryconfigure(i, underline=0)


def tooltip(widget, text):
    """`text` in a borderless topmost Toplevel under `widget`, TOOLTIP_MS after <Enter>.

    Gone on <Leave>, <ButtonPress> and <Destroy>. Topmost: the window it sits on can be.
    """
    tip = {"job": None, "box": None}

    def show():
        tip["job"] = None
        box = tip["box"] = tk.Toplevel(widget)
        box.overrideredirect(True)
        box.attributes("-topmost", True)
        tk.Label(box, text=text, bg=PANEL, fg=FG, relief="solid", borderwidth=1,
                 padx=6, pady=2, font=("Segoe UI", 8)).pack()
        box.geometry(f"+{widget.winfo_rootx()}+{widget.winfo_rooty() + widget.winfo_height() + 2}")

    def enter(_):
        tip["job"] = widget.after(TOOLTIP_MS, show)

    def leave(_):
        if tip["job"] is not None:
            widget.after_cancel(tip["job"])
            tip["job"] = None
        if tip["box"] is not None:
            tip["box"].destroy()
            tip["box"] = None

    widget.bind("<Enter>", enter, add="+")
    for event in ("<Leave>", "<ButtonPress>", "<Destroy>"):
        widget.bind(event, leave, add="+")


def clickable(widget, command, skip_buttons=False):
    """<Button-1> on `widget` and every descendant runs `command`.

    Tk does not pass a click up to the parent. `skip_buttons`: Buttons keep only their own command.
    """
    def press(event):
        command()

    pending = [widget]
    while pending:
        current = pending.pop()
        if skip_buttons and isinstance(current, tk.Button):
            continue
        current.config(cursor="hand2")
        current.bind("<Button-1>", press)
        pending.extend(current.winfo_children())


def centre_over(box, parent):
    """Put `box` in the middle of `parent`. update_idletasks first: an unlaid Toplevel reports 1x1."""
    box.update_idletasks()
    x = parent.winfo_rootx() + (parent.winfo_width() - box.winfo_width()) // 2
    y = parent.winfo_rooty() + (parent.winfo_height() - box.winfo_height()) // 2
    box.geometry(f"+{max(0, x)}+{max(0, y)}")


def wrap_to_width(event):
    """<Configure>: wraplength follows the label's width; it has no default tied to the pane."""
    if event.width > 80:
        event.widget.config(wraplength=event.width - 8)


def wheel(canvas):
    """The wheel scrolls `canvas` while the pointer is over it.

    bind_all on <Enter>: the rows are frames inside the canvas. The previous
    bind_all (EDMC, other plugins) is put back on <Leave> and <Destroy>.
    """
    def scroll(event):
        canvas.yview_scroll(-int(event.delta / 120), "units")

    def enter(event):
        canvas.rs_previous = canvas.bind_all("<MouseWheel>")
        canvas.bind_all("<MouseWheel>", scroll)

    def leave(event):
        canvas.unbind_all("<MouseWheel>")
        if getattr(canvas, "rs_previous", None):
            canvas.bind_all("<MouseWheel>", canvas.rs_previous)
            canvas.rs_previous = None

    canvas.bind("<Enter>", enter, add="+")
    canvas.bind("<Leave>", leave, add="+")
    canvas.bind("<Destroy>", leave, add="+")
