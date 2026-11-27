"""
EDMC Settings UI code for uploading bookmarks feature

vScourge
"""

import tkinter as tk
from tkinter import messagebox

import rs_core.upload
from rs_core.logging import logger

try:
    import myNotebook as nb
    from config import config
except ImportError:      # running outside EDMC
    nb = config = None


### CONSTANTS ###

_upload_enabled = None
_upload_include_cmdr_name = None
_upload_url = None
_upload_access_key = None

_data_warning_shown = False


### FUNCTIONS ###

def prefs(frame: tk.Frame, panel: bool=True) -> tk.Frame:
    """
    Set up the widgets for the upload portion of RhinoSpotter's settings panel
    """
    global _upload_enabled, _upload_include_cmdr_name, _upload_url, _upload_access_key
    
    cur_row = frame.grid_size()[1] + 1
    
    tk.ttk.Separator(frame, orient='horizontal').grid(row=cur_row, column=0, columnspan=2, sticky='ew', padx=5, pady=2)
    
    # Enable uploading
    val = config.get_bool(rs_core.upload.UPLOAD_ENABLED_KEY, default=False) if config is not None else True
    _upload_enabled = tk.BooleanVar(value=val)
    nb.Checkbutton(frame, text='Upload Bookmarks', variable=_upload_enabled, command=lambda: _upload_enabled_changed(frame)).grid(row=cur_row+1, column=0, sticky='w', padx=5, pady=2)

    # Upload URL
    val = config.get_str(rs_core.upload.UPLOAD_URL_KEY, default='') if config is not None else True
    _upload_url = tk.StringVar(value=val)

    nb.Label(frame, text='Upload Server URL').grid(row=cur_row+2, column=0, sticky='w', padx=25, pady=2)
    tk.ttk.Entry(frame, textvariable=_upload_url, width=40).grid(row=cur_row+2, column=1, sticky='w', padx=5, pady=2)

    # Access Key
    val = config.get_str(rs_core.upload.UPLOAD_ACCESS_KEY_KEY, default='') if config is not None else True
    _upload_access_key = tk.StringVar(value=val)

    nb.Label(frame, text='Access Key').grid(row=cur_row+3, column=0, sticky='w', padx=25, pady=2)
    tk.ttk.Entry(frame, textvariable=_upload_access_key, width=40).grid(row=cur_row+3, column=1, sticky='w', padx=5, pady=2)

    # Include CMDR name
    val = config.get_bool(rs_core.upload.UPLOAD_INCLUDE_CMDR_NAME_KEY, default=True) if config is not None else True
    _upload_include_cmdr_name = tk.BooleanVar(value=val)
    nb.Checkbutton(frame, text='Include CMDR name', variable=_upload_include_cmdr_name).grid(row=cur_row+4, column=0, sticky='w', padx=25, pady=2)

    return frame


def prefs_changed() -> None:
    """
    If widgets have been changed, set their values in our config
    """
    global _upload_enabled, _upload_include_cmdr_name, _upload_url, _upload_access_key

    if config is not None:
        if _upload_enabled is not None:
            config.set(rs_core.upload.UPLOAD_ENABLED_KEY, bool(_upload_enabled.get()))
        if _upload_include_cmdr_name is not None:
            config.set(rs_core.upload.UPLOAD_INCLUDE_CMDR_NAME_KEY, bool(_upload_include_cmdr_name.get()))
        if _upload_url is not None:
            config.set(rs_core.upload.UPLOAD_URL_KEY, str(_upload_url.get()))
        if _upload_access_key is not None:
            config.set(rs_core.upload.UPLOAD_ACCESS_KEY_KEY, str(_upload_access_key.get()))


def _upload_enabled_changed(parent):
    global _data_warning_shown
    
    if _upload_enabled.get() and not _data_warning_shown:
        msg = """NOTICE: Enabling uploads will share bookmark data with other users, including:\n\n  Location, material, density, amount, rigs,\n  current time and (optionally) your CMDR name.\n\nSpeak with the manager of your server if you have questions about how this data is used."""
        messagebox.showinfo('Data Sharing Notice', msg, parent=parent.winfo_toplevel())
        _data_warning_shown = True
        
    