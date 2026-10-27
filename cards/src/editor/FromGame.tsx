import { useEffect, useRef, useState } from "react";
import type { Game, GamePlayer } from "../model/games";
import { REPLAY_FILES, cardFromGame, lookUpGame, openReplay } from "../model/games";
import { FindGame } from "./FindGame";

type Props = {
  open: boolean;
  /** A replay dropped on the page, to be read as soon as it arrives. Wrapped,
   *  so the same file dropped twice is read twice. */
  dropped: { file: File } | null;
  /** Throws when the card cannot be adopted, so the dialog can say so. */
  onImport: (card: unknown) => void;
  onClose: () => void;
};

const teamsOf = (players: GamePlayer[]): [number, GamePlayer[]][] => {
  const teams = new Map<number, GamePlayer[]>();
  for (const player of players) teams.set(player.team, [...(teams.get(player.team) ?? []), player]);
  return [...teams.entries()];
};

const ages = (player: GamePlayer) =>
  [player.feudal && `Feudal ${player.feudal}`, player.castle && `Castle ${player.castle}`]
    .filter(Boolean).join(" · ");

/** Stays mounted while closed — `open` only hides it — so a search, its
 *  filters and the game last read are all still there for the next player. */
export function FromGame({ open, dropped, onImport, onClose }: Props) {
  const [mode, setMode] = useState<"find" | "link" | "file">("find");
  const chooser = useRef<HTMLInputElement>(null);
  const [link, setLink] = useState("");
  const [game, setGame] = useState<Game | null>(null);
  const [onGame, setOnGame] = useState(false);
  const [mark, setMark] = useState<number | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = async (doing: string, work: () => Promise<void>) => {
    setBusy(doing);
    setError(null);
    try {
      await work();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setBusy(null);
    }
  };

  const read = (what: string, highlight: number | null) =>
    run("Downloading and reading the replay…", async () => {
      setGame(await lookUpGame(what));
      setMark(highlight);
      setOnGame(true);
    });

  const openFile = (file: File) =>
    run(`Reading ${file.name}…`, async () => {
      setGame(await openReplay(file));
      setMark(null);
      setOnGame(true);
    });

  useEffect(() => {
    if (!dropped || busy) return;
    setMode("file");
    openFile(dropped.file);
  }, [dropped]);

  const take = (player: GamePlayer) => game &&
    run(`Writing ${player.name}'s card…`, async () => onImport(await cardFromGame(game.matchId, player.number)));

  return (
    <div className="modal-backdrop" style={open ? undefined : { display: "none" }} onClick={onClose}>
      <div className="modal wide" onClick={(e) => e.stopPropagation()}
           onDragOver={(e) => { if (e.dataTransfer.types.includes("Files")) e.preventDefault(); }}
           onDrop={(e) => {
             const file = e.dataTransfer.files[0];
             if (!file) return;
             e.preventDefault();
             if (!busy) openFile(file);
           }}>
        <div className="row">
          <strong className="grow">Analyze a recorded game</strong>
          <button onClick={onClose}>Close</button>
        </div>

        {game && onGame && (
          <div className="game">
            <div className="row">
              <button className="tiny" onClick={() => setOnGame(false)}>← Back</button>
              <span className="hint grow">
                {game.setting}
                {game.started && ` · ${new Date(game.started).toLocaleString()}`}
                {` · ${game.duration} game time`}
              </span>
            </div>
            <p className="hint">Pick whose build to turn into a card. It opens unsaved until you save it.</p>
            {teamsOf(game.players).map(([team, players]) => (
              <div key={team} className="game-team">
                <div className="hint">Team {team}{players.some((p) => p.won) ? " · won" : ""}</div>
                {players.map((player) => (
                  <button key={player.number} disabled={busy !== null}
                          className={`game-player${player.profileId === mark ? " on" : ""}`}
                          title={`Import ${player.name}'s opening as a card`} onClick={() => take(player)}>
                    <span className="swatch" style={{ background: player.color }} />
                    <span className="grow who">
                      <span className="name">{player.name}</span>
                      {player.strategy && <span className="strategy">{player.strategy}</span>}
                    </span>
                    <span className="hint">{player.civ}</span>
                    <span className="hint ages">{ages(player)}</span>
                  </button>
                ))}
              </div>
            ))}
          </div>
        )}
        {/* Hidden rather than unmounted, here and between the two tabs, so Back
            finds the search and its filters where they were. */}
        <div style={game && onGame ? { display: "none" } : undefined}>
          <div className="chips" style={{ margin: "10px 0" }}>
            <span className={`chip${mode === "find" ? " on" : ""}`} onClick={() => setMode("find")}>
              Find a game
            </span>
            <span className={`chip${mode === "link" ? " on" : ""}`} onClick={() => setMode("link")}>
              Paste a link
            </span>
            <span className={`chip${mode === "file" ? " on" : ""}`} onClick={() => setMode("file")}>
              Open a file
            </span>
            {game && <span className="chip" onClick={() => setOnGame(true)}>Last game read →</span>}
          </div>
          <div style={mode === "find" ? undefined : { display: "none" }}>
            <FindGame busy={busy !== null} run={run}
                      onPick={(played, player) => read(String(played.matchId), player.profileId)} />
          </div>
          <div style={mode === "link" ? undefined : { display: "none" }}>
            <p className="hint" style={{ margin: "0 0 10px" }}>
              A match link from aoe2companion or aoe2insights, the aoe.ms replay link, or the match id.
              Microsoft keeps replays for a few months.
            </p>
            <form className="row"
                  onSubmit={(e) => { e.preventDefault(); if (link.trim() && !busy) read(link.trim(), null); }}>
              <input type="text" className="grow" value={link} placeholder="https://www.aoe2companion.com/match/…"
                     onChange={(e) => setLink(e.target.value)} />
              <button type="submit" className="primary" disabled={!link.trim() || busy !== null}>Look up</button>
            </form>
          </div>
          <div style={mode === "file" ? undefined : { display: "none" }}>
            <p className="hint" style={{ margin: "0 0 10px" }}>
              A replay on this computer: the .aoe2record the game saves — usually under
              Games\Age of Empires 2 DE\&lt;your id&gt;\savegame — or the zip aoe.ms downloads.
              Choose it, or drop it anywhere on the page. It goes only to the reader running here.
            </p>
            <button className="primary" disabled={busy !== null} onClick={() => chooser.current?.click()}>
              Choose a replay…
            </button>
            <input ref={chooser} type="file" accept={REPLAY_FILES} hidden
                   onChange={(e) => {
                     const file = e.target.files?.[0];
                     if (file) openFile(file);
                     e.target.value = "";
                   }} />
          </div>
        </div>

        {busy && <p className="hint">{busy}</p>}
        {error && <p className="game-error">{error}</p>}
      </div>
    </div>
  );
}
