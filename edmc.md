# Getting into the EDMC plugin registry, and staying there

Notes for [EDCD/EDMC-Plugin-Registry](https://github.com/EDCD/EDMC-Plugin-Registry),
which is what feeds EDMC's own plugin browser. Covers both plugins in this
account: **RhinoSpotter** and **EliteMeritTracker**.

The two documents that govern it:

- [docs/STANDARDS.md](https://github.com/EDCD/EDMC-Plugin-Registry/blob/main/docs/STANDARDS.md) - what a plugin must be
- [docs/CONTRIBUTING.md](https://github.com/EDCD/EDMC-Plugin-Registry/blob/main/docs/CONTRIBUTING.md) - how to submit it

Every submission is read by a person. Nothing here is automatic.

---

## Where we stand

Checked 2026-09-11 against EDMC 6.1.2 as installed.

| | RhinoSpotter | EliteMeritTracker |
|---|---|---|
| Public repo | yes | yes |
| Licence, GPL v2+ compatible | **missing** | GPL-3.0 |
| `VERSION` or `__version__` in the plugin | in `rs_core/update.py`, not `load.py` | **none anywhere** |
| Semantic version | 2.1.0 | **`v0.4.400.3.004`** - four parts and a `v` |
| Published release to link a zip to | `v2.0.0` | yes |

### RhinoSpotter, before submitting

1. **Add a LICENSE file.** GPL v2 or v3, BSD-2, BSD-3, LGPL or MIT. The
   registry calls plugins derivative works of EDMC, so this is not optional.
2. **Expose the version from `load.py`.** The standard asks for a `VERSION`
   constant or a `__version__` dunder on the plugin. Ours lives one module
   down; re-exporting it is one line:

   ```python
   from rs_core.update import VERSION   # noqa: F401  - the registry reads this
   ```
3. **Consider deleting `lib/`.** 3.2 MB of vendored pg8000 that nothing
   imports, left from a database path that no longer exists. It is gitignored
   so it never reaches a release zip, but "bundle only resources necessary for
   core functions" is a listed rule and a reviewer looking at the working tree
   will see it.

### EliteMeritTracker, before submitting

1. **Add a `VERSION` constant.** The version is an attribute on
   `configPlugin` in `emt_core/config.py`. The registry wants it on the
   plugin, so `load.py` needs something it can read.
2. **Decide what to put in `pluginVer`.** `v0.4.400.3.004` is not semantic
   versioning: four components, and a leading `v`. The JSON field is specified
   as a semantic version string. STANDARDS says enforcement is deferred until
   EDMC supports auto-update - the manual review is not deferred. Either map
   it (`0.4.400` with the rest as build metadata) or renumber.
3. **`backup_legacy/` is in the repo**, 17 files, described in its own
   `structure.md` as "Legacy code backup (pre-refactor)". Under "least
   privilege" that is the first thing a reviewer will ask about. `system_data/`
   is 45 MB but already untracked, which is right.

---

## Submitting

One pull request, one new JSON file in `/plugins/`, nothing else touched. The
master list rebuilds itself when the PR is merged - editing it yourself is
called out as wrong.

```
EDMC-Plugin-Registry/
└── plugins/
    └── RhinoSpotter.json      <- the only file in the PR
```

### The file

Keys as they appear in [docs/example.json](https://github.com/EDCD/EDMC-Plugin-Registry/blob/main/docs/example.json).
Twelve are required; `pluginZip` and `pluginHash` are recommended and worth
filling in.

```json
{
  "pluginName": "RhinoSpotter",
  "pluginVer": "2.1.0",
  "pluginZip": "https://github.com/Fumlop/EDRhinoSpotter/releases/download/v2.1.0/RhinoSpotter-2.1.0.zip",
  "autoUpdateEnabled": false,
  "autoInstallEnabled": false,
  "pluginAuthors": ["Fumlop"],
  "pluginMainLink": "https://github.com/Fumlop/EDRhinoSpotter",
  "pluginLastUpdate": "2026-09-11",
  "pluginDirName": "RhinoSpotter",
  "pluginCategory": ["Exploration"],
  "pluginDesc": "Surface mining: which bodies in this system are worth landing on, and a card for the patch you are standing on.",
  "pluginLastTestedEDMC": "6.1.2",
  "pluginRequirements": [],
  "pluginLicense": "GPL-3.0-or-later",
  "pluginIcon": "",
  "pluginVT": "",
  "pluginHash": ""
}
```

Notes on the fiddly ones:

- **`autoUpdateEnabled` and `autoInstallEnabled` are both `false`.** Not a
  choice - CONTRIBUTING says set them false. Our own in-plugin update button
  is unrelated to this and stays.
- **`pluginDirName`** is the folder EDMC will create. It has to match what
  `load.py` expects to be sitting in, which for us is `RhinoSpotter`, not the
  repo name `EDRhinoSpotter`.
- **`pluginLicense`** is an SPDX identifier, not a sentence. `GPL-3.0-or-later`,
  `MIT`, `BSD-3-Clause`.
- **`pluginLastTestedEDMC`** is the EDMC you actually ran it against. 6.1.2
  today. The rule is that the plugin must work on at least the current patch
  line, so this needs revisiting when EDMC moves.
- **`pluginCategory`** takes one or more. Overstating what a plugin does is
  listed under things that get you removed, so pick the one that is true.

### The hash

`pluginHash` is the SHA256 of the zip named in `pluginZip`.

```powershell
Get-FileHash -Algorithm SHA256 .\RhinoSpotter-2.1.0.zip
```

The zip has to be the one attached to the release, not a fresh one built
locally - a rebuilt zip has different timestamps and a different hash.

Valid `pluginCategory` values, and only these: Exploration, Navigation,
Combat, Trading, Engineering, Anti-Xeno, Colonization, Utility, Lore, Social,
Streaming, Other.

### The steps

1. Cut the release on our side first (below). Nothing can be submitted without
   a version that exists.
2. Fork `EDCD/EDMC-Plugin-Registry`, branch.
3. Copy `docs/registry/RhinoSpotter.json` from this repo into `plugins/`.
   One file, nothing else touched.
4. Open the PR, follow their template, and wait for a human.

`docs/registry/RhinoSpotter.json` is kept here as the source of truth for what
we submitted, so the next version is a diff rather than a rewrite.

---

## Releasing a new version, ours

The order matters: the registry entry points at a release, so the release has
to exist first.

1. **Bump the version in both places.** `rs_core/update.py` holds `VERSION`;
   the changelog's top heading repeats it. A test fails if they disagree, so
   run `pytest` before anything else.
2. **Regenerate the screenshots** if the panel, window or card changed:
   `python rs_tests/make_docs_images.py`. A README showing last month's layout
   is worse than one showing none.
3. **Commit, tag, push both.**

   ```bash
   git tag -a v2.1.0 -m "RhinoSpotter 2.1.0 - what changed in a line"
   git push origin main
   git push origin v2.1.0
   ```
4. **Publish the release on GitHub** from that tag. A tag alone is not a
   release: `releases/latest` returns nothing for it, so neither the registry
   nor our own update button sees anything.
5. **Attach a zip** whose top-level folder is `RhinoSpotter`. GitHub's
   auto-generated zipball wraps everything in `Fumlop-EDRhinoSpotter-<sha>`,
   which is not a folder EDMC can load - our own updater handles that, a
   person unpacking by hand does not.
6. **Update the registry entry.** Edit the same JSON: `pluginVer`,
   `pluginZip`, `pluginHash`, `pluginLastUpdate`, and `pluginLastTestedEDMC`
   if EDMC moved. One more PR, same rules.

---

## Things that get a plugin dropped

Straight from STANDARDS, worth keeping in view:

- Not keeping up with EDMC. Listing is conditional on staying compatible with
  the current patch line, and removal is explicit for plugins that go stale
  "between versions".
- Scraping a community service instead of using its API. We do not touch one
  at all, which is the easy version of this.
- Names that game the alphabet, tags that overstate what the plugin does.
- Bundling what the plugin does not need.
