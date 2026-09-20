# CLAUDE.md

RhinoSpotter, an EDMC plugin. Global rules live in `~/.claude/CLAUDE.md`.

## Comments and docstrings

Technical register only. A comment states what the code does, what it takes,
what it returns, or which constraint made it this way. Nothing else.

**Banned:**

- Narration and scene-setting. No "somebody has stood on it here", no "the
  question has become where is the jadeite", no second person.
- Aphorisms and rhetorical contrasts: "X is not Y, it is Z", "two tables that
  look alike and disagree are worse than one table", "that is the point of it".
- Jokes, asides, easter-egg commentary, anything an essay would open with.
- Restating the code in prose. Repeating the CHANGELOG.
- Justifying a design at length. One clause for the constraint, then stop.

**Required:**

- Numbers, not adjectives: `100 m: 8 rigs at 76 m spacing + 10%`, not
  "a generous margin".
- Name the mechanism: the event, the column, the Win32 call, the file.
- A docstring is one summary line; then args/returns/raises only where a caller
  can get them wrong; then constraints. No motivation paragraph.
- Units on every number. Config keys, journal event names and column names
  spelled exactly.

**Length:** if a comment runs past three lines, it is explaining a decision
that belongs in the CHANGELOG or in `structure.md`, not beside the code.

Comments written before this rule are being converted. Match the converted
style, not the surrounding one.

## UI strings

Say what the control does, in the fewest words that stay exact. Include the
threshold and its unit. "Show materials under 50,000 Cr/t", not "Offer the low
value ones too".
