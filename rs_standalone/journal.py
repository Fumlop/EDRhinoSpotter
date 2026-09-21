r"""The journal feed EDMC hands to journal_entry, for standalone.py.

Follows EDMC 6.1.2 monitor.py (read from its bytecode):
- newest file: LOGFILE among the folder's names, max by ctime.
- start(): every line of the newest file parsed for state, none delivered; then
  one synthesised StartUp. EDMC sends it when the game process runs; here when
  the file's last event is not Shutdown.
- poll(), every POLL_MS: complete new lines parsed, then delivered as
  deliver(cmdr, is_beta, system, station, entry, state). A newer file: the old
  one read to its end first, then the new one from byte 0.

No tkinter.
"""

import json
import os
import re
import time

from rs_core.logging import logger

LOGFILE = re.compile(r"^Journal(Alpha|Beta)?\.[0-9]{2,4}(-)?[0-9]{2}(-)?[0-9]{2}(T)?"
                     r"[0-9]{2}[0-9]{2}[0-9]{2}\.[0-9]{2}\.log$")
POLL_MS = 1000                  # EDMC monitor._POLL, 1 s

SYSTEM_KEYS = ("SystemAddress", "SystemName", "SystemPopulation", "StarPos",
               "Body", "BodyID", "BodyType", "StationName", "MarketID", "StationType")


def newest(folder):
    """Path of the newest journal in `folder`, or None."""
    try:
        names = [name for name in os.listdir(folder) if LOGFILE.search(name)]
    except OSError:
        return None
    if not names:
        return None
    return max((os.path.join(folder, name) for name in names), key=os.path.getctime)


class Journal:
    """The newest Journal.*.log in `folder`, tailed into `deliver`."""

    def __init__(self, folder, deliver):
        self.folder = folder
        self.deliver = deliver
        self.path = None
        self.pos = 0
        self.partial = b""          # a line without its newline yet
        self.cmdr = None
        self.is_beta = False
        self.running = False        # the last event read was not Shutdown
        self.state = dict.fromkeys(SYSTEM_KEYS)
        self.state["IsDocked"] = False
        self._error = None

    def start(self):
        """Catch up on the newest file without delivering, then send StartUp."""
        self.path = newest(self.folder)
        logger.info(f"journal: {self.folder}, starting on {self.path}")
        for entry in self._read():
            self._parse(entry)
        if self.running:
            self._send(self._startup())

    def poll(self):
        """Deliver what was written since the last poll, following a new file."""
        for entry in self._read():
            self._parse(entry)
            self._send(entry)
        latest = newest(self.folder)
        if latest and (self.path is None
                       or os.path.normcase(latest) != os.path.normcase(self.path)):
            # Lines written to the old file between the read above and newest().
            for entry in self._read():
                self._parse(entry)
                self._send(entry)
            logger.info(f"journal: new file {latest}, was {self.path}")
            self.path, self.pos, self.partial = latest, 0, b""
            for entry in self._read():
                self._parse(entry)
                self._send(entry)

    def _read(self):
        """Entries from the complete lines after self.pos. A line that is not
        JSON is logged at debug and skipped."""
        if not self.path:
            return []
        try:
            with open(self.path, "rb") as handle:
                if os.fstat(handle.fileno()).st_size < self.pos:     # replaced, read again
                    self.pos, self.partial = 0, b""
                handle.seek(self.pos)
                data = handle.read()
        except OSError as err:
            if repr(err) != self._error:
                logger.warning(f"journal: cannot read {self.path}: {err}")
                self._error = repr(err)
            return []
        self._error = None
        self.pos += len(data)
        lines = (self.partial + data).split(b"\n")
        self.partial = lines.pop()
        entries = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line.decode("utf-8"))
            except ValueError as err:
                logger.debug(f"journal: skipped a line of {self.path}: {err}")
                continue
            if isinstance(entry, dict):
                entries.append(entry)
        return entries

    def _reset_system(self):
        for key in SYSTEM_KEYS:
            self.state[key] = None

    def _parse(self, entry):
        """monitor.parse_entry, for the fields journal_entry and StartUp carry."""
        event = entry.get("event")
        state = self.state
        if event == "Fileheader":
            self.cmdr = None
            self._reset_system()
            self.is_beta = "beta" in str(entry.get("gameversion", "")).lower()
        elif event == "Commander":
            self.cmdr = entry.get("Name")
        elif event == "LoadGame":
            self.cmdr = entry.get("Commander")
            self._reset_system()
        elif event in ("JoinACrew", "QuitACrew"):
            self._reset_system()
        elif event == "Undocked":
            state["StationName"] = state["MarketID"] = state["StationType"] = None
            state["IsDocked"] = False
        elif event == "Docked":
            state["IsDocked"] = True
            for key in ("StationName", "MarketID", "StationType"):
                state[key] = entry.get(key)
        elif event == "SupercruiseExit":
            for key in ("Body", "BodyID", "BodyType"):
                state[key] = entry.get(key)
            if entry.get("BodyType") == "Station":
                state["Body"] = state["BodyID"] = None
        elif event in ("Location", "FSDJump", "CarrierJump"):
            for key in ("Body", "BodyID", "BodyType"):
                state[key] = entry.get(key) if event != "FSDJump" else None
            if event == "Location":
                state["IsDocked"] = entry.get("Docked", False)
            state["StarPos"] = entry.get("StarPos")
            state["SystemAddress"] = entry.get("SystemAddress")
            state["SystemPopulation"] = entry.get("Population")
            state["SystemName"] = entry.get("StarSystem")
            if event == "FSDJump":
                state["StationName"] = state["MarketID"] = state["StationType"] = None
            else:
                state["StationName"] = entry.get("StationName")
                if entry.get("BodyType") == "Station":
                    state["StationName"] = entry.get("Body")
                state["MarketID"] = entry.get("MarketID")
                state["StationType"] = entry.get("StationType")
        if event:
            self.running = event != "Shutdown"

    def _startup(self):
        """monitor.synthesize_startup_event."""
        state = self.state
        entry = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                 "event": "StartUp", "StarSystem": state["SystemName"],
                 "StarPos": state["StarPos"], "SystemAddress": state["SystemAddress"],
                 "Population": state["SystemPopulation"]}
        if state["Body"]:
            entry["Body"] = state["Body"]
            entry["BodyID"] = state["BodyID"]
            entry["BodyType"] = state["BodyType"]
        if state["StationName"]:
            entry["Docked"] = True
            entry["MarketID"] = state["MarketID"]
            entry["StationName"] = state["StationName"]
            entry["StationType"] = state["StationType"]
        return entry

    def _send(self, entry):
        """One entry to `deliver`; a raise is logged, as EDMC does per plugin."""
        try:
            self.deliver(self.cmdr, self.is_beta, self.state["SystemName"],
                         self.state["StationName"], entry, self.state)
        except Exception:
            logger.exception(f"journal: journal_entry raised on {entry.get('event')}")
