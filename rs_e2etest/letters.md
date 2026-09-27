# letters_e2e.py - what it covers and what it hides

`python rs_e2etest/letters_e2e.py`. One Tk process, the real material lists
(`main._materials()` over `mining_sheet.json`), menus built by
`scan.letter_jump`, keystrokes sent with `keybd_event` to the posted native
menu. Needs the desktop: the menu is really opened and typed into.

## Ways it can fail, each checked

- A letter lands on an entry that is not the first with that letter in list
  order.
- A letter shared by several materials picks one instead of highlighting the
  first (Enter must pick it).
- A letter no material starts with changes the pick.
- Lower- and upper-case entries: the key matches either.
- The panel placeholder ("select material") taking a letter: S would land on
  it before Sapphire.
- A check that passes without the key doing anything: the letter's first
  entry must differ from the value the menu starts on.
- The panel's Material menu, refilled when Settings changes
  (`main._fill_menu`), loses the letters.
- The three menus: panel Material, RhinoData filter, Edit dialog Material -
  one without the letters.

## Not covered

- EDMC's own window and theme around the panel menu.
- Mouse use of the menus: unchanged, not driven.
