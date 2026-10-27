/**
 * Recorded games, read by the replay server (`replays/server.py`).
 *
 * The one thing in the app that needs a server: a replay is a binary file
 * Microsoft only serves to a program, and reading it is Python. The server also
 * serves this app, so the calls are relative to the page. Opened any other way
 * there is nothing at the other end, and every call says so instead of failing
 * with a parse error.
 */

export type GamePlayer = {
  number: number;
  profileId: number | null;
  name: string;
  civ: string;
  team: number;
  won: boolean | null;
  color: string;
  feudal: string | null;
  castle: string | null;
  /** What they were doing, in a few words: "men-at-arms → archers". */
  strategy: string;
};

export type Game = {
  /** A match id, or `local-…` for a file opened from this computer. */
  matchId: number | string;
  map: string;
  setting: string;
  started: string | null;
  duration: string;
  players: GamePlayer[];
};

export type Profile = {
  profileId: number;
  name: string;
  clan: string;
  country: string;
  games: number;
  verified: boolean;
};

/** One of a player's recent games, as the finder filters it. `seat` is null
 *  wherever the game cannot say: a 1v1 or 2v2, a nomad start, scattered teams. */
export type PlayedGame = {
  matchId: number;
  started: string | null;
  map: string;
  leaderboard: string;
  format: string;
  civ: string;
  seat: "flank" | "pocket" | null;
  won: boolean | null;
  rating: number | null;
  allies: string[];
  opponents: string[];
};

export const NO_SERVER =
  "The replay reader is not running. Start it from the repository root with " +
  "`python -m uvicorn replays.server:app --port 8030`, then try again.";

async function ask<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch {
    throw new Error(NO_SERVER);
  }
  // A static host answers an unknown path with the app's own page, so anything
  // that is not JSON means there is no reader behind this page.
  if (!response.headers.get("content-type")?.includes("application/json")) throw new Error(NO_SERVER);
  const body = await response.json();
  if (!response.ok) throw new Error(typeof body?.detail === "string" ? body.detail : `HTTP ${response.status}`);
  return body as T;
}

export const lookUpGame = (link: string) =>
  ask<Game>(`api/games?link=${encodeURIComponent(link)}`);

/** What a replay file from this computer is called: the .aoe2record a game
 *  saves, or the zip aoe.ms serves. */
export const REPLAY_FILES = ".aoe2record,.zip";

export const isReplay = (file: File) =>
  REPLAY_FILES.split(",").some((ending) => file.name.toLowerCase().endsWith(ending));

export const openReplay = (file: File) =>
  ask<Game>("api/games/file", { method: "POST", body: file });

export const cardFromGame = (matchId: number | string, player: number) =>
  ask<unknown>(`api/games/${matchId}/cards/${player}`);

export const findPlayers = (search: string) =>
  ask<Profile[]>(`api/players?search=${encodeURIComponent(search)}`);

export const recentGames = (profileId: number) =>
  ask<PlayedGame[]>(`api/players/${profileId}/games`);

export const gameStrategy = (matchId: number, profileId: number) =>
  ask<{ strategy: string }>(`api/games/${matchId}/strategy/${profileId}`).then((r) => r.strategy);
