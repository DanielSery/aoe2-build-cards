/**
 * The card itself — the only thing that ends up in the PNG.
 *
 * Editing affordances are all class names and handlers passed in from above,
 * so the same component renders the finished image: drop `edit` and what is
 * left is exactly what exports.
 */

import type { JSX } from "react";
import type { Card, Item, Part, Section, Slot, Step, Where } from "../model/card";
import { newSlot, numbering, slotIsEmpty, totals } from "../model/card";
import { iconLabel, iconUrl } from "../icons";

export type Edit = {
  selected: Where | null;
  select: (where: Where | null) => void;
  relocate: (from: Where, to: Where) => void;
  relocateStep: (from: Where, to: Where) => void;
  addIcon: (where: Where, key: string) => void;
  addNumber: (where: Where, value: string) => void;
  addRow: (where: Where) => void;
};

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

function itemHandlers(edit: Edit | undefined, where: Where) {
  if (!edit) return {};
  return {
    draggable: true,
    onClick: (event: React.MouseEvent) => { event.stopPropagation(); edit.select(where); },
    onDragStart: (event: React.DragEvent) => {
      event.stopPropagation();
      event.dataTransfer.setData(DRAG_ITEM, JSON.stringify(where));
      event.dataTransfer.effectAllowed = "move";
    },
    ...dropHandlers(edit, where, [DRAG_ITEM, ...FROM_SHELF]),
  };
}

function ItemView({ item, where, edit, total }: {
  item: Item; where: Where; edit?: Edit; total?: string;
}) {
  const classes = ["item", `item--${item.kind}`];
  if (same(edit?.selected ?? null, where)) classes.push("is-selected");
  const common = { className: classes.join(" "), ...itemHandlers(edit, where) };

  switch (item.kind) {
    case "icon":
      return (
        <span {...common} title={iconLabel(item.icon)}>
          {/* Out of flow on purpose: a caption must not make its row taller
              than the rows around it, or the icons stop lining up. */}
          {item.caption && <span className="cap">{item.caption}</span>}
          <span className="tile">
            <img src={iconUrl(item.icon)} alt={iconLabel(item.icon)} draggable={false} />
          </span>
        </span>
      );
    case "count": {
      // A word in a number's place — "All" — carries no figure: under a word
      // it reads as a count of the word.
      const word = /[a-z]/i.test(item.value);
      return (
        <span {...common}>
          <span className={`countbox${word ? " countbox--word" : ""}`}>
            <b>{item.value}</b>
            {total !== undefined && !word && <i>{total}</i>}
          </span>
        </span>
      );
    }
    case "text":
      return <span {...common}><span className="phrase">{item.text}</span></span>;
    case "box":
      return (
        <span {...common}>
          <span className="boxed">
            {item.items.map((child) => (
              <ItemView key={child.id} item={child} edit={edit}
                        where={{ ...where, item: child.id, inBox: item.id }} />
            ))}
            {edit && item.items.length === 0 && <span className="boxed-empty">empty box</span>}
          </span>
        </span>
      );
  }
}

/** One of the three places. */
function SlotView({ slot, part, hint, step, section, edit, sums }: {
  slot: Slot; part: Part; hint: string; step: Step; section: Section;
  edit?: Edit; sums: Record<string, string>;
}) {
  const where: Where = { section: section.id, step: step.id, part };
  const classes = ["slot", `slot--${part}`];
  if (same(edit?.selected ?? null, where)) classes.push("is-selected");
  return (
    <span className={classes.join(" ")} data-hint={hint}
          onClick={edit && ((event) => { event.stopPropagation(); edit.select(where); })}
          {...dropHandlers(edit, where, [DRAG_ITEM, ...FROM_SHELF])}>
      {slot.items.map((item) => (
        <ItemView key={item.id} item={item} edit={edit} total={sums[item.id]}
                  where={{ ...where, item: item.id }} />
      ))}
      {slot.label && <span className="phrase">{slot.label}</span>}
    </span>
  );
}

function StepRow({ step, section, number, edit, sums }: {
  step: Step; section: Section; number?: number;
  edit?: Edit; sums: Record<string, string>;
}) {
  const where: Where = { section: section.id, step: step.id };
  const selected = same(edit?.selected ?? null, where);
  const extrasAt: Where = { ...where, part: "extras" };
  const chain: [Part, Slot | null, string][] = [
    ["to", step.to, "end"],
    ["via", step.via, "before"],
    ["from", step.from, "source"],
  ];
  // While editing, all three places are on the row whether or not they hold
  // anything: the empty ones are where you click to fill them, and they are
  // the only explanation of the format the card ever gives.
  const shown = chain.filter(([, slot]) => edit || !slotIsEmpty(slot));

  return (
    <div className={`step${selected ? " is-selected" : ""}`}
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
      {section.numbered && <span className="step-no">{number}</span>}
      <span className="chain">
        {shown.map(([part, slot, hint], index) => (
          <span className="link" key={part}>
            {index > 0 && <span className="arrow">←</span>}
            <SlotView slot={slot ?? newSlot()} part={part} hint={hint} step={step}
                      section={section} edit={edit} sums={sums} />
          </span>
        ))}
      </span>
      <span className={`extras${same(edit?.selected ?? null, extrasAt) ? " is-selected" : ""}`}
            data-hint="extras"
            onClick={edit && ((event) => { event.stopPropagation(); edit.select(extrasAt); })}
            {...dropHandlers(edit, extrasAt, [DRAG_ITEM, DRAG_ICON])}>
        {step.extras.map((item) => (
          <ItemView key={item.id} item={item} edit={edit} total={sums[item.id]}
                    where={{ ...extrasAt, item: item.id }} />
        ))}
      </span>
    </div>
  );
}

export function CardView({ card, edit }: { card: Card; edit?: Edit }): JSX.Element {
  const numbers = numbering(card);
  const sums = card.totals ? totals(card) : {};
  return (
    <div className={`card${edit ? " card--edit" : ""}`}
         onClick={edit && (() => edit.select(null))}>
      <header className="card-head">
        <h1>{card.title || card.name}</h1>
        {card.subtitle && <p>{card.subtitle}</p>}
      </header>
      {card.sections.map((section) => {
        const where: Where = { section: section.id };
        const selected = same(edit?.selected ?? null, where);
        return (
          <section key={section.id}
                   className={`phase phase--${section.tone}${selected ? " is-selected" : ""}`}
                   onClick={edit && ((event) => { event.stopPropagation(); edit.select(where); })}
                   {...dropHandlers(edit, { section: section.id }, [DRAG_ROW])}>
            <div className="phase-label">{section.label}</div>
            <div className="phase-steps">
              {section.steps.map((step) => (
                <StepRow key={step.id} step={step} section={section} edit={edit} sums={sums}
                         number={numbers[step.id]} />
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
    </div>
  );
}
