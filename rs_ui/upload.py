"""Settings rows for bookmark upload."""

import tkinter as tk
from tkinter import messagebox, ttk

import rs_core.upload

try:
    import myNotebook as nb
    from config import config
except ImportError:      # running outside EDMC
    nb = config = None


_upload_enabled = None
_upload_include_cmdr_name = None
_upload_url = None
_upload_access_key = None

_data_warning_shown = False


def prefs(frame: tk.Frame) -> tk.Frame:
    """Add the upload rows under the rows already in `frame`; returns `frame`."""
    global _upload_enabled, _upload_include_cmdr_name, _upload_url, _upload_access_key

    cur_row = frame.grid_size()[1] + 1

    ttk.Separator(frame, orient='horizontal').grid(row=cur_row, column=0, columnspan=2, sticky='ew', padx=5, pady=2)

    val = config.get_bool(rs_core.upload.UPLOAD_ENABLED_KEY, default=False) if config is not None else False
    _upload_enabled = tk.BooleanVar(value=val)
    nb.Checkbutton(frame, text=f'Upload bookmarks to a team server, checked every {rs_core.upload.NEW_BOOKMARKS_CHECK_INTERVAL // 60} min', variable=_upload_enabled, command=lambda: _upload_enabled_changed(frame)).grid(row=cur_row+1, column=0, sticky='w', padx=5, pady=2)

    val = config.get_str(rs_core.upload.UPLOAD_URL_KEY, default='') if config is not None else ''
    _upload_url = tk.StringVar(value=val)
    nb.Label(frame, text='Server URL (https://)').grid(row=cur_row+2, column=0, sticky='w', padx=25, pady=2)
    ttk.Entry(frame, textvariable=_upload_url, width=40).grid(row=cur_row+2, column=1, sticky='w', padx=5, pady=2)

    val = config.get_str(rs_core.upload.UPLOAD_ACCESS_KEY_KEY, default='') if config is not None else ''
    _upload_access_key = tk.StringVar(value=val)
    nb.Label(frame, text='Access Key').grid(row=cur_row+3, column=0, sticky='w', padx=25, pady=2)
    ttk.Entry(frame, textvariable=_upload_access_key, width=40, show='*').grid(row=cur_row+3, column=1, sticky='w', padx=5, pady=2)

    val = config.get_bool(rs_core.upload.UPLOAD_INCLUDE_CMDR_NAME_KEY, default=False) if config is not None else False
    _upload_include_cmdr_name = tk.BooleanVar(value=val)
    nb.Checkbutton(frame, text='Send my CMDR name with them', variable=_upload_include_cmdr_name).grid(row=cur_row+4, column=0, sticky='w', padx=25, pady=2)

    return frame


def prefs_changed() -> None:
    """Settings OK: the four rows to EDMC config."""
    if config is None:
        return
    if _upload_enabled is not None:
        config.set(rs_core.upload.UPLOAD_ENABLED_KEY, bool(_upload_enabled.get()))
    if _upload_include_cmdr_name is not None:
        config.set(rs_core.upload.UPLOAD_INCLUDE_CMDR_NAME_KEY, bool(_upload_include_cmdr_name.get()))
    if _upload_url is not None:
        config.set(rs_core.upload.UPLOAD_URL_KEY, str(_upload_url.get()))
    if _upload_access_key is not None:
        config.set(rs_core.upload.UPLOAD_ACCESS_KEY_KEY, str(_upload_access_key.get()))


def _upload_enabled_changed(parent):
    """Data notice, once per session."""
    global _data_warning_shown

    if _upload_enabled.get() and not _data_warning_shown:
        msg = ("Every bookmark goes to the upload server, checked every 5 minutes:\n\n"
               "  system, body, location number, latitude, longitude, heading,\n"
               "  planet radius, material, rigs, density, amount,\n"
               "  when it was marked, edited and marked depleted,\n"
               "  your CMDR name only with \"Send my CMDR name with them\" ticked.\n\n"
               "Whoever runs the server can share it. Ask them how it is used.")
        messagebox.showinfo('Data Sharing Notice', msg, parent=parent.winfo_toplevel())
        _data_warning_shown = True
