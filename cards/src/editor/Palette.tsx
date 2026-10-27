import { useMemo, useState } from "react";
import { ICON_CATEGORIES, iconTitle, iconUrl, searchIcons } from "../icons";
import { ALL } from "../model/card";
import { DRAG_ICON, DRAG_NUMBER } from "../render/CardView";

/** The numbers worth having to hand. Past twenty a build order is counting
 *  population rather than villagers on a job, and the field takes anything. */
const NUMBERS = [...Array.from({ length: 20 }, (_, i) => String(i + 1)), ALL];

/** The shelf: numbers and icons. Drag one onto the card, or click it and it
 *  lands wherever the selection is aiming — which is why the banner says
 *  where that is. */
export function Palette({ onPick, onNumber, target }: {
  onPick: (key: string) => void;
  onNumber: (value: string) => void;
  target: string;
}) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<string | null>(null);
  const found = useMemo(() => searchIcons(query, category), [query, category]);

  return (
    <>
      <p className="palette-target">Click adds to <strong>{target}</strong> — or drag onto the card</p>

      <h2 className="section">Numbers</h2>
      <div className="number-strip">
        {NUMBERS.map((value) => (
          <button key={value} className="number-btn" draggable
                  onDragStart={(event) => {
                    event.dataTransfer.setData(DRAG_NUMBER, value);
                    event.dataTransfer.effectAllowed = "copy";
                  }}
                  onClick={() => onNumber(value)}>{value}</button>
        ))}
      </div>

      <h2 className="section">Icons</h2>
      <input className="wide" type="search" placeholder="Search icons…"
             value={query} onChange={(e) => setQuery(e.target.value)} />
      <div className="chips" style={{ margin: "8px 0" }}>
        <button className={`chip${category === null ? " on" : ""}`}
                onClick={() => setCategory(null)}>All</button>
        {ICON_CATEGORIES.map(([key, label]) => (
          <button key={key} className={`chip${category === key ? " on" : ""}`}
                  onClick={() => setCategory(key)}>{label}</button>
        ))}
      </div>
      <div className="icon-grid">
        {found.map((entry) => (
          <button key={entry.key} className="icon-btn" title={iconTitle(entry.key)}
                  draggable
                  onDragStart={(event) => {
                    event.dataTransfer.setData(DRAG_ICON, entry.key);
                    event.dataTransfer.effectAllowed = "copy";
                  }}
                  onClick={() => onPick(entry.key)}>
            <img src={iconUrl(entry.key)} alt={entry.label} draggable={false} />
          </button>
        ))}
      </div>
      {found.length === 0 && <p className="hint">Nothing matches “{query}”.</p>}
    </>
  );
}
