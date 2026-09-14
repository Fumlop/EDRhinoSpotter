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

Checked 2026-09-13 against EDMC 6.1.2 as installed.

| | RhinoSpotter | EliteMeritTracker |
|---|---|---|
| Public repo | yes | yes |
| Licence, GPL v2+ compatible | GPL-3.0 | GPL-3.0 |
| `VERSION` and `__version__` on `load.py` | yes, 4.1.4 | yes, `v0.4.400.3.005` |
| Semantic version | 4.1.4 | **no** - four parts and a leading `v` |
| Ships only what it needs | `lib/` is gitignored | `backup_legacy/` untracked |
| Published release to point a zip at | v4.1.4, zip attached | yes, v0.4.400.3.005 |

RhinoSpotter is submitted: EDCD/EDMC-Plugin-Registry PR #77, open, awaiting
review. Its branch `add-rhinospotter` on the Fumlop fork carries
`plugins/RhinoSpotter.json` for 4.1.1, the same fields as
`docs/registry/RhinoSpotter.json` here in the fork's two-space-indented
layout. Each release updates both: version, zip URL, hash - verified against
the zip as GitHub serves it.

### EliteMeritTracker, one thing left

`pluginVer` is specified as a semantic version string and `v0.4.400.3.005` is
not one: four components, and a leading `v`. STANDARDS says enforcement is
deferred until EDMC supports auto-update - the manual review is not deferred.

Either map it for the registry entry (`0.4.400`, with the rest as build
metadata) or renumber the scheme. That is a call about the plugin's own
history, not about the registry, which is why it is still open.

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
  "pluginVer": "2.2.0",
  "pluginZip": "https://github.com/Fumlop/EDRhinoSpotter/releases/download/v2.2.0/RhinoSpotter-2.2.0.zip",
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

### The optional keys

`pluginZip`, `pluginHash`, `pluginVT`, `pluginIcon` and `pluginRequirements`
must be **present**, because the shape is fixed, but may be **empty**. Counted
across the 26 entries already merged:

| key | filled | empty |
|---|---|---|
| `pluginZip` | 22 | 4 |
| `pluginHash` | 18 | 8 |
| `pluginVT` | 8 | 18 |
| `pluginIcon` | 6 | 20 |

So an empty `pluginVT` is normal - it is a VirusTotal report URL, and most
listings do not have one. `pluginHash` is worth filling because it is what
proves the zip a user downloads is the zip that was reviewed.

### The hash

`pluginHash` is the SHA256 of the zip named in `pluginZip`.

```powershell
Get-FileHash -Algorithm SHA256 .\RhinoSpotter-2.2.0.zip
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
2. **Regenerate the screenshots** if the panel, window or card changed. The
   tool is behind `RHINOSPOTTER_DOCS=1` and is not written up anywhere else -
   it drives real windows and grabs the screen, which is maintenance work and
   not something the plugin does.
3. **Commit, tag, push both.**

   ```bash
   git tag -a v2.2.0 -m "RhinoSpotter 2.2.0 - what changed in a line"
   git push origin main
   git push origin v2.2.0
   ```
4. **Publish the release on GitHub** from that tag. A tag alone is not a
   release: `releases/latest` returns nothing for it, so neither the registry
   nor our own update button sees anything.
5. **Attach a zip** whose top-level folder is `RhinoSpotter`. GitHub's
   auto-generated zipball wraps everything in `Fumlop-EDRhinoSpotter-<sha>`,
   which is not a folder EDMC can load - our own updater handles that, a
   person unpacking by hand does not.

   Build it from what git tracks, so the zip and the tag cannot disagree:

   ```bash
   python - <<'EOF'
   import subprocess, zipfile, hashlib
   from rs_core.update import VERSION
   out = f"RhinoSpotter-{VERSION}.zip"
   tracked = subprocess.run(["git", "ls-files"], capture_output=True,
                            text=True).stdout.split()
   with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
       for rel in sorted(tracked):
           archive.write(rel, f"RhinoSpotter/{rel}")
   print(hashlib.sha256(open(out, "rb").read()).hexdigest())
   EOF
   ```

   Unpack it once and check `load.py` sits directly inside a folder called
   `RhinoSpotter`. That is the whole contract with EDMC.
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
