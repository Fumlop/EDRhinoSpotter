"""RhinoSpotter - surface mining, from the panel EDMC already has open.

Two buttons.

    Bookmark    marks the patch you are standing on and renders it as a PNG.
                Position, body and the targeted mining location come out of
                Status.json at the press, which is live-only, so the card has
                to be made while you are still there.

    RhinoScan   lists the landable bodies of the system you are in, grouped by
                what kind of body they are, with what that kind has been found
                to hold. Bodies come from the journal, rates from the mining
                sheet shipped as mining_sheet.json. Neither asks the network
                for anything.

Nothing is written to a database. The card is the record, and the scan window
is read-only.

This file is the EDMC contract and nothing else: the lifecycle hooks, and where
they go. The panel is rs_ui, the work is rs_core, the tests are rs_tests.
"""

from rs_core.update import VERSION            # noqa: F401  the registry reads this
from rs_ui import main

# VERSION is re-exported on purpose. The EDMC plugin registry asks for a
# VERSION constant or a __version__ dunder on the plugin, and the plugin is
# this file - rs_core/update.py is where it is defined, because that is what
# compares it against a release.
__version__ = VERSION


def plugin_start3(plugin_dir):
    return main.start(plugin_dir)


def plugin_app(parent):
    return main.build(parent)


def journal_entry(cmdr, is_beta, system, station, entry, state):
    return main.journal_entry(cmdr, is_beta, system, station, entry, state)


def plugin_prefs(parent, cmdr, is_beta):
    return main.prefs(parent)


def prefs_changed(cmdr, is_beta):
    return main.prefs_changed()


def plugin_stop():
    return main.stop()
