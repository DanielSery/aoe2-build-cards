/**
 * State, undo, saving, and the three panes.
 *
 * The library is this browser's local storage and the only way a card leaves
 * the machine is the PNG, the PDF or the JSON. The one server the app ever
 * talks to is the replay reader behind "Analyze game…" (`model/games.ts`), and
 * what it hands back is not stored until you press Save: reading games to find
 * a build is browsing, and the library should hold the ones you kept.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { Card, Where } from "./model/card";
import { addItem, addStep, count, dropItem, dropSection, dropStep, icon, moveItem,
         moveStep, newCard, newStep, reborn, relocate, relocateStep } from "./model/card";
import { download, fileName, load, read, save } from "./model/library";
import { sampleCard } from "./model/samples";
import { CardView } from "./render/CardView";
import type { Edit } from "./render/CardView";
import { cardsToPdf, SHEETS } from "./render/pdf";
import type { SheetName } from "./render/pdf";
import { cardToPng } from "./render/png";
import { FromGame } from "./editor/FromGame";
import { Inspector } from "./editor/Inspector";
import { Library } from "./editor/Library";
import { Palette } from "./editor/Palette";
import { appendTarget, partName } from "./editor/target";

const boot = (): Card[] => {
  const saved = load();
  return saved.length ? saved : [sampleCard()];
};

const ZOOMS = [0.4, 0.5, 0.6, 0.75, 0.9, 1, 1.15, 1.35, 1.6, 2];

const typing = (target: EventTarget | null) => {
  const tag = (target as HTMLElement | null)?.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
};

export function App() {
  const [cards, setCards] = useState<Card[]>(boot);
  const [currentId, setCurrentId] = useState<string>(() => cards[0]?.id ?? "");
  const [selected, setSelected] = useState<Where | null>(null);
  const [past, setPast] = useState<Card[]>([]);
  const [future, setFuture] = useState<Card[]>([]);
  const [showLibrary, setShowLibrary] = useState(false);
  const [showGame, setShowGame] = useState(false);
  const [unsaved, setUnsaved] = useState<string | null>(null);
  const [rendering, setRendering] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [sheet, setSheet] = useState<SheetName>("a4Middle");
  const [ticked, setTicked] = useState<Set<string>>(() => new Set());
  const [pdfJob, setPdfJob] = useState<{ cards: Card[]; sheet: SheetName } | null>(null);
  const paper = useRef<HTMLDivElement>(null);
  const pdfPaper = useRef<HTMLDivElement>(null);

  const card = cards.find((c) => c.id === currentId) ?? cards[0];

  useEffect(() => { save(cards.filter((c) => c.id !== unsaved)); }, [cards, unsaved]);

  const put = useCallback((next: Card) => {
    setCards((prev) => prev.map((c) => (c.id === next.id ? next : c)));
  }, []);

  const apply = useCallback((f: (card: Card) => Card) => {
    if (!card) return;
    setPast((p) => [...p.slice(-59), card]);
    setFuture([]);
    put({ ...f(card), updated: Date.now() });
  }, [card, put]);

  // Read the stacks here rather than inside an updater: an updater that also
  // calls setState is run twice under StrictMode and loses a step.
  const undo = useCallback(() => {
    const previous = past.at(-1);
    if (!previous || !card) return;
    setPast(past.slice(0, -1));
    setFuture([...future, card]);
    put(previous);
  }, [past, future, card, put]);

  const redo = useCallback(() => {
    const next = future.at(-1);
    if (!next || !card) return;
    setFuture(future.slice(0, -1));
    setPast([...past, card]);
    put(next);
  }, [past, future, card, put]);

  /** Del removes whatever is selected, and the selection steps up to what held
   *  it — deleting a row and being left pointing at nothing is how you delete
   *  the next one by accident. */
  const remove = useCallback(() => {
    if (!selected) return;
    if (selected.item) {
      setSelected({ section: selected.section, step: selected.step, part: selected.part });
      apply((c) => dropItem(c, selected));
    } else if (selected.step) {
      setSelected({ section: selected.section });
      apply((c) => dropStep(c, selected));
    } else {
      setSelected(null);
      apply((c) => dropSection(c, selected.section));
    }
  }, [selected, apply]);


  /** Add a row and select it, so the next click or drag has somewhere to go. */
  const addRow = useCallback((at: Where) => {
    const made = newStep();
    apply((c) => addStep(c, at, made));
    setSelected({ section: at.section, step: made.id });
  }, [apply]);

  /** The library makes a PDF of the cards ticked in it; the editor, of the card on screen. */
  const exportPdf = useCallback(() => {
    if (pdfJob || !card) return;
    const chosen = showLibrary ? cards.filter((c) => ticked.has(c.id)) : [card];
    if (chosen.length) setPdfJob({ cards: chosen, sheet });
  }, [pdfJob, card, cards, showLibrary, ticked, sheet]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const chord = event.ctrlKey || event.metaKey;
      // Ahead of the typing guard: focus is usually still on the sheet picker or
      // a tick box, and letting it through opens the browser's print dialog.
      if (chord && event.key.toLowerCase() === "p") {
        event.preventDefault();
        exportPdf();
        return;
      }
      if (typing(event.target)) return;
      if (chord && event.key.toLowerCase() === "z") {
        event.preventDefault();
        (event.shiftKey ? redo : undo)();
      } else if (event.key === "Delete" || event.key === "Backspace") {
        event.preventDefault();
        remove();
      } else if (event.key === "Escape") {
        setSelected(null);
      } else if (event.key === "Enter" && selected) {
        // After the row you are on, or at the end of the phase you are on.
        event.preventDefault();
        addRow({ section: selected.section, step: selected.step });
      } else if (selected && event.key.startsWith("Arrow")) {
        // The same nudge the inspector's arrows do, on the keys that look like
        // them: an item along its place, a row up and down its phase.
        const by = event.key === "ArrowLeft" || event.key === "ArrowUp" ? -1 : 1;
        const sideways = event.key === "ArrowLeft" || event.key === "ArrowRight";
        if (selected.item && sideways) { event.preventDefault(); apply((c) => moveItem(c, selected, by)); }
        else if (selected.step && !selected.item && !sideways) {
          event.preventDefault();
          apply((c) => moveStep(c, selected, by));
        }
      } else if (chord && (event.key === "0" || event.key === "+" || event.key === "-")) {
        event.preventDefault();
        setZoom((z) => (event.key === "0" ? 1 : step(z, event.key === "+" ? 1 : -1)));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [undo, redo, remove, selected, apply, addRow, exportPdf]);

  // Empty places are drawn only while something is being dragged. Listened for
  // in the capture phase, because every drop target stops the drop there. A
  // drop ends it a turn later: ended at once, the empty place being dropped on
  // is gone before its own handler runs. `dragend` still ends it when the drag
  // was over nothing, and is missed when the dragged item was moved away.
  useEffect(() => {
    const on = () => setDragging(true);
    const off = () => setDragging(false);
    const later = () => setTimeout(off);
    window.addEventListener("dragstart", on, true);
    window.addEventListener("dragend", off, true);
    window.addEventListener("drop", later, true);
    return () => {
      window.removeEventListener("dragstart", on, true);
      window.removeEventListener("dragend", off, true);
      window.removeEventListener("drop", later, true);
    };
  }, []);

  // A drag that ends off the card never fires `dragleave` on what it was last
  // over, and the caret would stay behind.
  useEffect(() => {
    const sweep = () => document.querySelectorAll("[data-drop], .is-over")
      .forEach((node) => { node.removeAttribute("data-drop"); node.classList.remove("is-over"); });
    window.addEventListener("dragend", sweep);
    window.addEventListener("drop", sweep);
    return () => {
      window.removeEventListener("dragend", sweep);
      window.removeEventListener("drop", sweep);
    };
  }, []);

  // The copies only exist once this render has committed them, hence an effect.
  useEffect(() => {
    const nodes = pdfPaper.current?.children;
    if (!pdfJob || !nodes) return;
    const name = pdfJob.cards.length === 1 ? fileName(pdfJob.cards[0].name, "pdf") : "aoe2_build_cards.pdf";
    cardsToPdf(Array.from(nodes) as HTMLElement[], SHEETS[pdfJob.sheet])
      .then((pdf) => download(name, pdf))
      .finally(() => setPdfJob(null));
  }, [pdfJob]);

  const openLibrary = () => {
    setTicked(new Set([card.id]));
    setShowLibrary(true);
  };

  const open = (id: string) => { setCurrentId(id); setSelected(null); setPast([]); setFuture([]); };

  const addCard = (made: Card) => {
    setCards((prev) => [...prev, made]);
    open(made.id);
  };

  const target = appendTarget(card, selected);

  const pickIcon = (key: string) => {
    if (target) apply((c) => addItem(c, target, icon(key)));
  };

  const pickNumber = (value: string) => {
    if (target) apply((c) => addItem(c, target, count(value)));
  };


  const edit: Edit = {
    selected,
    dragging,
    select: setSelected,
    relocate: (from, to) => apply((c) => relocate(c, from, to)),
    relocateStep: (from, to) => apply((c) => relocateStep(c, from, to)),
    addIcon: (where, key) => apply((c) => addItem(c, where, icon(key))),
    addNumber: (where, value) => apply((c) => addItem(c, where, count(value))),
    addRow,
  };

  const exportPng = async () => {
    const node = paper.current?.firstElementChild;
    if (!node) return;
    setRendering(true);
    try {
      download(fileName(card.name, "png"), await cardToPng(node as HTMLElement));
    } finally {
      setRendering(false);
    }
  };

  const exportJson = (payload: unknown, name: string) =>
    download(name, new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" }));

  const importFiles = async (files: FileList) => {
    const found: Card[] = [];
    for (const file of Array.from(files)) {
      try {
        const parsed = JSON.parse(await file.text()) as unknown;
        const list = Array.isArray((parsed as { cards?: unknown[] }).cards)
          ? (parsed as { cards: unknown[] }).cards
          : [parsed];
        for (const candidate of read(list)) found.push(reborn(candidate, candidate.name));
      } catch {
        alert(`${file.name} is not a card file.`);
      }
    }
    if (!found.length) return;
    setCards((prev) => [...prev, ...found]);
    open(found[0].id);
  };

  // One unsaved card at a time: reading the next player replaces it.
  const importFromGame = (value: unknown) => {
    const [made] = read([value]).map((candidate) => reborn(candidate, candidate.name));
    if (!made) throw new Error("The replay reader sent something that is not a card.");
    setCards((prev) => [...prev.filter((c) => c.id !== unsaved), made]);
    setUnsaved(made.id);
    open(made.id);
    setShowGame(false);
  };

  if (!card) return null;

  return (
    <div className="app">
      <div className="topbar">
        <span className="brand">AoE2 Build Cards</span>
        <input type="text" value={card.name}
               onChange={(e) => apply((c) => ({ ...c, name: e.target.value }))} />
        <button onClick={openLibrary}>Library…</button>
        <button onClick={() => setShowGame(true)}>Analyze game…</button>
        {card.id === unsaved && (
          <>
            <span className="unsaved" title="Read from a game and not in the library yet. Reading another player replaces it.">
              not saved
            </span>
            <button className="primary" onClick={() => setUnsaved(null)}>Save</button>
          </>
        )}
        <button onClick={() => addCard(newCard(`Build ${cards.length + 1}`))}>New</button>
        <span className="spacer" />
        <span className="zoom">
          <button onClick={() => setZoom((z) => step(z, -1))} title="Zoom out (Ctrl -)">−</button>
          <button className="level" onClick={() => setZoom(1)} title="Reset (Ctrl 0)">
            {Math.round(zoom * 100)}%
          </button>
          <button onClick={() => setZoom((z) => step(z, +1))} title="Zoom in (Ctrl +)">+</button>
        </span>
        <button onClick={undo} disabled={!past.length}>Undo</button>
        <button onClick={redo} disabled={!future.length}>Redo</button>
        <span className="menu-anchor">
          <button className="primary" onClick={() => setExporting((open) => !open)}
                  disabled={rendering || pdfJob !== null}>
            {rendering || pdfJob ? "Rendering…" : "Export ▾"}
          </button>
          {exporting && (
            <>
              <span className="menu-backdrop" onClick={() => setExporting(false)} />
              <span className="menu" onClick={() => setExporting(false)}>
                <button onClick={exportPng}>Image <small>PNG</small></button>
                <button onClick={exportPdf}>Print <small>PDF · Ctrl P</small></button>
                <button onClick={() => exportJson(card, fileName(card.name, "json"))}>
                  Card file <small>JSON</small>
                </button>
              </span>
            </>
          )}
        </span>
      </div>

      <div className="body">
        <div className="pane palette">
          <Palette onPick={pickIcon} onNumber={pickNumber}
                   target={partName(target?.part)} />
        </div>
        <div className="pane canvas"
             onWheel={(event) => {
               if (!event.ctrlKey) return;
               setZoom((z) => step(z, event.deltaY < 0 ? +1 : -1));
             }}>
          {/* `zoom` rather than a transform: it reflows, so the pane's
              scrollbars still describe what is actually there. */}
          <div className="canvas-inner" style={{ zoom }}>
            <CardView card={card} edit={edit} />
          </div>
        </div>
        <div className="pane inspector">
          <Inspector card={card} selected={selected} apply={apply} select={setSelected}
                     addRow={addRow} />
        </div>
      </div>

      {showLibrary && (
        <Library cards={cards} currentId={card.id} onClose={() => setShowLibrary(false)}
                 onOpen={open}
                 onNew={() => { addCard(newCard(`Build ${cards.length + 1}`)); setShowLibrary(false); }}
                 onDuplicate={(id) => {
                   const source = cards.find((c) => c.id === id);
                   if (source) addCard(reborn(source, `${source.name} copy`));
                 }}
                 onRename={(id, name) => setCards((prev) => prev.map((c) => (c.id === id ? { ...c, name } : c)))}
                 unsaved={unsaved}
                 onDelete={(id) => {
                   if (id === unsaved) setUnsaved(null);
                   setCards((prev) => {
                     const left = prev.filter((c) => c.id !== id);
                     if (id === currentId && left[0]) open(left[0].id);
                     return left;
                   });
                 }}
                 onImport={importFiles}
                 onExportAll={() => exportJson({ cards }, "aoe2_build_cards.json")}
                 ticked={ticked} onTicked={setTicked}
                 sheet={sheet} onSheet={setSheet}
                 exportingPdf={pdfJob !== null} />
      )}

      <FromGame open={showGame} onImport={importFromGame} onClose={() => setShowGame(false)} />

      {/* The card as it will be exported: no editing affordances, no drop
          targets, no zoom, laid out off-screen rather than hidden so it has a
          real size. Capturing the edited card instead made the PNG reflow. */}
      <div className="export-copy" aria-hidden ref={paper}><CardView card={card} /></div>
      {pdfJob && (
        <div className="export-copy" aria-hidden ref={pdfPaper}>
          {pdfJob.cards.map((c) => <CardView key={c.id} card={c} />)}
        </div>
      )}
    </div>
  );
}

const step = (zoom: number, by: number) => {
  const at = ZOOMS.reduce((best, z, i) =>
    Math.abs(z - zoom) < Math.abs(ZOOMS[best] - zoom) ? i : best, 0);
  return ZOOMS[Math.min(ZOOMS.length - 1, Math.max(0, at + by))];
};
