import { useState } from "react";
import type { PlayedGame, Profile } from "../model/games";
import { findPlayers, recentGames } from "../model/games";
import { useStrategies } from "./strategies";

type Filter = { format: string; seat: string; civ: string; map: string };
type Key = keyof Filter;

const ANY: Filter = { format: "", seat: "", civ: "", map: "" };
const FORMATS = ["1v1", "2v2", "3v3", "4v4"];
// Two players on a side are both on an end of their team's arc: a 2v2 has no pocket.
const SEATED = new Set(["3v3", "4v4"]);
const SHOWN = 200;

const passes = (game: PlayedGame, filter: Filter, except?: Key) =>
  (Object.keys(filter) as Key[]).every((key) =>
    key === except || !filter[key] || (game[key] ?? "") === filter[key]);

/** Options for one filter, counted under every *other* filter, so a number
 *  beside a choice is how many games picking it would leave. */
function tally(games: PlayedGame[], filter: Filter, key: Key): [string, number][] {
  const counts = new Map<string, number>();
  for (const game of games) {
    const value = game[key];
    if (value && passes(game, filter, key)) counts.set(value, (counts.get(value) ?? 0) + 1);
  }
  if (filter[key] && !counts.has(filter[key])) counts.set(filter[key], 0);
  return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}

const when = (started: string | null) =>
  started ? new Date(started).toLocaleString(undefined,
    { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "";

type Props = {
  busy: boolean;
  run: (doing: string, work: () => Promise<void>) => Promise<void>;
  onPick: (game: PlayedGame, player: Profile) => void;
};

export function FindGame({ busy, run, onPick }: Props) {
  const [query, setQuery] = useState("");
  const [found, setFound] = useState<Profile[] | null>(null);
  const [player, setPlayer] = useState<Profile | null>(null);
  const [games, setGames] = useState<PlayedGame[] | null>(null);
  const [filter, setFilter] = useState<Filter>(ANY);
  const { plans, watch } = useStrategies(player?.profileId ?? null);

  const load = async (profile: Profile) => {
    setPlayer(profile);
    setFound(null);
    setGames(null);
    setGames(await recentGames(profile.profileId));
  };

  const search = () => run("Searching aoe2companion…", async () => {
    const profiles = await findPlayers(query.trim());
    if (profiles.length === 1) await load(profiles[0]);
    else {
      setPlayer(null);
      setGames(null);
      setFound(profiles);
    }
  });

  const choose = (profile: Profile) => run(`Fetching ${profile.name}'s recent games…`, () => load(profile));

  const set = (key: Key, value: string) => setFilter((f) => {
    const next = { ...f, [key]: value };
    if (key === "format" && value && !SEATED.has(value)) next.seat = "";
    return next;
  });

  const select = (key: Key, any: string, options: [string, number][], disabled = false) => (
    <select value={filter[key]} disabled={disabled} onChange={(e) => set(key, e.target.value)}>
      <option value="">{any}</option>
      {options.map(([value, n]) => <option key={value} value={value}>{value} ({n})</option>)}
    </select>
  );

  const shown = games?.filter((g) => passes(g, filter)) ?? [];

  return (
    <div>
      <form className="row" onSubmit={(e) => { e.preventDefault(); if (query.trim() && !busy) search(); }}>
        <input type="text" className="grow" value={query} placeholder="Player name, profile id or link"
               onChange={(e) => setQuery(e.target.value)} />
        <button type="submit" className="primary" disabled={!query.trim() || busy}>Search</button>
      </form>

      {found && (
        <div className="finder-list">
          {found.map((profile) => (
            <button key={profile.profileId} className="game-player" disabled={busy}
                    onClick={() => choose(profile)}>
              <span className="grow name">{profile.name}{profile.verified ? " ✓" : ""}</span>
              <span className="hint">{[profile.clan, profile.country.toUpperCase()].filter(Boolean).join(" · ")}</span>
              <span className="hint">{profile.games} games · {profile.profileId}</span>
            </button>
          ))}
        </div>
      )}

      {player && games && (
        <>
          <p className="hint">
            <strong>{player.name}</strong> · {games.length} games
            {games.length ? ` since ${new Date(games.at(-1)!.started ?? "").toLocaleDateString()}` : ""}.
            Nothing older than four months is listed: its replay is gone. A filter left on “any” filters nothing.
          </p>
          <div className="row">
            <select value={filter.format} onChange={(e) => set("format", e.target.value)}>
              <option value="">Any format</option>
              {FORMATS.map((f) => (
                <option key={f} value={f}>
                  {f} ({games.filter((g) => g.format === f && passes(g, filter, "format")).length})
                </option>
              ))}
            </select>
            {select("seat", "Any seat", tally(games, filter, "seat"),
                    Boolean(filter.format) && !SEATED.has(filter.format))}
            {select("civ", "Any civ", tally(games, filter, "civ"))}
            {select("map", "Any map", tally(games, filter, "map"))}
            {Object.values(filter).some(Boolean) &&
              <button className="tiny" onClick={() => setFilter(ANY)}>Clear</button>}
          </div>
          <p className="hint">{shown.length} game{shown.length === 1 ? "" : "s"} — pick one to read its replay</p>
          <div className="finder-list">
            {shown.slice(0, SHOWN).map((game) => (
              <button key={game.matchId} className="found-game" disabled={busy}
                      ref={watch} data-match={game.matchId}
                      title={[game.leaderboard, game.allies.length ? `with ${game.allies.join(", ")}` : "",
                              `against ${game.opponents.join(", ")}`].filter(Boolean).join("\n")}
                      onClick={() => onPick(game, player)}>
                <span className="hint">{when(game.started)}</span>
                <span className="name">{game.map}</span>
                <span>{game.format}</span>
                <span className="hint">{game.seat ?? ""}</span>
                <span>{game.civ}</span>
                <span className={game.won ? "won" : "lost"}>{game.won == null ? "" : game.won ? "W" : "L"}</span>
                <span className={`plan${plans[game.matchId]?.failed ? " failed" : ""}`}
                      title={plans[game.matchId]?.failed ? plans[game.matchId].text : undefined}>
                  {plans[game.matchId] ? (plans[game.matchId].failed ? "no plan read" : plans[game.matchId].text) : "…"}
                </span>
              </button>
            ))}
            {shown.length > SHOWN && <p className="hint">and {shown.length - SHOWN} more — narrow the filters</p>}
          </div>
        </>
      )}
    </div>
  );
}
