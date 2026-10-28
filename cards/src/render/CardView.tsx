/**
 * The card itself — the only thing that ends up in the PNG.
 *
 * Editing affordances are all class names and handlers passed in from above,
 * so the same component renders the finished image: drop `edit` and what is
 * left is exactly what exports. Words and numbers are typed on the card
 * itself — there is no panel of fields — so each opens in place (`Typed`).
 */

import { useLayoutEffect, useRef, useState } from "react";
import type { JSX } from "react";
import type { Card, Item, Part, Section, Slot, Step, Where } from "../model/card";
import { addSection, findItem, mapSection, mapSlot, minorIcons, movesAnyone, newSlot, slotIsEmpty,
         toggleSlot, totals, updateItem } from "../model/card";
import { iconLabel, iconUrl } from "../icons";

export type Edit = {
  selected: Where | null;
  /** Something is being dragged, so the empty places are drawn to drop on. */
  dragging: boolean;
  select: (where: Where | null) => void;
  relocate: (from: Where, to: Where) => void;
  relocateStep: (from: Where, to: Where) => void;
  addIcon: (where: Where, key: string) => void;
  addNumber: (where: Where, value: string) => void;
  addRow: (where: Where) => void;
  change: (f: (card: Card) => Card) => void;
  /** What is open for typing (`typing`), and the key that opened it, if one did. */
  typing: string | null;
  seed: string | null;
  type: (key: string | null, seed?: string) => void;
};

type Field = "title" | "subtitle" | "label" | "words" | "value" | "total" | "caption" | "text";

/** The one name for a piece of text on the card, so a double-click and a key
 *  in `App` open the same one. */
export const typing = (field: Field, id = "") => `${field}:${id}`;

/** What F2, or a key typed with a number selected, opens: the selection's own
 *  words — and the card's title with nothing selected. */
export function typingFor(card: Card, at: Where | null): string | null {
  if (!at) return typing("title");
  if (at.item) {
    const item = findItem(card, at);
    if (!item) return null;
    return typing(item.kind === "count" ? "value" : item.kind === "text" ? "text" : "caption", item.id);
  }
  if (at.step) return at.part && at.part !== "extras" ? typing("words", `${at.step}/${at.part}`) : null;
  return typing("label", at.section);
}

/** Text open for typing. Enter or clicking away keeps it; Esc puts it back. */
function Typed({ edit, value, onCommit, placeholder }: {
  edit: Edit; value: string; onCommit: (value: string) => void; placeholder?: string;
}) {
  const [draft, setDraft] = useState(edit.seed ?? value);
  // Enter closes it, and closing it would blur it a second time.
  const done = useRef(false);
  const finish = (keep: boolean) => {
    if (done.current) return;
    done.current = true;
    if (keep && draft !== value) onCommit(draft);
    edit.type(null);
  };
  const stop = (event: React.SyntheticEvent) => event.stopPropagation();
  return (
    <input className="typing" autoFocus value={draft} placeholder={placeholder}
           size={Math.max(draft.length, placeholder?.length ?? 0, 2)}
           onFocus={(event) => { if (edit.seed === null) event.target.select(); }}
           onChange={(event) => setDraft(event.target.value)}
           onKeyDown={(event) => {
             if (event.key === "Enter") finish(true);
             else if (event.key === "Escape") finish(false);
           }}
           onBlur={() => finish(true)}
           onClick={stop} onDoubleClick={stop} onMouseDown={stop}
           onDragStart={(event) => event.preventDefault()} />
  );
}

/** Opens `key` for typing on a double-click, and keeps the double-click from
 *  opening whatever holds it as well. */
const opens = (edit: Edit | undefined, key: string) =>
  edit ? { onDoubleClick: (event: React.MouseEvent) => { event.stopPropagation(); edit.type(key); } } : {};

export const DRAG_ITEM = "application/x-aoe2-card-item";
export const DRAG_ROW = "application/x-aoe2-card-row";
export const DRAG_ICON = "application/x-aoe2-icon";
export const DRAG_NUMBER = "application/x-aoe2-number";
/** Both come off the shelf, so both are a copy rather than a move. */
const FROM_SHELF = [DRAG_ICON, DRAG_NUMBER];

const same = (a: Where | null, b: Where) =>
  !!a && a.section === b.section && a.step === b.step && a.item === b.item
  && (a.item !== undefined || a.part === b.part);

/** Which edge of an element the pointer is nearer. Halves rather than a narrow
 *  strip between items: the whole tile aims, so there is nothing to hit. */
const sideOf = (event: React.DragEvent, element: Element): "before" | "after" => {
  const box = element.getBoundingClientRect();
  return event.clientX < box.left + box.width / 2 ? "before" : "after";
};

/** One place to read a drop, because three things can be dragged onto the same
 *  target and only the type tells them apart.
 *
 *  Over an item the target is an *edge* — `data-drop` draws the caret there
 *  and the same reading decides where it lands, so what you saw is what you
 *  get. Over anything else it is the whole box, outlined. */
function dropHandlers(edit: Edit | undefined, where: Where, kinds: string[]) {
  if (!edit) return {};
  const mine = (event: React.DragEvent) => kinds.find((k) => event.dataTransfer.types.includes(k));
  const aim = (event: React.DragEvent): Where =>
    (where.item ? { ...where, side: sideOf(event, event.currentTarget) } : where);
  const clear = (element: HTMLElement) => {
    element.classList.remove("is-over");
    element.removeAttribute("data-drop");
  };
  return {
    onDragOver: (event: React.DragEvent) => {
      const kind = mine(event);
      if (!kind) return;
      event.preventDefault();
      event.stopPropagation();
      // Has to match the `effectAllowed` the drag started with, or the browser
      // refuses the drop and nothing says why.
      event.dataTransfer.dropEffect = FROM_SHELF.includes(kind) ? "copy" : "move";
      const node = event.currentTarget as HTMLElement;
      if (where.item) node.dataset.drop = sideOf(event, node);
      else node.classList.add("is-over");
    },
    onDragLeave: (event: React.DragEvent) => clear(event.currentTarget as HTMLElement),
    onDrop: (event: React.DragEvent) => {
      const kind = mine(event);
      if (!kind) return;
      event.preventDefault();
      event.stopPropagation();
      const landing = aim(event);
      clear(event.currentTarget as HTMLElement);
      const payload = event.dataTransfer.getData(kind);
      if (kind === DRAG_ICON) edit.addIcon(landing, payload);
      else if (kind === DRAG_NUMBER) edit.addNumber(landing, payload);
      else if (kind === DRAG_ROW) edit.relocateStep(JSON.parse(payload) as Where, landing);
      else edit.relocate(JSON.parse(payload) as Where, landing);
    },
  };
}

function itemHandlers(edit: Edit | undefined, where: Where, open: string) {
  if (!edit) return {};
  return {
    draggable: !edit.typing?.endsWith(`:${where.item}`),
    ...opens(edit, open),
    onClick: (event: React.MouseEvent) => { event.stopPropagation(); edit.select(where); },
    onDragStart: (event: React.DragEvent) => {
      event.stopPropagation();
      event.dataTransfer.setData(DRAG_ITEM, JSON.stringify(where));
      event.dataTransfer.effectAllowed = "move";
    },
    ...dropHandlers(edit, where, [DRAG_ITEM, ...FROM_SHELF]),
  };
}

function ItemView({ item, where, edit, total, minor }: {
  item: Item; where: Where; edit?: Edit; total?: string; minor?: boolean;
}) {
  const classes = ["item", `item--${item.kind}`];
  if (minor) classes.push("item--minor");
  if (same(edit?.selected ?? null, where)) classes.push("is-selected");
  const field = item.kind === "count" ? "value" : item.kind === "text" ? "text" : "caption";
  const common = { className: classes.join(" "), ...itemHandlers(edit, where, typing(field, item.id)) };
  const open = (key: Field) => (edit && edit.typing === typing(key, item.id) ? edit : null);
  const set = (patch: Partial<Item>) => edit?.change((c) => updateItem(c, where, patch));

  switch (item.kind) {
    case "icon": {
      const caption = open("caption");
      return (
        <span {...common} title={iconLabel(item.icon)}>
          {/* Out of flow on purpose: a caption must not make its row taller
              than the rows around it, or the icons stop lining up. */}
          {caption
            ? <span className="cap cap--typing">
                <Typed edit={caption} value={item.caption} placeholder="caption"
                       onCommit={(text) => set({ caption: text })} />
              </span>
            : item.caption && <span className="cap">{item.caption}</span>}
          <span className="tile">
            <img src={iconUrl(item.icon)} alt={iconLabel(item.icon)} draggable={false} />
          </span>
        </span>
      );
    }
    case "count": {
      // A word in a number's place — "All" — carries no figure: under a word
      // it reads as a count of the word.
      const word = /[a-z]/i.test(item.value);
      const [value, figure] = [open("value"), open("total")];
      return (
        <span {...common}>
          <span className={`countbox${word ? " countbox--word" : ""}`}>
            <b>{value ? <Typed edit={value} value={item.value} onCommit={(v) => set({ value: v.trim() })} /> : item.value}</b>
            {total !== undefined && !word && (
              <i {...opens(edit, typing("total", item.id))}
                 title={edit ? "Double-click to state the total outright; left empty it is counted up" : undefined}>
                {figure
                  ? <Typed edit={figure} value={item.total} placeholder={total}
                           onCommit={(v) => set({ total: v.trim() })} />
                  : total}
              </i>
            )}
          </span>
        </span>
      );
    }
    case "text": {
      const words = open("text");
      return (
        <span {...common}>
          <span className="phrase">
            {words ? <Typed edit={words} value={item.text} onCommit={(text) => set({ text })} /> : item.text}
          </span>
        </span>
      );
    }
  }
}

/** One of the places. */
function SlotView({ slot, part, hint, step, section, edit, sums }: {
  slot: Slot; part: Part; hint: string; step: Step; section: Section;
  edit?: Edit; sums: Record<string, string>;
}) {
  const where: Where = { section: section.id, step: step.id, part };
  const classes = ["slot", `slot--${part}`];
  const selected = same(edit?.selected ?? null, where);
  if (selected) classes.push("is-selected");
  // The place or anything in it: a place full of tiles has little of its own to click.
  const holding = edit?.selected?.step === step.id && edit.selected.part === part;
  const minor = minorIcons(slot);
  const key = typing("words", `${step.id}/${part}`);
  const words = edit && edit.typing === key && part !== "extras" ? edit : null;
  return (
    <span className={classes.join(" ")} data-hint={hint}
          onClick={edit && ((event) => { event.stopPropagation(); edit.select(where); })}
          {...dropHandlers(edit, where, [DRAG_ITEM, ...FROM_SHELF])}>
      {slot.items.map((item) => (
        <ItemView key={item.id} item={item} edit={edit} total={sums[item.id]} minor={minor.has(item.id)}
                  where={{ ...where, item: item.id }} />
      ))}
      {words
        ? <span className="phrase">
            <Typed edit={words} value={slot.label} placeholder="words"
                   onCommit={(label) => part !== "extras" && words.change((c) =>
                     mapSlot(toggleSlot(c, where, part, true), where, (s) => ({ ...s, label })))} />
          </span>
        : slot.label
          ? <span className="phrase" {...opens(edit, key)}>{slot.label}</span>
          : edit && holding && (
              <button className="add-words" onClick={(event) => { event.stopPropagation(); edit.type(key); }}>
                + words
              </button>
            )}
    </span>
  );
}

/**
 * Whether an empty place is drawn. Only while something is being dragged — it
 * is somewhere to drop — or while it or its row is the selection, so it can be
 * clicked to aim the shelf at it: with no panel to add a move or a source,
 * selecting the row is how they are reached. The new villagers' source is
 * offered only beside somewhere they went, since it says who joined them.
 */
function offered(edit: Edit | undefined, step: Step, section: Section, part: Part): boolean {
  if (!edit) return false;
  if (same(edit.selected, { section: section.id, step: step.id, part })) return true;
  if (edit.dragging || same(edit.selected, { section: section.id, step: step.id }))
    return part !== "toFrom" || !slotIsEmpty(step.to);
  return false;
}

function Chain({ places, step, section, edit, sums }: {
  places: [Part, Slot | null, string][]; step: Step; section: Section;
  edit?: Edit; sums: Record<string, string>;
}) {
  const shown = places.filter(([part, slot]) => !slotIsEmpty(slot) || offered(edit, step, section, part));
  return (
    <span className="chain">
      {shown.map(([part, slot, hint], index) => (
        <span className="link" key={part}>
          {index > 0 && <span className="arrow">←</span>}
          <SlotView slot={slot ?? newSlot()} part={part} hint={hint} step={step}
                    section={section} edit={edit} sums={sums} />
        </span>
      ))}
    </span>
  );
}

/** A row: the new villagers and any who joined them, the ones moved off other
 *  work to somewhere else, and what the row only mentions — three columns. */
function StepRow({ step, section, edit, sums }: {
  step: Step; section: Section; edit?: Edit; sums: Record<string, string>;
}) {
  const where: Where = { section: section.id, step: step.id };
  const selected = same(edit?.selected ?? null, where);
  const extrasAt: Where = { ...where, part: "extras" };
  const moves = movesAnyone(step);
  const mentions = step.extras.length > 0;
  const columns = [moves && "step--moves", mentions && "step--extras", selected && "is-selected"];

  return (
    <div className={["step", ...columns].filter(Boolean).join(" ")}
         onClick={edit && ((event) => { event.stopPropagation(); edit.select(where); })}
         {...dropHandlers(edit, where, [DRAG_ROW])}>
      {edit && (
        <span className="grip" title="Drag to move this row" draggable
              onDragStart={(event) => {
                event.stopPropagation();
                event.dataTransfer.setData(DRAG_ROW, JSON.stringify(where));
                event.dataTransfer.effectAllowed = "move";
              }}>⠿</span>
      )}
      <span className="step-body">
        <span className="column column--new">
          <Chain step={step} section={section} edit={edit} sums={sums}
                 places={[["to", step.to, "end"], ["toFrom", step.toFrom, "joined from"]]} />
        </span>
        <span className="column column--move">
          <Chain step={step} section={section} edit={edit} sums={sums}
                 places={[["moveTo", step.moveTo, "moved to"], ["from", step.from, "source"]]} />
        </span>
        {(mentions || offered(edit, step, section, "extras")) &&
          <span className={`extras${same(edit?.selected ?? null, extrasAt) ? " is-selected" : ""}`}
              data-hint="extras"
              onClick={edit && ((event) => { event.stopPropagation(); edit.select(extrasAt); })}
              {...dropHandlers(edit, extrasAt, [DRAG_ITEM, DRAG_ICON, DRAG_NUMBER])}>
          {step.extras.map((item) => (
            <ItemView key={item.id} item={item} edit={edit} total={sums[item.id]}
                      where={{ ...extrasAt, item: item.id }} />
          ))}
        </span>}
      </span>
    </div>
  );
}

/**
 * The moves line up down the card: the new villagers' column is as wide as
 * the widest on the card among rows with a move after it, so every move starts
 * at one x. Left out of that measure is a row with no move — one age-up label
 * would push every move right — and a row whose move would not fit beside it
 * even so, since the move goes to a line of its own. The extras need no
 * measure: they keep to the right edge.
 *
 * Measured rather than laid out as a grid, because the rows sit in separate
 * phase boxes; set as a variable on the card itself, so the off-screen copy
 * the PNG is taken from measures and carries its own.
 */
function useColumns(card: Card) {
  const node = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const root = node.current;
    if (!root) return;
    const bodies = [...root.querySelectorAll<HTMLElement>(".step-body")];
    const gap = bodies.length ? Number.parseFloat(getComputedStyle(bodies[0]).columnGap) || 0 : 0;
    const widths = bodies.flatMap((body) => {
      const width = (selector: string) => body.querySelector<HTMLElement>(selector)?.offsetWidth ?? 0;
      const [fresh, move] = [width(".column--new > .chain"), width(".column--move > .chain")];
      const moves = body.parentElement!.classList.contains("step--moves");
      return moves && fresh + gap + move <= body.clientWidth ? [fresh] : [];
    });
    root.style.setProperty("--new-column", `${widths.length ? Math.max(...widths) : 0}px`);
  }, [card]);
  return node;
}

export function CardView({ card, edit }: { card: Card; edit?: Edit }): JSX.Element {
  const sums = card.totals ? totals(card) : {};
  const node = useColumns(card);
  return (
    <div ref={node} className={`card${edit ? " card--edit" : ""}`}
         onClick={edit && (() => edit.select(null))}>
      <header className="card-head">
        <h1 {...opens(edit, typing("title"))}>
          {edit && edit.typing === typing("title")
            ? <Typed edit={edit} value={card.title || card.name}
                     onCommit={(title) => edit.change((c) => ({ ...c, title }))} />
            : card.title || card.name}
        </h1>
        {edit && edit.typing === typing("subtitle")
          ? <p><Typed edit={edit} value={card.subtitle} placeholder="subtitle"
                      onCommit={(subtitle) => edit.change((c) => ({ ...c, subtitle }))} /></p>
          : card.subtitle
            ? <p {...opens(edit, typing("subtitle"))}>{card.subtitle}</p>
            : edit && <p className="no-subtitle" {...opens(edit, typing("subtitle"))}>double-click to add a subtitle</p>}
      </header>
      {card.sections.map((section) => {
        const where: Where = { section: section.id };
        const selected = same(edit?.selected ?? null, where);
        return (
          <section key={section.id}
                   className={`phase phase--${section.tone}${selected ? " is-selected" : ""}`}
                   onClick={edit && ((event) => { event.stopPropagation(); edit.select(where); })}
                   {...dropHandlers(edit, { section: section.id }, [DRAG_ROW])}>
            <div className="phase-label" {...opens(edit, typing("label", section.id))}>
              {edit && edit.typing === typing("label", section.id)
                ? <Typed edit={edit} value={section.label}
                         onCommit={(label) => edit.change((c) => mapSection(c, section.id, (s) => ({ ...s, label })))} />
                : section.label}
            </div>
            <div className="phase-steps">
              {section.steps.map((step) => (
                <StepRow key={step.id} step={step} section={section} edit={edit} sums={sums} />
              ))}
              {edit && (
                <button className="add-row" title="Add a row (Enter)"
                        onClick={(event) => {
                          event.stopPropagation();
                          edit.addRow({ section: section.id });
                        }}>+ row</button>
              )}
            </div>
          </section>
        );
      })}
      {edit && (
        <button className="add-row add-phase" title="Add a phase at the end of the card"
                onClick={(event) => { event.stopPropagation(); edit.change((c) => addSection(c, null)); }}>
          + phase
        </button>
      )}
    </div>
  );
}
