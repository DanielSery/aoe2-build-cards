import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { gameStrategy } from "../model/games";

/** A game's plan, or why there is none. */
export type Strategy = { text: string; failed?: boolean };

const AT_ONCE = 2;

/**
 * Each listed game's plan, filled in as its row comes into view. Every one is
 * a replay of several megabytes to download and read, so a game nobody
 * scrolls to is never fetched, and a row scrolled away before its turn is
 * dropped from the queue. The newest rows in view go first.
 *
 * `watch` is the row's ref; the row carries its match id as `data-match`.
 */
export function useStrategies(profileId: number | null) {
  const [plans, setPlans] = useState<Record<number, Strategy>>({});
  const queue = useRef<number[]>([]);
  const running = useRef(new Set<number>());
  const asked = useRef(new Set<number>());
  // Answers for a player no longer listed arrive after the switch; this tells them apart.
  const current = useRef(profileId);

  useEffect(() => {
    current.current = profileId;
    queue.current = [];
    running.current.clear();
    asked.current.clear();
    setPlans({});
  }, [profileId]);

  const pump = useCallback(() => {
    const player = current.current;
    if (player === null) return;
    while (running.current.size < AT_ONCE && queue.current.length) {
      const match = queue.current.shift()!;
      if (asked.current.has(match)) continue;
      asked.current.add(match);
      running.current.add(match);
      gameStrategy(match, player)
        .then((text): Strategy => ({ text }), (error: Error): Strategy => ({ text: error.message, failed: true }))
        .then((plan) => {
          if (current.current !== player) return;
          running.current.delete(match);
          setPlans((all) => ({ ...all, [match]: plan }));
          pump();
        });
    }
  }, []);

  const observer = useMemo(() => new IntersectionObserver((entries) => {
    for (const entry of entries) {
      const match = Number((entry.target as HTMLElement).dataset.match);
      queue.current = queue.current.filter((m) => m !== match);
      if (entry.isIntersecting && !asked.current.has(match)) queue.current.unshift(match);
    }
    pump();
  }), [pump]);

  useEffect(() => () => observer.disconnect(), [observer]);

  const watch = useCallback((node: HTMLElement | null) => {
    if (!node) return;
    observer.observe(node);
    return () => {
      observer.unobserve(node);
      queue.current = queue.current.filter((m) => m !== Number(node.dataset.match));
    };
  }, [observer]);

  return { plans, watch };
}
