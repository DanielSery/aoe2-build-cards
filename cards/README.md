# AoE2 build-order cards

A drawing tool for the build-order cards players share as images — rows of
icons, grouped into phases, exported as a PNG, or several cards at once
as a PDF.

It is a static site. There is no server, no account and no simulation: the
card says what you draw, and the library is this browser's local storage —
everything read back out of it goes through `src/model/migrate.ts`, so a card
an older version of the editor saved still opens.

The one exception is **Analyze game…**, which turns a recorded game into a
card and needs the replay reader in [`../replays`](../replays) running. See
[From a recorded game](#from-a-recorded-game).

## Running it

```powershell
cd cards
npm install
npm run dev              # editor on http://localhost:5173
npm run build            # tsc -b && vite build, output in dist/
```

`dist/` is self-contained and can be served from any static host or
subdirectory (`base` is relative).

## Analyzing a recorded game

**Analyze game…** in the bar finds a game three ways:

- **Find a game** — type a player's name or profile id, pick them, and their
  games from the last four months are listed. Narrow them by format (1v1 to
  4v4), seat (flank or pocket, for 3v3 and 4v4), civ and map; each filter is
  optional, and the number beside a choice is how many games it would leave.
  Under each game its plan appears as you scroll to it — the replay has to be
  downloaded and read first, a couple at a time, so a long list fills in as
  you go and a game you never scroll to is never fetched.
- **Paste a link** — an aoe2companion or aoe2insights match link, the aoe.ms
  replay link, or just the match id.
- **Open a file** — a replay on this computer: the `.aoe2record` the game
  saves (usually under `Games\Age of Empires 2 DE\<your id>\savegame`) or the
  zip aoe.ms downloads. Choose it, or drop it anywhere on the page. It goes
  only to the reader running on this machine; names, civs and teams come from
  the replay itself.

Whichever way, you get the game's players with their civ, age-up times and the
plan they played, in a few words — "men-at-arms → archers", "boom → knights",
"unique unit, fast imp → hand cannoneers": the units they made, named as the
upgrade they had, towers and castles built near an enemy, a boom, a fast
imperial. The one you pick becomes a card. **It is not saved**: it opens marked *not saved*,
and only **Save** in the bar puts it in the library. Reading another player
replaces an unsaved card instead of piling up beside it.

It needs the replay reader, which also serves the app:

```powershell
cd cards; npm run build; cd ..
python -m pip install -r requirements.txt     # once: fastapi, uvicorn, mgz
python -m uvicorn replays.server:app --port 8030
# open http://localhost:8030/
```

`npm run dev` and `npm run preview` pass `/api` through to it as well.

Microsoft keeps replays for a few months, so an older game has none. The
card covers the opening up to a minute into Castle Age. No villager is made
while an age is researching, so one first sent to work then is written just
before the age-up, and a Town Centre tech clicked then just after it.
Villagers sent to the enemy — towers, a castle, a fight, laming — are
*forward*, which is no work, until they are sent back to some. Buildings,
techs, age times, gather points and which villagers were sent where come
straight from the replay. **How many villagers** a row moves is partly inferred: the
replay records every queue click, including the ones there was no food for,
so the age-up row's "at N vils" is an estimate. Techs, age-ups and soldiers
are placed when they were done or came out — the click plus the game's own
time for it, without civ bonuses — rather than when they were clicked, and
Loom after the villagers queued ahead of it wherever the next age-up says how
long that was. A task a villager held for
less than 30 seconds — 15 for gold, stone or a building site, which a build
order sends villagers to in short stints — or gave up before they could have
walked there, is left out, and so are single villagers swapped back and forth
inside a phase.

## The format

A card is **phases**, each holding **rows**. A new card starts with the five
every build order has — **Dark Age, Going Feudal, Feudal Age, Going Castle,
Castle Age** — the ages plus the stretch between each pair of them, where the
work is different. They start **empty**: a card is allowed to have no rows at
all, and a phase you have emptied stays empty rather than handing a blank row
straight back. Both transitions wear the same neutral band, which is what
says they are the in-between rather than an age. Add, rename, recolour or
delete them freely.

A row is three columns: the **new** villagers — with any moved off other
work to the same place — the ones **moved** somewhere else, and what the row
only mentions. A place is a number, its work, and then what is done on the
way, drawn small; a move reads right to left.

```
  [4][boar] house ← [3][sheep]      [2][berries] mill ← [sheep]      [2][deer]
  └ goes to         └ joined from   └ moved to          └ source     └ extras
```

| Place | What it says |
|---|---|
| **Goes to** | how many go there — new villagers, and any it was joined by — the work, then what they build on the way |
| **Joined from** | villagers moved off other work to the same place: how many — or **All** — and the work they came off |
| **Moved to** | how many were taken off other work — or **All** — where they go, then what they build on the way |
| **Source** | the work moved villagers were taken off. No number: *moved to* has it |
| **Extras** | anything the row only mentions: the deer pushed in, a tech, a note |

The moves line up down the card, and the extras keep to its right edge. A
row too long for one line breaks before its move, and then before its extras
— never in the middle of a column.

Each place holds **icons**, **numbers** and optional **words**. In a place
with a number, the first icon is the work and every icon after it is drawn
small: it is what they do on the way, not what the row is about. A number
and the icon after it are drawn as one tile. The arrow before the source is
drawn, never placed — it is there because the source exists.

A number is simply the first thing in the place it is about — there is no
column of its own. Words on *goes to* are how a row becomes an instruction: an
icon and "Research Loom".

Extras are **pictures, words and numbers** — "2 deer", a tech, a note. A
number there counts what it stands beside, never villagers, so it carries no
running figure. (The bordered hunt box of earlier versions is gone; a card
saved with one opens with its icons in its place.)

### Numbers

A number is an entity like an icon: drag it off the shelf, select it, move it,
delete it. It shows its own figure and, smaller beneath, **the villagers on
that number's work** — sheep, hunt, berries, farms, the wood line,
stragglers, gold or stone — not one total over the card, and not one per
resource either: "5" under berries and "6" under sheep are both food, but they
are not the same job.

The work comes from the icons in the number's own place: sheep, turkeys and
llamas are sheep; boar and deer are the hunt; the wood pile or a lumber camp is
the wood line and the straggler tree is stragglers. A place that names no work
— a tower, a militia, a tech, or a mill or mining camp, which serve two kinds —
leaves its number without a total rather than with a meaningless one.

A number in **moved to** is villagers *moved*: they go on to that work and
come off the source's. **All** moves everyone the source had. A number in
*goes to* is everyone arriving there, and one on *joined from* is how many of
them came off that work — **All** for everyone on it — so "4 boar ← 3 sheep"
is three off the sheep and one new. With no number in *goes to*, the ones off
the source are all who arrived. Use *joined from* only for a move to where
the new villagers go; a move anywhere else is *moved to*. The second column
is counted before the first, whatever order they are drawn in.

That figure is **counted up** by default. Double-click it and type one, and
it says so outright, and everything below counts on from there; clear it and
it counts up again. Turn the totals off for the whole card with *Running
totals*, above the shelf while nothing is selected.

Cards saved before the number moved to *moved to* open with it there, and
their *before* places folded into the place after the work.

### Captions

The small figure over a tile — `50` over gold — is **out of the layout**. A
row that has one is exactly as tall as a row that does not, and every tile on
the card stays on the same line. Double-click the icon to type it.

## Editing

- The shelf on the left holds **numbers and icons**. Drag either onto any
  place on the card, or click it and it lands wherever the selection is aiming
  — the banner at the top of the shelf says where. **All** beside the numbers
  is for where moved villagers go, or for *joined from*: everyone on that work
  moves.
- **Add a row** with the `+ row` strip at the foot of each phase, or press
  `Enter` — which adds one after whatever is selected. Either way the new row
  is selected, so the next click or drag has somewhere to go. `Ctrl D`
  duplicates the selected row, and `+ phase` at the foot of the card adds a
  phase.
- There is no panel of fields: **type on the card**. Double-click the title,
  the subtitle, a phase's label, a number, the figure under it, a note or an
  icon (for its caption) and type; `Enter` or clicking away keeps it, `Esc`
  puts it back. `F2` does the same for whatever is selected, and with a
  number selected, typing a digit starts a new one.
- Click anything on the card to select it. Above the shelf, the app says what
  is selected and what can be done to it: a phase's colour, `+ Row`,
  *Duplicate*, a note in the row's extras, moving it and deleting it. With
  nothing selected it offers a new phase and the running totals.
- Selecting a row shows its empty places — where new villagers go, a move and
  its source, the extras — so one can be clicked and the shelf aimed at it.
  Empty places also appear while you drag something. A place, or anything in
  it, selected offers `+ words` for words after its icons ("Research Loom").
- **Drag** icons and numbers to reorder them inside a place, or to move them
  to another place or another row. A **blue caret** shows the
  gap it will land in — aim at the left or right half of whatever you are
  over. Drag a row by the grip on its left, including into another phase.
- **Arrow keys** nudge the selection: `←` `→` move an item along its place,
  `↑` `↓` move a row up and down its phase, or a phase up and down the card.
- **Del** removes whatever is selected — an icon, a number, a row, a phase.
- **Zoom** with the buttons in the bar, `Ctrl` `+` / `-` / `0`, or `Ctrl` and
  the wheel. It is a view setting and never reaches the PNG.
- `Ctrl+Z` / `Ctrl+Shift+Z`, and `Esc` to select nothing.

## Exporting

- **Export** in the bar exports the card you are editing as an **image**
  (PNG), a **print** (PDF, also `Ctrl P`) or the **card file** (JSON).
- `Ctrl P` in the Library exports every card ticked there as one PDF, in
  library order. Every card in a PDF is drawn at the same width, whichever
  layout you pick there:

  | Layout | Cards | Card width |
  |---|---|---|
  | A4, one in the middle (default) | one per page, centred across it, at the top | 335pt (118 mm), 5/4 of two across |
  | A4, two across | two side by side, as many rows as fit | 268pt (94 mm) |
  | A4 landscape, two across | two side by side | 391pt (138 mm) |
  | A4, one across | one per row, as many as fit | 547pt (193 mm) |
  | A page per card | one per page, the page as tall as the card | 547pt (193 mm) |

  On A4 a card is never shrunk to fit. A card taller than the page is cut
  between two of its rows (never through one, and never between a phase's
  label and its first row) and carries on at the top of the next page, in
  the same column. A row of cards that will not fit under the one before it
  starts a new page. *A page per card* never cuts anything, but its pages
  are not A4, so a printer shrinks the long ones to fit the sheet.

## Icons

291 icons in `public/icons/aoe2/`, downloaded by
[`../tools/fetch_card_icons.py`](../tools/fetch_card_icons.py) from the
SiegeEngineers tech-tree repository and the Age of Empires wiki, the way the
fan sites redistribute Microsoft's art. That script also writes
`src/icons.generated.ts`, which is the picker's list — so an icon that failed
to download is simply absent rather than a broken tile.

Every tech researchable in Feudal or Castle Age is there, and every unit any
civ can make — but only the first unit of each line: an Elite Skirmisher or a
Hussar is drawn as the Skirmisher or the Scout it was trained as. A handful of
upgrades kept from before (Man-at-Arms, Long Swordsman, Crossbowman, Pikeman,
Light Cavalry) stay, because saved cards use them.

**Resources** are one shelf: the four resources, then what is on the map —
sheep, boar, deer, berries and the rest. Wood is either the **wood** resource
(the wood line) or a **straggler**, which is drawn as a bamboo — Age of
Mythology Retold's, because every AoE2 tree the wikis have is a clump, and one
plant standing alone is what tells a straggler from wood. There are no mine or
wood line icons: on a card those are the resource itself, and a card saved with
them opens with the resource instead.

**Buildings and technologies are listed in the age they unlock in** — Dark,
Feudal, Castle, Imperial, then alphabetically inside each — because when you
can have the thing is what a build order is about. Units stay alphabetical;
you look those up by name. Every icon that has an age shows it in the tooltip.

The age is read off the game's own tech tree, which every civ has a copy of;
where they disagree the answer is the one *most* civs give, so the Cumans'
Feudal-age Siege Workshop does not move it out of Castle for everybody else.
Technologies are resolved by **name** rather than by id: the tech tree and the
.dat disagree about which id the age-ups wear, which silently fetched the
Castle banner for "Feudal Age" and the Feudal one for "Castle Age".

Re-run it to change the set:

```powershell
python tools/fetch_card_icons.py
```

## Checking a change

```powershell
cd cards
npm run build
npm run preview -- --port 8020
node shot.mjs            # needs: npm i --no-save playwright
```

`shot.mjs` drives the editor headlessly — the shelf by click and by drag, Del
on an item and on a row, dragging an icon and a whole row, the library, zoom,
the PNG download and a two-card PDF — and writes `editor.png`, `card.png` and
`cards.pdf` so the export path is exercised rather than assumed.

Two of its checks are worth keeping honest. It types a caption onto a row that
has none and asserts **nothing on the card changes size**, because comparing
two different rows would only have measured their dividers. And it checks the
PNG's **pixel size against the card's own**: the export is a clone of the DOM,
and a clone that lays out even slightly differently overlaps rows rather than
failing. The PDF gets the same check, and it exports a short card beside a
long one in three layouts, asserting **every card is drawn the same width** and
that the long one is **cut between two rows**, never through one.
