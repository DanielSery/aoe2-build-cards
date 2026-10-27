# AoE2 Build Cards — working notes

Two parts that ship together: `cards/`, the card editor, a static site; and
`replays/`, the replay reader and the HTTP server that also serves the built
editor. `aoe2planner/gamedata/` is the game's own data, which the reader names
things by, and `tools/` holds the icon fetcher and the offline checks.

### `cards/` — the card editor

A Vite + React app: the build-order **card** players post as an image —
rows of icons under coloured phase bands. It is a static site with no
Python: a card answers "what am I telling you to do?", not "would this build
work?". The one thing it asks a server for is *Analyze game…*, which
`replays/` answers; served without it, that dialog says so and everything else
works.

| Path | Owns |
|---|---|
| `src/model/card.ts` | the document — phases, rows, a row's three columns — and every edit as a pure function |
| `src/model/jobs.ts` | which work an icon is about. The only game knowledge in the app |
| `src/model/library.ts` | the library: this browser's local storage, and the JSON in and out |
| `src/model/samples.ts` | the card it opens with, which is what explains the format |
| `src/model/games.ts` | the calls to the replay reader, and the message when nothing answers |
| `src/icons.generated.ts` | written by `tools/fetch_card_icons.py`; do not hand-edit |
| `src/icons.ts` | where the image files are, the picker's search, and the shelf's labels |
| `src/render/CardView.tsx` | the card. Editing is class names and handlers passed in, so the same component is what exports |
| `src/render/png.ts` | the card as an image |
| `src/render/pdf.ts` | ticked cards as one PDF: the layouts, where a card may be cut, and the file itself |
| `src/editor/` | the shelf, the row form, the library panel, *Analyze game…* and its finder, and where an added icon lands |
| `src/App.tsx` | state, undo, the three panes, the off-screen export copy |

**A row is three columns, not a canvas.** First where the **new** villagers
go (`to`), and any moved off other work to the *same* place with them, whose
source is `toFrom`: "12 boar ← All sheep". Then the ones **moved** somewhere
else: `moveTo` ← `from`, the number on where they went. Last the `extras`,
what the row only mentions. A
place is a number, its work, and then what is done on the way — "4 boar house
house" — and everything after the first icon of a counted place is drawn
small (`minorIcons`), so the work reads first. A number and the icon after it
touch, one border between them, so "4 boar" is one thing. The arrow is *drawn
because the source exists*, never placed by hand; a place takes icons and
numbers and nothing else, a move's source icons only; and `extras` take anything — a
number there ("2 deer") counts what it stands beside, never villagers, so it
carries no figure. The first version let you drop anything anywhere in a flat
list, and it was unusable; the next had one sentence a row, and "4 hunt ← 3
sheep" — three off the sheep and one new besides — was a puzzle while it
was the only way to say a move. Splitting it into "1 hunt" and "3 hunt ←
sheep" put one work in two columns of one row, and that read worse, so a move
to where the new villagers go is back in their place, as "4 hunt ← 3 sheep",
and the second column is for moves anywhere else. Each column had a
*before* place of its own for a while, with its own arrow; a row with a
building in each was five places and four arrows wide and ran off the card.

**The moves are a column, and so are the extras.** Every row with anything
after its new villagers has that column as wide as the widest such on the
card, and every row with extras has its moves' column as wide as the widest
such, so every move starts at one x and every row's extras at another
(`CardView.useColumns`, CSS variables on the card itself, so the off-screen
copy measures its own). A row with nothing after a column is left out of
its measure, or one age-up label would push every move on the card to the
right; so is a row that would not fit on one line even so. A row that does
not fit breaks between its columns — the move, then the extras, go to a line
of their own (`.step-body` wraps) — and never inside a column. Lining the
extras up on their left once ran a card off its own edge; it fits since the
rows lost their numbers, and the wrap is what keeps the odd long row on the
card. Measured rather than a CSS grid, because the rows sit in separate
phase boxes.

**A row has no number.** The circle in front of every row counted rows, or
the villagers at work, and took 66px off every row of a 1040px card for a
figure the numbers on the row already carry.

**An empty place is drawn only while something is being dragged** — or when
it is the selection, or the end of a selected row that holds nothing, so a
click on the shelf has somewhere visible to land. `App` tracks the drag in the
capture phase, since every drop target stops propagation, and ends it a turn
*after* a drop: ended at once, React re-renders before the drop reaches the
empty place's own handler, the place is gone, and the drop lands nowhere.

**A number has no column.** It is the first thing in the place it is about,
like any other item. The column it used to have was a fifth `Part` that took
one item, had to be forced visible while editing so a number had somewhere to
land, and reserved its width on every row whether or not it held anything —
which is dead space on both sides of every number. Rows no longer line up on
it; that is the trade, and it was asked for.

**Everything on a row is an entity with an id** — icons, numbers, notes — and
that is the whole reason one thing can be selected, dragged anywhere and
deleted. The moment a number is a `string` field on its container instead, it
is the one thing on the card you cannot drag, and `Del` needs a special case.
`accepts()` is what keeps that from turning into a free-for-all.

Four more rules are easy to break:

- **Anything under `.card` in `theme.css` is part of the exported PNG** —
  which is why every editing affordance is scoped to `.card--edit`, and why
  the font stack is system faces only: a webfont mid-load would export as its
  fallback.
- **The PNG is taken from the off-screen copy, never from the card you are
  editing.** `html-to-image` re-lays-out a clone, and a card carrying
  placeholders and drop targets reflows differently from the finished one —
  which showed up as row 5's icons drawn over row 6's. For the same reason
  nothing passes `width`/`height` to `toPng` (pinning them turns a reflow into
  an overlap) and `.chain` does not wrap. `shot.mjs` checks the PNG's pixel
  size against the card's own, which is what notices.
- **Every card in a PDF is the same width, so a fixed page cuts a card
  rather than shrinking it.** Every card is drawn one column wide; one taller
  than the page is cut at the last break that fits — above a phase or between
  two rows, read off the DOM by `breaks` — and carries on at the top of the
  next page. Fit it to the page instead and the long card comes out narrower
  than its neighbours, which is the one thing the PDF was asked not to do. A
  cut card is still one image in the file, drawn once per page under a clip.
  The PDF's cards are a second off-screen copy that exists only while one is
  being made, which is why `App` captures them in an effect. `shot.mjs`
  asserts one width, each card's own pixel size, and a cut that misses every
  row.
- **A phase may hold no rows, and a card may hold none at all.** `newSection`
  starts empty, `dropStep` deletes the last one, and `migrate` reads an empty
  list as empty. Every one of those used to put a blank row back, which makes
  deleting the last row a no-op you cannot see — and gives a new card five
  rows nobody asked for. The `+ row` strip is what refills a phase.
- **Adding a row selects it, which is why `addStep` takes the row.** It used
  to make one internally, so the caller had no id to select and you had to go
  and click the thing you had just asked for — half an "add". The `+ row` at
  the foot of each phase and `Enter` are the same call.
- **A card read from a game is not in the library until Save.** `App` keeps
  one `unsaved` id and leaves that card out of every `save`; reading another
  player replaces it rather than adding to it. Reading games to find a build
  is browsing, and storing every one turned the library into a history.
- **Selection is the aim** — clicking an icon on the shelf adds it to whatever
  is selected, so every click handler on the card stops propagation. Leave one
  out and selecting a row silently selects its phase, and the icon lands on the
  phase's last row instead.
- **A number's second figure is per work, and it is a claim, not a sum.**
  `totals()` keeps a running figure for each kind of work — sheep, hunt,
  berries, farms, the wood line, stragglers, gold, stone — and reads a
  number's work off the icons in its own place (`jobs.ts`). It was one total
  over the card, then one per resource; but "5" under berries and "6" under
  sheep are both food, and a card is about who is on which. A place naming no
  work — or naming a mill or a mining camp, which serve two — gets no figure
  at all rather than a meaningless one. `CountItem.total` states the figure
  outright and *sets* the running one from there on, because an absolute is a
  claim no arithmetic over the card can make. **All** is the one word
  `totals()` reads: where moved villagers go, it is everyone on the source.
- **A number on `moveTo` is how many moved, and they come off `from`** —
  which is why a source takes no number; **All** moves the source's whole
  figure. The figure under it is where they went, not what is left behind:
  the number was on the source for a while, and a card read better saying
  where people are than where they are not. A card numbering both, from
  before, said "3 off the sheep, 4 to the hunt", and `migrate` reads that as
  3 moved and 1 new. The moved column is counted before the new one, so a
  number on the left shows its work once the whole row is done: "1 hunt"
  beside "3 hunt ← sheep" reads 4 under the 1 if the hunt was empty.
- **Beside the new villagers it is the other way round.** The number on `to`
  is everyone arriving there, and the one on `toFrom` — a number or **All** —
  is how many of them came off it, so that source does take a number and
  carries no figure; with no number on `to`, the moved ones are all who
  arrived. "4 hunt ← 3 sheep" is 3 moved and 1 new, which is why it is only
  for a move to the place the new villagers went: anywhere else, the move has
  its own column.
- **Wood is the resource or a straggler, and those are two icons.** A build
  order means different things by them, and each has its own figure. The wood line,
  gold mine and stone mine icons were dropped for the resource icons
  (`resource-wood`, `-gold`, `-stone`); `migrate.RENAMED` carries old cards
  across. Every AoE2 tree either wiki has is a clump, which reads as a wood
  line whatever it is labelled, so `gaia-straggler` is Age of Mythology
  Retold's bamboo, run through `CROPPED` in the fetcher to trim it. Badging a
  tree with a Town Centre was tried too: the game's own Town Centre icon is the
  two-villager button art, unreadable at badge size.
- **A retired icon key is a broken tile, so `migrate.RENAMED` carries it.**
  The fetcher only writes the keys it still knows, and nothing deletes the rest
  — but a card naming a key the set has dropped draws nothing at all.
- **The shelf lists buildings by age, and the age is the game's own.**
  `techtree.node_ages` reads `age_id` off the same tech-tree nodes the icons
  come from — no second download, and no hand-written table to drift. It takes
  the age *most* civs give rather than the earliest: exactly one building
  differs across the 56 trees, and the Cumans' Feudal Siege Workshop should not
  move it out of Castle for everybody. Sorting is in `write_catalogue`, where
  `BY_AGE` names the categories that use it.
- **A caption is out of the layout, and that is the point.** `.cap` is
  absolutely positioned over its tile; the row reserves headroom in its
  padding instead. Put it back in flow and the one row with a `50` over its
  gold is taller than every other row, and the tiles stop lining up — which is
  the whole reason the format has a column. `shot.mjs` types a caption onto a
  row that has none and asserts nothing changes size; comparing two different
  rows only measures their dividers, since the first row of a phase has no
  top border.
- **The caret is the promise, and one reading has to keep it.** `sideOf`
  decides which half of an item the pointer is nearer; the *same* call draws
  `data-drop` on hover and picks the landing slot on drop, so what was shown
  is what happens. Compute the landing any other way and the two drift apart
  on exactly the cases nobody tests. The halves are the target, not a strip
  between items — a gap you have to hit is the thing that made reordering hard.
  A drag that ends off the card never fires `dragleave`, so `App` sweeps stray
  carets on `dragend` and `drop`.
- **A drop lands where the caret was, and the index is read before the
  source is lifted out.** `relocate` and `relocateStep` both do this, and both
  had the same bug before they did: the removal shifts everything after it
  left by one, so an index read afterwards means "before the target" in *both*
  directions — which makes dragging an item rightwards along a place put it
  back exactly where it started, silently. Read first and the one index means
  "after the target" going right and "before it" going left, which is what
  taking its place looks like either way. `addItem` is the exception and
  deliberately inserts *before*: nothing has been removed, so the thing under
  the pointer is still where it looked.
- **Three things can be dropped on the same target**, and only
  `dataTransfer.types` tells them apart: an item, a row, an icon off the
  shelf. `dropEffect` in `dragover` has to match the `effectAllowed` the drag
  started with (`copy` for the shelf, `move` for the rest) or the browser
  refuses the drop silently.
- **Nothing is read from storage or a file without `model/migrate.ts`.** A
  card is *drawn*, not validated, so one field an older version did not write
  is an exception in the middle of a render and the page goes white with the
  library still in local storage and no way to reach it. `normaliseCard` fills
  every field and carries the first version's flat item list into the three
  places — the hand-placed arrows are what says where the places divide, so
  that translation is exact. `Boundary` is the second line: it turns a render
  that still fails into a message with a download button, because the alternative
  is telling somebody to clear the only copy of their work. Six shapes so
  far; each new one is a branch in `migrate.ts`, never a new storage key.

### `replays/` — a recorded game, read into a card

The server behind the cards app's *Analyze game…*. Given a match link it
fetches aoe2companion's record of the match and Microsoft's replay (both cached
in `.data/replays/`), and writes one player's opening as a card. A replay file
opened from disk is posted as the request body instead, kept in
`.data/replays/local/` under a hash of its content, and answers to
`local-<hash>` wherever a match id would go; its teams, names and colours come
from the replay itself (`server._file_record`), since there is no record to
ask, and players are told apart by number as well as profile id because a game
against the AI repeats one. A file that turns out to be no replay is deleted
again. It serves
`cards/dist` as well, so the dialog finds it on its own origin; `npm run dev`
and `npm run preview` proxy `/api` to it.

| File | Owns |
|---|---|
| `mgzfix.py` | mgz 1.8.51 made to read save 67.2 and later, without mixing players' selections or tripping on a misread lobby setting |
| `fetch.py` | a link → the match id; the two downloads and the cache; a file opened from disk |
| `history.py` | a player by name or id, their recent games, and the seat they had in each |
| `game.py` | the commands, resolved: what a right-click lands on, where a gather point is |
| `card.py` | everything inferred, and the card format (mirrors `cards/src/model/card.ts`) |
| `strategy.py` | a player's plan in a few words, for the player list |
| `units.json` | every unit to its upgrade line; written by `tools/fetch_card_icons.py`, do not hand-edit |
| `server.py` | HTTP |

- **A replay is commands, not state.** It never says how many villagers the
  Town Centre trained: a queue click without the food is recorded like one
  with it (Benanji queued 99 in one game; 39 ever appear in a command).
  `Opening.spawns` places every villager the replay names by its id, and fills
  in between only while queue clicks were outstanding, no age-up or Loom was
  researching, and the next named villager still had room. So the villager
  counts are an inference; buildings, techs, age landings, gather points and
  right-clicks are read.
- **An id is a clock, but a slow one.** Ids are handed out in creation order
  across all players, so nothing is younger than the first command naming any
  larger id (`Replay.created_by`). That is a bound, and it can be late by a
  minute; a late bound leaves a gap in front of it that looks like villagers
  nobody commanded. So `spawns` also spaces the named villagers the way one
  Town Centre must have trained them, each as late as the ones after it allow,
  and fills only gaps that are still there. Reading bounds alone put 77 of 144
  age-up clicks above what one Town Centre could have trained by then — a
  Roman at 22 against at most 18. Two things stop the spacing: a second Town
  Centre, and an age landing, since more villagers right after one than a
  Town Centre can train came with the age (the Bengalis get two at each).
- **A cancelled building is no building.** A replay never says a building was
  finished, and a DELETE names an id and nothing else. Ids are handed out in
  creation order, so a deleted id nobody ever commanded is pinned to the last
  thing that player placed before anything that new was named
  (`PlayerLog._cancelled`). Where that is a BUILD less than `MATCH` seconds
  back, and the delete came before one villager could have finished it (the
  game data's build time), the building is left out of everything — the card,
  the strategy, a boom's count. Over 14 cached games that is about 1.5% of
  BUILDs, most deleted within five seconds of being placed. A foundation the
  enemy destroyed is not a command, so it still counts.
- **Not every new unit right-clicked onto a resource is a villager.** A
  replay never says what a unit is, and a militia clicked onto a berry bush
  reads exactly like a villager sent there. `PlayerLog.soldiers` leaves out a
  unit given soldiers' commands (formation, patrol, attack-move…) that never
  did a villager's work all game; villagers selected with soldiers get those
  commands too, which is why it is the work that decides.
- **An age-up click is the last one before the landing.** Clicks without the
  food come first, and none comes after the one that started the research: in
  144 age-ups not one fell inside its research. Counting back from the landing
  by the nominal time instead dates a Persian or Malay click too early.
- **A card dates things by when they happened, not when they were asked
  for.** A replay has the clicks, so the rest is the click plus the game
  data's time (`game.research_seconds`, `train_seconds`): a "Going" band runs
  from the research's start — the click, or later if villagers queued before
  it were still to come out, which the nominal time back from the landing
  says — to the landing; a Town Centre tech is a row when it was done, off its
  last click, since none follows the one that starts it; another building's
  tech is mentioned when it was done; a soldier when it came out; and the
  strategy line dates units and upgrades the same way. Civ bonuses to research
  and training are not read, and a queue click without the resources still
  counts, so a date is the earliest it could have been. Villagers were always
  dated by when they came out (`spawns`).
- **A Town Centre tech waits for the villagers queued ahead of it**
  (`Opening._tc_done`). The queue is first in, first out, and the next
  age-up's start is known from its landing, so when the Town Centre was still
  busy at that click, the tech was done just in time for whatever was queued
  in between: Loom clicked at 4:35 behind three villagers, with Feudal clicked
  at 6:11 and started at 6:15, was done at 6:15 — dated off its click it was
  done at 5:00, and drawn above villagers who came out before it. That
  holds only if each thing in between waited for its turn: one clicked as its
  turn came may have found the Town Centre idle for any time before it, and
  then the click is all there is. A villager clicked without the food reads
  as one that waited, so the date errs early, never late. Over 155 games this
  moves 85 of 706 Town Centre techs, nearly all Loom, by a median of 18
  seconds and at most 84. A tech with no busy age-up after it — the Town
  Centre idle when the age-up was clicked, or none clicked — is still dated
  off its click, and is early wherever villagers were queued ahead of it.
- **mgz misreads `SPECIAL` and `UNGARRISON` unit ids** by a byte (an id times
  256, plus one), so `created_by` skips them. In most games the result is over
  a million and filtered anyway; on Socotra, whose ids are small, one
  ungarrison bounded every unit of the game to 0:32 and the card counted 63
  villagers at the Feudal click.
- **An empty selection is per player *and* per command type.** mgz's `Inputs`
  cached it by type alone and handed one player's units to another's command;
  `mgzfix` turns that off and `Replay._resolve_selections` does it right. Per
  player across types is wrong too: a move straight after queueing at the Town
  Centre is not a move of the Town Centre.
- **The game data is older than the games.** `civdata.json` is VER 8.9 and the
  replays are 9.4, and a right-click on a type nothing names sets no job — so
  the move silently leaves the card. That is how a snow Arena lost every
  "sheep → hunt": its boar is a Walrus. `game.NEW_GAIA` names what is newer,
  from AoE2ScenarioParser's unit tables (an animal counts as boar or deer by
  sharing their description there; predators are left out, since a villager
  sent at a wolf is fighting it). The next patch will add more, and
  `PlayerLog.unresolved` counts the right-clicks on types it could not name —
  look there first when a card is missing a move.
- **Flank and pocket are a reading, not a field.** `history.seat` takes the
  colour in ranked games and the slot in a lobby, for 3v3 and up only, and
  says nothing on a nomad start, where there is no arc of bases to be on the
  end of.
- **The finder filters in the browser.** `recent_games` fetches up to 900 games
  or four months once, and every filter is a pass over that list, so changing
  one costs no request; older games are not fetched because their replays are
  gone. Each listed game's plan is filled in afterwards, two at a time, and
  only for rows scrolled into view (`editor/strategies.ts`): every one is a
  replay of 2.5–7.5 MB to download and read, and a history is up to 900 games.
  `/api/games/{match}/strategy/{profile}` takes the match record the history
  already fetched (`history.played`) rather than asking aoe2companion again,
  keeps the parsed game out of the cards' own cache so browsing cannot push
  out the game being imported, and saves each plan to
  `.data/replays/strategies.json` signed with a hash of `game.py`,
  `strategy.py` and `units.json` — change the rules and every saved plan is
  read again.
- **Buildings follow the work, techs are extras — except the Town
  Centre's.** Loom, Wheelbarrow, Town Watch and anything else researched at
  the Town Centre is a step of its own, like an age-up: it is the Town
  Centre's work for that while, not a mention on someone's row. A house, a
  market or a Town Centre goes up on the way, so `card.py` puts it after the
  work in the same place, beside any camp the row's villagers dropped, and the
  card draws it small; a building with no icon is named in the extras,
  since a place takes icons and numbers only. Every building placed is drawn
  once: a camp several rows' villagers helped build sits on the first of them,
  a camp counts as on the way only in the first `ON_THE_WAY` seconds of its
  builders' step (the same crew's second lumber camp ten minutes later went
  up when it went up, not beside the first),
  a camp no step claimed goes up on the way like a house, and walls — a
  dragged wall is a `WALL` command, not a `BUILD` — are drawn once per phase
  band. A tech with no icon of its own wears its unit's if it is that unit's
  upgrade (Man-at-Arms), as its button in the game does, and a unit with no
  icon of its own wears its line's (`units.json`): the icon set has the first
  unit of every line, not every upgrade.
- **A strategy is plans in time order** (`strategy.py`): the unit lines made,
  towers and castles built forward, a douche (the starting Town Centre
  deleted and a Town Centre built forward after it), a boom (two or more Town
  Centres after the first) and a fast imp (Imperial clicked within five minutes of reaching
  Castle Age). Plans overlapping inside one age are joined with a comma, the
  next one with an arrow. Three readings are easy to get wrong:
  - a replay queues a line's *first* unit whatever is researched, so a unit is
    named as the upgrade its line had at the click — scouts, light cavalry,
    hussars — read off the research of the same name;
  - militia are a drush only if Man-at-Arms never came before Castle Age;
    otherwise they were the start of a men-at-arms rush;
  - forward is within 40 tiles of an enemy's starting Town Centre *and*
    clearly (0.75×) nearer it than any Town Centre of one's own team
    (`Replay.forward`, which the card reads too). Against one's own Town
    Centre alone, a pocket's castle by the flank's base read as a castle
    drop.
  Every threshold there is judgement, not measurement, and units are counted
  off queue clicks, which include the unpaid ones.
- **Pastures are farms.** The Khitans' pasture is building 1889, which mgz
  cannot name (`game.NEW_BUILDINGS`); a villager who builds or is sent to one
  is on the pasture, a job and a figure of its own, drawn with its own icon.
- **Villagers sent to the enemy are forward, and forward is no work.** A
  tower rush, a castle drop, a douche, a forward barracks: the villagers who
  walk there are taken off their work on the card — "10 forward tower ←
  sheep", forward wearing the game's own aggressive-stance button
  (`command-forward`, the one icon the fetcher takes for a command) — and
  come back off it — "9 stone ← forward" — when they are next given work at
  home or at the enemy's gold. A walk is read off `MOVE` commands to a forward
  spot, a fight off a right-click there on anything that is not one's own
  building, and laming off one on a sheep, boar or deer there; helping to
  build is a right-click on one's own foundation. A trip only counts if its
  villagers fight, lame, or put up or help build a tower, a castle, a Town
  Centre, a barracks, range, stable or siege workshop there (`card.FRONT`):
  without that rule a team game's wall along its front and a walk out to a
  far gold mine read as forward, and on Socotra, whose Town Centres are 45 tiles
  apart, so does anything a few tiles past the middle. Fights are in because
  on Socotra villager fights and laming are the game; they also catch
  villagers knocking down an Arena wall at the enemy's, which is forward but
  no plan the strategy line names. A forward walk is its own event kind, not an
  `assign`, because the units in it need not be villagers, and `spawns` only
  believes work.
- **An imported card numbers villagers, and the "Going" bands not at all.**
  The Town Centre is researching through them, so no villager is added there:
  one first put to work in a Going band is written at the end of the band
  before (`Opening._before_going`). Of 206 such villagers over 88 cards, about
  half were still in the Town Centre's queue at the click — which puts the
  age-up behind them, which is why the band starts when the research does —
  most of the rest had stood idle, and 15 came from a second Town Centre,
  which really can train during the research; the card leaves the band to
  moves anyway. So is a Town Centre tech clicked during the research: the
  queue puts it behind the age-up, so its row comes after the landing
  (`Opening._tc_start`). Units made are mentioned, in the extras of the row
  being worked when the first of them came out in that phase, like a tech
  from any other building.
- **A task held under 30 seconds, or given up before the villager got there,
  never happened** (`card.BRIEF`, `_begun`). A villager sent somewhere and
  sent on again sooner than that — a misclick, a change of mind, a gather
  point left at once, a new villager on the sheep sent on to the boar, the
  wood swapped for the boar while still walking to the trees — is drawn going
  straight to where they went next, and a detour back to the same work is no
  move at all. Gold, stone and a building site count from 15 seconds
  (`ERRAND`), there and straight back included: a build order sends
  villagers for "50 stone", or to put up a camp and go, and dropping a short
  stint as an errand once took exactly those off the card. The walk is a
  straight line at the villager's speed in the game data, from where the
  previous command had got them to; a run of commands to one work is timed by
  its first target, since stepping between carcasses or trees is the work
  itself. Over 106 cards, 30 seconds rather than 15 drops 4% of villager
  steps and 1.5% of rows, most of them between the sheep and the hunt, and
  the exception keeps 40 of those steps and 21 of the rows.
- **A row's new villagers are the first column, its moved ones the second
  — unless they went to the same place.** Three off the sheep and one new to
  the hunt is "4 hunt ← 3 sheep", one place. New villagers to one place and a
  move to another at the same time are one row — "2 wood", "2 boar ← sheep",
  "2 deer", or "4 hunt ← 3 sheep", "1 wood ← berries" — unless the first
  column names the move's source or destination, where counting the move
  first would be the wrong order (`_paired`). A move joins the latest move row
  of the phase when it is the same move, however long after, so "1 farm ←
  sheep" and then "2 farm ← sheep" are "3 farm ← sheep". A new villager reaching the same place within
  `MERGE` seconds of a move is folded into it, which makes the lure and the
  crew that follows it one row; one sent where the row before it went joins
  that row however long after, so one villager off the sheep building the mill
  and the next four sent to the berries are "4 berries" and
  "1 berries mill ← sheep". The new villagers' column names a place once in
  a run: "1 wood lumber camp" and then "3 wood" are "4 wood lumber camp",
  across rows that only move others, but never across one that takes anyone
  off that work. A camp sits in the column of whoever built it
  (`via_moved`, `via_new`), and both go with the place when the move shares
  the new villagers'; the other buildings of the moment go with the new
  villagers, or with the move on a row that has none. A move is written with
  its number and never **All**: the app would move the card's whole figure for
  it, and where the replay's "nobody left" and the card's count disagree, All
  would carry the difference somewhere it never went. The deer go in the
  extras as one number and one deer. The card draws no figure under a word (`CardView`, `countbox--word`),
  and draws the word quieter than a number.
- **Grouping must not cost the figures their truth.** A card's figures are
  read top to bottom, and a row gathers moves from a span of time, so three
  rules keep them equal to the replay's own reading at the end of every phase
  band (440 of 440 over 13 games, a villager first sent during an age-up read
  as sent at its click): a move joins a row only if its villager was
  already on the source when the row began; a new villager folds into another
  row only while still there when that row starts; and never across a row that
  moves anyone on or off the same work. Each was a real drift — "All" off the
  sheep followed by two villagers who had left with it, a straggler row that
  folded in someone already gone to the farms. Moves never group across a
  phase band either.
- **Boar and deer are one job on a card: hunt.** `card_job` folds them before
  anything is grouped, so a crew stepping from the deer to the boar is no row
  at all, and the boar icon stands for the hunt. The deer are only
  mentioned, in the extras: one per deer somebody was right-clicked or rallied
  onto, drawn on the first row that went for it, so a card's deer add up to the
  herd. Villagers walk on to the next carcass by themselves, so that is at most
  the deer eaten. `game.py` still tells boar from deer; folding them is a
  card's choice of words, not a reading of the replay.
- **What goes up on the way never splits a row.** A drop-off site is matched to
  the step its builder was on (`transitions`, by job) rather than being a step:
  a mill built by someone already on the berries changes no job, and a build
  followed by a click on the same camp reads as a misclick. Rows group by
  source and destination only, so one villager building the mill and four
  more following are one row.


## Running it

```powershell
python -m pip install -r requirements.txt
cd cards; npm ci; npm run build; cd ..
python -m uvicorn replays.server:app --port 8030    # editor + "Analyze game…" at http://localhost:8030/

cd cards; npm run dev                                # editor on :5173, /api proxied to :8030
```

## Verifying a change

```powershell
python tools/check.py                                # the reader's offline checks
cd cards; npm run build; npm run preview -- --port 8020
cd cards; node shot.mjs                              # drives the editor, writes editor.png, card.png and cards.pdf
```

`shot.mjs` needs `npm i --no-save playwright` and is the editor's whole test:
it downloads the PNG and the PDF rather than trusting that the buttons are
wired up. Add a reader check as a function in `tools/check.py` that takes
`fail` and calls it with a sentence per problem, and list it in `CHECKS`.

Reading a real game needs the network and a replay Microsoft still keeps, so
the rest is checked by hand: run the server, open *Analyze game…* on a match
from the last few weeks, and import a player. A card that changes for a replay
that did not is the regression to look for.

## Conventions

- **Comments explain why, never what.** Most code here needs none.
- `replays/units.json`, `cards/src/icons.generated.ts` and the icons are
  written by `tools/fetch_card_icons.py`; do not hand-edit them.
