import { toPng } from "html-to-image";

/**
 * The card as an image, at twice its screen size so it stands up to a Discord
 * or forum thumbnail.
 *
 * The node handed in is the off-screen copy, never the one being edited: the
 * library re-lays-out its clone, and a card carrying placeholders and drop
 * targets reflows differently from the finished one — which showed up as rows
 * overlapping each other in the PNG while the screen looked right.
 *
 * Nothing is passed for width or height on purpose. Pinning them makes any
 * difference between the clone's layout and the original's overlap instead of
 * merely resize, which is the same bug wearing a hat.
 *
 * Fonts are whatever the machine has, which is why the stack in theme.css is
 * system faces only — a webfont that had not finished loading would export as
 * a fallback.
 */
export async function cardToPng(node: HTMLElement, scale = 2): Promise<Blob> {
  const url = await toPng(node, { pixelRatio: scale, backgroundColor: "#ffffff" });
  return await (await fetch(url)).blob();
}
