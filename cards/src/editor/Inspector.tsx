/**
 * Everything you can change about whatever is selected — and nothing else.
 *
 * One entity at a time: the card, a phase, a row, or one thing on a row. The
 * crumbs at the top are how you get back up, because selecting a child is a
 * one-way click on the card.
 */

import { SLOTS, TONES, addItem, addSection, count, dropItem,
         dropSection, dropStep, duplicateStep, findItem, findSection, findStep,
         mapSection, mapSlot, moveItem, moveSection, moveStep, text, toggleSlot,
         updateItem } from "../model/card";
import type { Card, Item, RowNumbers, Tone, Where } from "../model/card";
import { ICONS, iconLabel, iconUrl } from "../icons";

type Props = {
  card: Card;
  selected: Where | null;
  apply: (f: (card: Card) => Card) => void;
  select: (where: Where | null) => void;
  addRow: (at: Where) => void;
};

const KINDS: Record<Item["kind"], string> = {
  icon: "Icon", count: "Number", text: "Text",
};

export function Inspector({ card, selected, apply, select, addRow }: Props) {
  const section = selected ? findSection(card, selected) : null;
  const step = selected?.step ? findStep(card, selected) : null;
  const item = selected?.item ? findItem(card, selected) : null;
  const at: Where | null = section && step ? { section: section.id, step: step.id } : null;

  const crumbs: [string, Where | null][] = [["Card", null]];
  if (section) crumbs.push([section.label || "Phase", { section: section.id }]);
  if (at && step) crumbs.push(["Row", at]);
  if (item) crumbs.push([KINDS[item.kind], selected]);

  return (
    <>
      <nav className="crumbs">
        {crumbs.map(([label, where], index) => (
          <span key={index}>
            {index > 0 && <span className="sep">›</span>}
            <button className={`crumb${index === crumbs.length - 1 ? " on" : ""}`}
                    onClick={() => select(where)}>{label}</button>
          </span>
        ))}
      </nav>

      {item && selected
        ? <ItemPanel card={card} selected={selected} item={item} apply={apply} select={select} />
        : at && step
          ? <RowPanel card={card} at={at} apply={apply} select={select} addRow={addRow} />
          : section
            ? <PhasePanel card={card} sectionId={section.id} apply={apply} select={select}
                          addRow={addRow} />
            : <CardPanel card={card} apply={apply} />}
    </>
  );
}

function CardPanel({ card, apply }: Pick<Props, "card" | "apply">) {
  return (
    <>
      <label className="field">Title</label>
      <input className="wide" value={card.title}
             onChange={(e) => apply((c) => ({ ...c, title: e.target.value }))} />
      <label className="field">Subtitle</label>
      <input className="wide" value={card.subtitle}
             onChange={(e) => apply((c) => ({ ...c, subtitle: e.target.value }))} />
      <label className="row" style={{ marginTop: 12 }}>
        <input type="checkbox" checked={card.totals} style={{ width: "auto" }}
               onChange={(e) => apply((c) => ({ ...c, totals: e.target.checked }))} />
        <span>Show the running total under each number</span>
      </label>
      <label className="field">Row numbers count</label>
      <select className="wide" value={card.rowNumbers}
              onChange={(e) => apply((c) => ({ ...c, rowNumbers: e.target.value as RowNumbers }))}>
        <option value="steps">the rows</option>
        <option value="villagers">the villagers at work after the row</option>
      </select>
      <div className="row" style={{ marginTop: 12 }}>
        <button onClick={() => apply((c) => addSection(c, null))}>Add phase</button>
      </div>
    </>
  );
}

function PhasePanel({ card, sectionId, apply, select, addRow }: Pick<Props, "card" | "apply" | "select">
                                                        & { sectionId: string; addRow: (at: Where) => void }) {
  const section = card.sections.find((s) => s.id === sectionId)!;
  const edit = (f: Parameters<typeof mapSection>[2]) => apply((c) => mapSection(c, sectionId, f));
  return (
    <>
      <label className="field">Label</label>
      <input className="wide" value={section.label}
             onChange={(e) => edit((s) => ({ ...s, label: e.target.value }))} />
      <label className="field">Colour</label>
      <select className="wide" value={section.tone}
              onChange={(e) => edit((s) => ({ ...s, tone: e.target.value as Tone }))}>
        {TONES.map(([tone, label]) => <option key={tone} value={tone}>{label}</option>)}
      </select>
      <label className="row" style={{ marginTop: 10 }}>
        <input type="checkbox" checked={section.numbered} style={{ width: "auto" }}
               onChange={(e) => edit((s) => ({ ...s, numbered: e.target.checked }))} />
        <span>Number the rows</span>
      </label>
      <div className="row" style={{ marginTop: 12 }}>
        <button className="primary" onClick={() => addRow({ section: sectionId })}>Add row</button>
        <button onClick={() => apply((c) => moveSection(c, sectionId, -1))} title="Move up">↑</button>
        <button onClick={() => apply((c) => moveSection(c, sectionId, +1))} title="Move down">↓</button>
        <button className="danger" onClick={() => { select(null); apply((c) => dropSection(c, sectionId)); }}>
          Delete phase
        </button>
      </div>
    </>
  );
}

function RowPanel({ card, at, apply, select, addRow }: Pick<Props, "card" | "apply" | "select">
                                               & { at: Where; addRow: (at: Where) => void }) {
  const step = findStep(card, at)!;
  const chip = (item: Item, where: Where) => (
    <button key={item.id} className="icon-btn small" title={KINDS[item.kind]}
            onClick={(e) => { e.stopPropagation(); select(where); }}>
      {item.kind === "icon"
        ? <img src={iconUrl(item.icon)} alt={iconLabel(item.icon)} />
        : <span className="glyph">{item.kind === "count" ? item.value
            : "T"}</span>}
    </button>
  );

  return (
    <>
      {SLOTS.map(([part, title, hint]) => {
        const slot = step[part];
        const where: Where = { ...at, part };
        const heading = part === "to" ? "New villagers" : part === "moveTo" ? "Moved off other work" : null;
        return (
          <div key={part}>
          {heading && <h2 className="section">{heading}</h2>}
          <div className="slot-block" onClick={() => select(where)}>
            <div className="row">
              <strong className="grow">{title}</strong>
              {part === "to"
                ? <span className="hint">{hint}</span>
                : <button className="tiny" onClick={(e) => {
                    e.stopPropagation();
                    apply((c) => toggleSlot(c, at, part, !slot));
                    select(where);
                  }}>{slot ? "Remove" : "Add"}</button>}
            </div>
            {slot && (
              <>
                <input className="wide" style={{ marginTop: 6 }} placeholder="words (optional)"
                       value={slot.label}
                       onChange={(e) => apply((c) => mapSlot(c, where, (s) => ({ ...s, label: e.target.value })))} />
                <div className="row tight" style={{ marginTop: 6 }}>
                  {slot.items.map((entry) => chip(entry, { ...where, item: entry.id }))}
                  {part !== "from" && <button className="tiny" onClick={(e) => {
                    e.stopPropagation();
                    apply((c) => addItem(c, where, count("1")));
                  }}>+ number</button>}
                </div>
                <p className="hint" style={{ marginTop: 6 }}>
                  Drag an icon here from the shelf, or select this place and click one.
                </p>
              </>
            )}
          </div>
          </div>
        );
      })}

      <h2 className="section">Mentioned</h2>
      <div className="slot-block" onClick={() => select({ ...at, part: "extras" })}>
        <div className="row">
          <strong className="grow">Extras</strong>
          <span className="hint">deer pushed in, a tech, a note</span>
        </div>
        <div className="row tight" style={{ marginTop: 6 }}>
          {step.extras.map((entry) => chip(entry, { ...at, part: "extras", item: entry.id }))}
        </div>
        <div className="row tight" style={{ marginTop: 6 }}>
          <button className="tiny" onClick={(e) => {
            e.stopPropagation();
            apply((c) => addItem(c, { ...at, part: "extras" }, count("2")));
          }}>+ number</button>
          <button className="tiny" onClick={(e) => {
            e.stopPropagation();
            apply((c) => addItem(c, { ...at, part: "extras" }, text("note")));
          }}>+ text</button>
        </div>
      </div>

      <div className="row" style={{ marginTop: 12 }}>
        <button className="primary" onClick={() => addRow(at)}>Add row</button>
        <button onClick={() => apply((c) => moveStep(c, at, -1))} title="Move row up">↑</button>
        <button onClick={() => apply((c) => moveStep(c, at, +1))} title="Move row down">↓</button>
        <button onClick={() => apply((c) => duplicateStep(c, at))}>Duplicate</button>
        <button className="danger" onClick={() => { select({ section: at.section }); apply((c) => dropStep(c, at)); }}>
          Delete row
        </button>
      </div>
    </>
  );
}

function ItemPanel({ selected, item, apply, select }: Pick<Props, "card" | "apply" | "select">
                                                      & { selected: Where; item: Item }) {
  const set = (patch: Partial<Item>) => apply((c) => updateItem(c, selected, patch));
  return (
    <>
      {item.kind === "icon" && (
        <>
          <div className="row">
            <img src={iconUrl(item.icon)} alt="" width={44} height={44}
                 style={{ background: "#000", borderRadius: 4, objectFit: "contain" }} />
            <span className="grow">{iconLabel(item.icon)}</span>
          </div>
          <label className="field">Which icon</label>
          <select className="wide" value={item.icon}
                  onChange={(e) => set({ icon: e.target.value })}>
            {ICONS.map((entry) => <option key={entry.key} value={entry.key}>{entry.label}</option>)}
          </select>
          <label className="field">Caption above the tile</label>
          <input className="wide" value={item.caption} placeholder="e.g. 50"
                 onChange={(e) => set({ caption: e.target.value })} />
          <p className="hint" style={{ marginTop: 6 }}>
            The caption sits over the tile without taking room, so a row that has
            one still lines up with the rows that do not.
          </p>
        </>
      )}
      {item.kind === "count" && (
        <>
          <label className="field">Number</label>
          <input className="wide" value={item.value} onChange={(e) => set({ value: e.target.value })} />
          <label className="field">Total on this work</label>
          <input className="wide" value={item.total} placeholder="counted up"
                 onChange={(e) => set({ total: e.target.value })} />
          <p className="hint" style={{ marginTop: 6 }}>
            The smaller figure under the number is the villagers on whatever
            this place names — sheep, hunt, berries, farms, the wood line,
            stragglers, gold, stone. Where moved villagers go, the number is
            how many moved: they come off the source too, and <em>All</em> is
            everyone who was on it. Left blank the figure is counted up from
            the numbers above; typed in, it says so outright and everything
            below counts on from there.
          </p>
        </>
      )}
      {item.kind === "text" && (
        <>
          <label className="field">Words</label>
          <input className="wide" value={item.text} onChange={(e) => set({ text: e.target.value })} />
        </>
      )}
      <div className="row" style={{ marginTop: 12 }}>
        <button onClick={() => apply((c) => moveItem(c, selected, -1))} title="Move left">←</button>
        <button onClick={() => apply((c) => moveItem(c, selected, +1))} title="Move right">→</button>
        <button className="danger" onClick={() => {
          select({ section: selected.section, step: selected.step, part: selected.part });
          apply((c) => dropItem(c, selected));
        }}>Delete</button>
      </div>
      <p className="hint" style={{ marginTop: 10 }}>Del removes whatever is selected.</p>
    </>
  );
}
