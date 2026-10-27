/**
 * Drives the editor headlessly: the fastest way to see that a change did not
 * break it. Needs `npm i --no-save playwright` and a server on port 8020
 * (`npm run preview -- --port 8020`).
 *
 * Writes editor.png (the whole app) and card.png (what the Download button
 * produced), so the export path is exercised rather than assumed.
 */

import { chromium } from "playwright";
import { writeFile } from "node:fs/promises";

const URL = process.env.CARDS_URL ?? "http://127.0.0.1:8020/";

const fail = (message) => { console.error(`FAIL ${message}`); process.exitCode = 1; };
const ok = (message) => console.log(`  ok  ${message}`);
const check = (condition, good, bad) => (condition ? ok(good) : fail(bad));

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1800, height: 1100 } });
await page.goto(URL);
await page.waitForSelector(".canvas .card");
// The tiles are what the card is made of; a card drawn before they load would
// screenshot as 95 empty boxes.
await page.waitForFunction(() =>
  [...document.querySelectorAll(".card img")].every((img) => img.complete && img.naturalWidth > 0));

const rows = page.locator(".canvas .card .step");
const row = (n) => rows.nth(n);
const iconsIn = (n, part) => row(n).locator(`.slot--${part} .item--icon`);

const title = await page.textContent(".canvas .card-head h1");
check(title === "MAA + Tower", `opens on “${title}”`, `title was “${title}”`);
check(await rows.count() === 9, "9 rows", `saw ${await rows.count()} rows`);

/** Starts a drag from `source` and leaves it in the air: empty places are
 *  drawn only once a drag is under way, so they cannot be aimed at before. */
async function lift(source) {
  await source.hover();
  await page.mouse.down();
  const box = await source.boundingBox();
  await page.mouse.move(box.x + box.width / 2 + 12, box.y + box.height / 2 + 12, { steps: 3 });
}

/** Drags `source` onto a place that may only exist while dragging. */
async function dragInto(source, target) {
  await lift(source);
  await target.hover();
  await page.mouse.up();
}

// The militia row has neither a move nor extras. At rest only what it holds
// is drawn; once a drag is under way, every place it could take is.
const hintsOf = (n) => row(n).locator(".slot, .extras").evaluateAll((els) => els.map((e) => e.dataset.hint));
const atRest = await hintsOf(6);
await lift(page.locator(".palette .icon-btn").first());
const dragging = await hintsOf(6);
await page.mouse.move(5, 5);
await page.mouse.up();
check(atRest.join("|") === "end" && dragging.join("|") === "end|moved to|source|extras",
  "empty places are drawn only while dragging",
  `row 7 showed ${atRest.join("|")} at rest and ${dragging.join("|")} while dragging`);

check(await page.locator(".canvas .card .step-count").count() === 0,
  "there is no number column", "a number column is still being drawn");

// Measured on the export copy: the edited card pads its places to give drop
// targets a hit area, and that padding is not part of the picture.
const firstGap = await page.locator(".export-copy .card .step").first().evaluate((e) => {
  const no = e.querySelector(".step-no").getBoundingClientRect();
  const first = e.querySelector(".slot--to .item").getBoundingClientRect();
  return Math.round(first.left - no.right);
});
check(firstGap === 14, "the number sits one gap after the row number",
  `the gap after the row number is ${firstGap}px`);

// --- numbers carry their own value and the running total ------------------

// 6 on sheep is 6 on sheep; 4 on wood is 4 on the wood line, not 10 of
// anything. All six off the sheep go to the hunt, so 6 new make it 12; 3 of
// them to the stone are 3 there. "All" is a word and carries no figure; a
// tower or a militia names no work, so it carries none either.
const numbers = await page.$$eval(".canvas .card .countbox",
  (els) => els.map((e) => [e.querySelector("b")?.textContent, e.querySelector("i")?.textContent ?? null]));
const wanted = [["6", "6"], ["4", "4"], ["6", "12"], ["All", null], ["3", "3"], ["5", null], ["3", null]];
check(JSON.stringify(numbers) === JSON.stringify(wanted),
  "each number totals its own work, and a move carries its villagers",
  `the numbers were ${JSON.stringify(numbers)}`);

// Counting villagers, a row wears every work's figure added up. A move keeps
// the total; the five sent to the tower go to no work the card counts, so the
// number on where they went is what came off the hunt: make it 7 and 9 are left.
await page.click(".canvas .card-head");
await page.locator(".inspector label:has-text('Row numbers count') + select").selectOption("villagers");
const byVillagers = await rows.evaluateAll((els) => els.slice(0, 6).map((e) => e.querySelector(".step-no")?.textContent));
await row(5).locator(".slot--moveTo .countbox").click();
await page.locator(".inspector label:has-text('Number') + input").fill("7");
const afterSeven = await row(5).locator(".step-no").textContent();
await page.click(".topbar button:has-text('Undo')");
await page.click(".topbar button:has-text('Undo')");
check(JSON.stringify(byVillagers) === JSON.stringify(["6", "10", "16", "16", "16", "11"]),
  "row numbers can count villagers, and a move keeps the total",
  `the first six rows were numbered ${JSON.stringify(byVillagers)}, wanted 6, 10, 16, 16, 16, 11`);
check(afterSeven === "9", "the number where moved villagers go takes them off the source",
  `7 off the hunt left the row at ${afterSeven}, wanted 9`);

// "4 boar": a number and its icon are one thing, and what is done on the way
// after the work is drawn small.
const [numberRight, iconLeft] = await row(4).locator(".slot--moveTo .item").evaluateAll((els) =>
  [els[0].getBoundingClientRect().right, els[1].getBoundingClientRect().left].map(Math.round));
const [workTile, wayTile] = await row(4).locator(".slot--moveTo .tile").evaluateAll((els) =>
  els.map((e) => Math.round(e.getBoundingClientRect().height)));
check(numberRight === iconLeft && wayTile < workTile,
  "a number touches its icon, and what is done on the way is small",
  `the number ends at ${numberRight} and the icon starts at ${iconLeft}; tiles ${workTile} and ${wayTile}px`);

// Three columns: every move starts at one x, and every row's extras end at one.
const edgesOf = (rows, part, edge) => page.locator(`.export-copy .card ${rows}`).evaluateAll((els, [part, edge]) =>
  els.map((e) => Math.round(e.querySelector(part).getBoundingClientRect()[edge])), [part, edge]);
const moveLefts = await edgesOf(".step--moves", ".column--move .slot", "left");
const extrasRights = await edgesOf(".step--extras", ".extras", "right");
check(moveLefts.length === 4 && new Set(moveLefts).size === 1 && extrasRights.length === 2 && new Set(extrasRights).size === 1,
  "moves and extras each form a column",
  `moves started at ${moveLefts.join(", ")} and extras ended at ${extrasRights.join(", ")}`);

// --- a caption must not move anything -------------------------------------

const middles = await row(4).locator(".tile").evaluateAll(
  (els) => els.map((e) => { const r = e.getBoundingClientRect(); return Math.round(r.top + r.height / 2); }));
check(new Set(middles).size === 1, "every tile on a row sits on one line",
  `tile middles on row 5 were ${middles.join(", ")}`);

// Put a caption on a row that has none and watch nothing move. Comparing two
// different rows would only have measured their dividers.
const heightOf = (n) => row(n).evaluate((e) => Math.round(e.getBoundingClientRect().height));
const cardHeight = () => page.locator(".canvas .card").evaluate(
  (e) => Math.round(e.getBoundingClientRect().height));
const [wasRow, wasCard] = [await heightOf(5), await cardHeight()];
await iconsIn(5, "moveTo").first().click();
await page.fill('.inspector input[placeholder="e.g. 50"]', "140");
const [nowRow, nowCard] = [await heightOf(5), await cardHeight()];
check(nowRow === wasRow && nowCard === wasCard,
  "a caption changes no measurement on the card",
  `the row went ${wasRow}→${nowRow}px and the card ${wasCard}→${nowCard}px`);
await page.click(".topbar button:has-text('Undo')");

// --- the shelf, by click and by drag --------------------------------------

await row(0).locator(".step-no").click();
const before = await iconsIn(0, "to").count();
await page.click(".palette .icon-btn >> nth=0");
check(await iconsIn(0, "to").count() === before + 1,
  "the shelf adds to the selected row", "clicking the shelf added nothing");
await page.click(".topbar button:has-text('Undo')");
check(await iconsIn(0, "to").count() === before, "undo puts it back", "undo did not restore the row");

await dragInto(page.locator(".palette .icon-btn").first(), row(6).locator(".slot--from"));
check(await iconsIn(6, "from").count() === 1,
  "an icon drags from the shelf onto a place", "the shelf drag landed nowhere");
await page.click(".topbar button:has-text('Undo')");

const hadNumbers = await row(3).locator(".countbox").count();
await page.locator(".palette .number-btn").nth(6).dragTo(row(3).locator(".slot--to"));
const gotNumber = await row(3).locator(".slot--to .countbox b").last().textContent().catch(() => null);
check(hadNumbers === 0 && gotNumber === "7",
  "a number drags from the shelf into a place",
  `row 4 had ${hadNumbers} numbers and now reads ${gotNumber}`);
await page.click(".topbar button:has-text('Undo')");

// --- Del removes whatever is selected -------------------------------------

await iconsIn(2, "from").first().click();
const panel = await page.textContent(".inspector");
check(panel.includes("Caption above the tile"),
  "selecting an icon opens its fields", "icon fields did not open");
check(!panel.includes("Number the rows"),
  "the inspector shows one entity at a time", "the phase panel was showing too");

await page.keyboard.press("Delete");
check(await iconsIn(2, "from").count() === 0, "Del removes the selected item", "Del did nothing");

await row(2).locator(".step-no").click();
await page.keyboard.press("Delete");
check(await rows.count() === 8, "Del removes the selected row", `still ${await rows.count()} rows`);
await page.click(".topbar button:has-text('Undo')");
await page.click(".topbar button:has-text('Undo')");
check(await rows.count() === 9, "undo brings the row back", `left with ${await rows.count()} rows`);

// --- adding a row ---------------------------------------------------------

const darkAge = page.locator(".canvas .card .phase").first();
const before9 = await rows.count();
await darkAge.locator(".add-row").click();
const selectedCrumb = await page.textContent(".inspector .crumb.on");
await page.keyboard.press("Enter");
const after = await rows.count();
await page.click(".topbar button:has-text('Undo')");
await page.click(".topbar button:has-text('Undo')");
check(after === before9 + 2 && selectedCrumb === "Row" && await rows.count() === before9,
  "the + adds a row and selects it, and Enter adds another",
  `rows went ${before9} → ${after}, crumb was ${selectedCrumb}`);

check(await page.locator(".export-copy .add-row").count() === 0,
  "the + is not in the export", "the add-row button reached the export copy");

// A phase is allowed to hold nothing: emptying one must not hand a blank row
// straight back, or deleting the last row is a no-op you cannot see.
const feudal = page.locator(".canvas .card .phase").last();
const had = await feudal.locator(".step").count();
for (let i = 0; i < had; i++) {
  await feudal.locator(".step").first().click();
  await page.keyboard.press("Delete");
}
const leftWith = await feudal.locator(".step").count();
const stillThere = await page.locator(".canvas .card .phase").count();
for (let i = 0; i < had; i++) await page.click(".topbar button:has-text('Undo')");
check(had > 0 && leftWith === 0 && stillThere === 3 && await feudal.locator(".step").count() === had,
  "a phase can be emptied of rows and stays a phase",
  `${had} rows → ${leftWith}, ${stillThere} phases`);

// --- dragging a whole row -------------------------------------------------

const rowOrder = () => page.$$eval(".canvas .card .step",
  (els) => els.map((e) => e.querySelector(".slot--to .item--icon img")?.src.split("/").pop() ?? "-"));
const was = await rowOrder();
await row(0).locator(".grip").dragTo(row(2));
const now = await rowOrder();
check(now[2] === was[0] && now[0] === was[1], "a row drags to another position",
  `order went ${was.slice(0, 3)} → ${now.slice(0, 3)}`);
await page.click(".topbar button:has-text('Undo')");

// --- reordering inside one place ------------------------------------------

const secondRow = page.locator(".canvas .card .step").nth(1);
const inPlace = secondRow.locator(".slot--to .item");
const order = () => inPlace.evaluateAll((els) => els.map((e) =>
  e.querySelector("img")?.src.split("/").pop() ?? `#${e.querySelector("b")?.textContent}`).join("|"));

/** Drag one item onto a chosen edge of another, reporting the caret the card
 *  drew while the pointer was there. Aim well inside the half rather than at
 *  the very edge: a synthetic drag's last `dragover` can land a few pixels
 *  short, which a hand holding the pointer there never does. */
async function dragOnto(fromN, toN, fraction) {
  const [a, c] = [await inPlace.nth(fromN).boundingBox(), await inPlace.nth(toN).boundingBox()];
  await page.mouse.move(a.x + a.width / 2, a.y + a.height / 2);
  await page.mouse.down();
  await page.mouse.move(c.x + c.width * fraction, c.y + c.height / 2, { steps: 12 });
  const caret = await inPlace.nth(toN).getAttribute("data-drop");
  await page.mouse.up();
  return caret;
}

const start = await order();
const caret = await dragOnto(0, 2, 0.75);
const afterDrop = await order();
await page.click(".topbar button:has-text('Undo')");
// The caret is the promise; the order is whether it was kept. Both directions,
// because only dragging rightwards was ever broken.
check(caret === "after" && afterDrop === "resource-wood.png|tech-double-bit-axe.png|#4",
  "the caret says which edge, and the item lands there",
  `caret ${caret}, ${start} → ${afterDrop}`);

const leftCaret = await dragOnto(0, 2, 0.35);
const leftDrop = await order();
await page.click(".topbar button:has-text('Undo')");
check(leftCaret === "before" && leftDrop === "resource-wood.png|#4|tech-double-bit-axe.png",
  "aiming at the other edge lands on the other side",
  `caret ${leftCaret}, ${start} → ${leftDrop}`);

check(await page.locator("[data-drop]").count() === 0,
  "no caret is left behind", "a caret survived the drop");

await inPlace.nth(0).click();
await page.keyboard.press("ArrowRight");
const nudged = await order();
await page.keyboard.press("ArrowLeft");
check(nudged === "resource-wood.png|#4|tech-double-bit-axe.png" && await order() === start,
  "the arrow keys nudge the selected item", `arrow keys gave ${nudged}`);

// --- an item between rows -------------------------------------------------

const grew = await iconsIn(2, "to").count();
await iconsIn(0, "to").first().dragTo(iconsIn(2, "to").first());
const landed = await iconsIn(2, "to").count();
const emptied = await iconsIn(0, "to").count();
check(landed === grew + 1 && emptied === 0, "an item drags to another row",
  `row 3 went ${grew} → ${landed}, row 1 left with ${emptied}`);
await page.click(".topbar button:has-text('Undo')");

// --- a row too long for one line ------------------------------------------

// Its move goes to a line of its own, and does not drag every other move on
// the card out of line with it. Left in place for the export, which has to
// break the row exactly as the card does.
await row(2).locator(".slot--to").click({ position: { x: 3, y: 3 } });
for (let i = 0; i < 12; i++) await page.click(".palette .icon-btn >> nth=0");
const broken = await page.locator(".export-copy .card .step").nth(2).evaluate((e) => {
  const [fresh, move] = [".column--new", ".column--move"].map((c) => e.querySelector(c).getBoundingClientRect());
  return move.top >= fresh.bottom - 1;
});
const stillLined = await edgesOf(".step--moves", ".column--move .slot", "left");
check(broken && stillLined.length === 4 && new Set(stillLined.slice(1)).size === 1,
  "a row too long for one line breaks before its move, and the other moves stay in line",
  `broke: ${broken}; moves started at ${stillLined.join(", ")}`);

// --- the library and the export -------------------------------------------

await page.click(".topbar button:has-text('Library')");
await page.waitForSelector(".modal");
ok("library opens");
await page.click(".modal button:has-text('Close')");

const download = page.waitForEvent("download", { timeout: 30000 });
await page.click(".topbar button:has-text('Export')");
await page.click(".topbar .menu button:has-text('Image')");
const file = await download;
const png = await (await file.createReadStream()).toArray().then(Buffer.concat);
await writeFile("card.png", png);
ok(`exported ${file.suggestedFilename()}`);

// The export is a clone, and a clone that lays out differently silently
// overlaps rows instead of failing. Its size is the cheapest thing that
// notices: off by a pixel and something reflowed.
const SCALE = 2;
const box = await page.locator(".export-copy .card").evaluate((node) => {
  const rect = node.getBoundingClientRect();
  return { w: Math.round(rect.width), h: Math.round(rect.height) };
});
const [w, h] = [png.readUInt32BE(16), png.readUInt32BE(20)];
check(Math.abs(w - box.w * SCALE) <= 2 && Math.abs(h - box.h * SCALE) <= 2,
  `the PNG is ${w}×${h}, the card's own size at ${SCALE}×`,
  `PNG ${w}×${h} against a card of ${box.w}×${box.h} — the export reflowed`);

for (let i = 0; i < 12; i++) await page.click(".topbar button:has-text('Undo')");

// --- zoom, which the export must not see ----------------------------------

const level = () => page.textContent(".zoom .level");
await page.click(".zoom button >> nth=2");
const zoomed = await level();
const still = await page.locator(".export-copy .card").evaluate(
  (node) => Math.round(node.getBoundingClientRect().width));
check(zoomed !== "100%" && still === box.w,
  `zoom went to ${zoomed} and left the export at ${still}px`,
  `zoom showed ${zoomed}; the export copy is ${still}px against ${box.w}px`);
await page.click(".zoom .level");
check(await level() === "100%", "the level resets", `reset left it at ${await level()}`);

// Leave a row selected, so the screenshot shows the row form and not just the
// card panel — that form is the thing most likely to regress unseen.
await row(4).locator(".step-no").click();
await page.screenshot({ path: "editor.png", fullPage: false });

// --- several cards as one PDF ---------------------------------------------

// A long card beside a short one. On an A4 page one across, the long one does
// not fit: it has to be cut between two rows, not shrunk narrower than the other.
const exportBox = () => page.locator(".export-copy .card").evaluate((node) => {
  const rect = node.getBoundingClientRect();
  return { w: Math.round(rect.width), h: Math.round(rect.height) };
});
for (let i = 0; i < 4; i++) await page.keyboard.press("Enter");
const long = await exportBox();
const longRows = await page.locator(".export-copy .card").evaluate((card) => {
  const box = card.getBoundingClientRect();
  return [...card.querySelectorAll(".step")].map((step) => {
    const rect = step.getBoundingClientRect();
    return [(rect.top - box.top) / box.height, (rect.bottom - box.top) / box.height];
  });
});
check(long.h / long.w > Math.SQRT2, `the long card is ${long.w}×${long.h}, taller than A4`,
  `the long card is only ${long.w}×${long.h}, which an A4 page holds anyway`);
await page.click(".topbar button:has-text('Library')");
await page.click(".modal button:has-text('New card')");
const cardBoxes = [long, await exportBox()];

/** Both cards, laid out as `layout`, read back page by page. A slice is the
 *  part of one card drawn on one page, with `from` and `to` as fractions of
 *  the card's height. */
async function exportPdf(layout) {
  await page.click(".topbar button:has-text('Library')");
  await page.locator(".modal .entry input[type=checkbox]").first().check();
  await page.selectOption(".modal select", { label: layout });
  const download = page.waitForEvent("download", { timeout: 60000 });
  await page.keyboard.press("Control+P");
  const file = await download;
  const bytes = await (await file.createReadStream()).toArray().then(Buffer.concat);
  await page.click(".modal button:has-text('Close')");
  const text = bytes.toString("latin1");
  const slice = /q ([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+) re W n ([\d.]+) 0 0 ([\d.]+) ([\d.]+) (-?[\d.]+) cm \/Im(\d+) Do Q/g;
  return {
    bytes,
    name: file.suggestedFilename(),
    images: [...text.matchAll(/\/Width (\d+) \/Height (\d+)/g)].map((m) => [+m[1], +m[2]]),
    pages: text.split("/Type /Page /Parent").slice(1).map((chunk) => ({
      size: chunk.match(/\/MediaBox \[0 0 ([\d.]+) ([\d.]+)\]/).slice(1).map(Number),
      slices: [...chunk.matchAll(slice)].map((m) => {
        const [, , clipY, , clipH, width, height, , y, card] = m.map(Number);
        const from = (y + height - (clipY + clipH)) / height;
        return { card, x: +m[1], top: clipY + clipH, width, height, from, to: from + clipH / height };
      }),
    })),
  };
}
const near = (a, b, by = 0.01) => Math.abs(a - b) <= by;
const widths = (pdf) => new Set(pdf.pages.flatMap((p) => p.slices.map((s) => s.width)));

const pair = await exportPdf("A4, two across");
ok(`exported ${pair.name}`);
const [left, right] = pair.pages[0]?.slices ?? [];
check(pair.pages.length === 1 && near(pair.pages[0].size[0], 595.28) && near(pair.pages[0].size[1], 841.89)
  && left && right && near(left.top, right.top) && left.x < right.x,
  "two cards side by side on one A4 page",
  `${pair.pages.length} pages: ${JSON.stringify(pair.pages)}`);
check(widths(pair).size === 1 && [left, right].every((s) => s && s.from === 0 && near(s.to, 1)),
  `both whole, both ${left?.width}pt wide`, `slices ${JSON.stringify([left, right])}`);
check([left, right].every((s, i) => s && near(s.height / s.width, pair.images[i][1] / pair.images[i][0], 0.001)),
  "no card is stretched", `slices ${JSON.stringify([left, right])} against images ${JSON.stringify(pair.images)}`);
// The same reflow check as the PNG's, on copies rendered only for the PDF.
check(pair.images.length === 2 && pair.images.every(([w, h], i) =>
  Math.abs(w - cardBoxes[i].w * SCALE) <= 2 && Math.abs(h - cardBoxes[i].h * SCALE) <= 2),
  "each PDF image is its card's own size",
  `images ${JSON.stringify(pair.images)} against cards ${JSON.stringify(cardBoxes)} at ${SCALE}×`);

const middle = await exportPdf("A4, one in the middle");
check(middle.pages.length === 2 && middle.pages.every((p) => near(p.size[0], 595.28) && near(p.size[1], 841.89)
  && p.slices.length === 1 && p.slices[0].from === 0 && near(p.slices[0].to, 1)),
  "one in the middle: one whole card to each A4 page", `pages ${JSON.stringify(middle.pages)}`);
const [alone] = widths(middle);
check(widths(middle).size === 1 && near(alone, (left?.width * 5) / 4, 0.05),
  `every card ${alone}pt wide, 5/4 of two across`,
  `widths ${[...widths(middle)]} against ${left?.width}pt two across`);
check(middle.pages.every(({ size: [w, h], slices: [s] }) =>
  near(2 * s.x + s.width, w, 0.05) && near(s.top, h - 24, 0.05)),
  "each card is centred across its page, at the top", `pages ${JSON.stringify(middle.pages)}`);
await writeFile("cards.pdf", middle.bytes);

const one = await exportPdf("A4, one across");
const longSlices = one.pages.flatMap((p, n) => p.slices.filter((s) => s.card === 0).map((s) => ({ ...s, page: n })));
const cut = longSlices[0]?.to;
check(one.pages.every((p) => near(p.size[0], 595.28) && near(p.size[1], 841.89)) && widths(one).size === 1,
  `one across: ${one.pages.length} A4 pages, every card ${[...widths(one)]}pt wide`,
  `pages ${JSON.stringify(one.pages.map((p) => p.size))}, widths ${[...widths(one)]}`);
check(longSlices.length === 2 && longSlices[1].page === longSlices[0].page + 1
  && near(longSlices[1].from, cut, 1e-4) && near(longSlices[1].to, 1),
  "the long card carries on at the top of the next page", `its slices were ${JSON.stringify(longSlices)}`);
check(cut !== undefined && longRows.every(([top, bottom]) => cut <= top + 1e-3 || cut >= bottom - 1e-3),
  `the cut falls between two rows, ${Math.round(cut * long.h)}px down`,
  `the cut at ${cut} goes through a row: ${JSON.stringify(longRows)}`);

const tall = await exportPdf("A page per card");
check(tall.pages.length === 2 && widths(tall).size === 1 && tall.pages.every((p) =>
  p.slices.length === 1 && near(p.size[0], 595.28) && near(p.size[1], p.slices[0].height + 48)),
  "a page per card: each page as tall as its card",
  `pages ${JSON.stringify(tall.pages)}`);

const screen = page.waitForEvent("download", { timeout: 60000 });
await page.keyboard.press("Control+P");
const lone = await (await (await screen).createReadStream()).toArray().then(Buffer.concat);
const loneImages = lone.toString("latin1").match(/\/Width \d+ \/Height \d+/g) ?? [];
check(loneImages.length === 1, "Ctrl P in the editor makes a PDF of the card on screen",
  `the editor's PDF held ${loneImages.length} cards`);

const printed = page.waitForEvent("download", { timeout: 60000 });
await page.click(".topbar button:has-text('Export')");
await page.click(".topbar .menu button:has-text('Print')");
check((await printed).suggestedFilename().endsWith(".pdf"), "Export ▸ Print is the same PDF",
  "Export ▸ Print downloaded no PDF");

await browser.close();
console.log(process.exitCode ? "shot: failures above" : "shot: all good");
