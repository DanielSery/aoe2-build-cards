import { useRef } from "react";
import type { Card } from "../model/card";
import { SHEETS } from "../render/pdf";
import type { SheetName } from "../render/pdf";

type Props = {
  cards: Card[];
  currentId: string;
  unsaved: string | null;
  onOpen: (id: string) => void;
  onNew: () => void;
  onDuplicate: (id: string) => void;
  onRename: (id: string, name: string) => void;
  onDelete: (id: string) => void;
  onImport: (files: FileList) => void;
  onExportAll: () => void;
  ticked: Set<string>;
  onTicked: (ticked: Set<string>) => void;
  sheet: SheetName;
  onSheet: (sheet: SheetName) => void;
  exportingPdf: boolean;
  onClose: () => void;
};

/** Saved cards live in this browser only, which is why import and export sit
 *  in the same panel as the list rather than off in a menu. */
export function Library(props: Props) {
  const file = useRef<HTMLInputElement>(null);
  const forPdf = props.cards.filter((card) => props.ticked.has(card.id)).length;
  const tick = (id: string) => {
    const next = new Set(props.ticked);
    if (!next.delete(id)) next.add(id);
    props.onTicked(next);
  };
  return (
    <div className="modal-backdrop" onClick={props.onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="row">
          <strong className="grow">Library</strong>
          <button onClick={props.onClose}>Close</button>
        </div>
        <p className="hint" style={{ margin: "8px 0 12px" }}>
          {props.cards.length} card{props.cards.length === 1 ? "" : "s"}, saved in this
          browser. Export to keep them anywhere else, or tick some to make a PDF.
        </p>
        <div className="cards-list">
          {props.cards.map((card) => (
            <div key={card.id} className={`entry${card.id === props.currentId ? " on" : ""}`}>
              <input type="checkbox" checked={props.ticked.has(card.id)} style={{ width: "auto" }}
                     title="Include in the PDF" onChange={() => tick(card.id)} />
              <span className="name" onClick={() => { props.onOpen(card.id); props.onClose(); }}>
                {card.name}
                {card.id === props.unsaved && <span className="hint"> · not saved</span>}
              </span>
              <button className="tiny" onClick={() => {
                const name = prompt("Card name", card.name);
                if (name) props.onRename(card.id, name);
              }}>Rename</button>
              <button className="tiny" onClick={() => props.onDuplicate(card.id)}>Copy</button>
              <button className="tiny danger" disabled={props.cards.length === 1}
                      onClick={() => confirm(`Delete “${card.name}”?`) && props.onDelete(card.id)}>
                Delete
              </button>
            </div>
          ))}
        </div>
        <div className="row" style={{ marginTop: 10 }}>
          <label className="row tight grow hint">
            <input type="checkbox" style={{ width: "auto" }}
                   checked={forPdf === props.cards.length}
                   onChange={(e) => props.onTicked(new Set(e.target.checked ? props.cards.map((c) => c.id) : []))} />
            <span>All</span>
          </label>
          <select value={props.sheet} title="Every card in the PDF is drawn the same width"
                  onChange={(e) => props.onSheet(e.target.value as SheetName)}>
            {Object.entries(SHEETS).map(([name, sheet]) => (
              <option key={name} value={name}>{sheet.label}</option>
            ))}
          </select>
          <span className="hint">
            {props.exportingPdf ? "Rendering…" : forPdf ? `Ctrl P: PDF of ${forPdf}` : "Tick a card for a PDF"}
          </span>
        </div>
        <div className="row" style={{ marginTop: 14 }}>
          <button className="primary" onClick={props.onNew}>New card</button>
          <button onClick={() => file.current?.click()}>Import JSON…</button>
          <button onClick={props.onExportAll}>Export all</button>
          <input ref={file} type="file" accept="application/json" multiple hidden
                 onChange={(e) => { if (e.target.files) props.onImport(e.target.files); e.target.value = ""; }} />
        </div>
      </div>
    </div>
  );
}
