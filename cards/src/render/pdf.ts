import { toCanvas } from "html-to-image";

const A4 = { short: 595.28, long: 841.89 };
const MARGIN = 24;
const GAP = 12;
const HALF_A4 = (A4.short - 2 * MARGIN - GAP) / 2;

/**
 * `height: null` is a page as tall as its card, one card to a page. `column`
 * is the card width; absent, the columns fill the page between the margins.
 * `alone` is one card to a page.
 */
export type Sheet = {
  label: string; width: number; height: number | null; across: number;
  column?: number; alone?: boolean;
};

export const SHEETS = {
  a4Middle: { label: "A4, one in the middle", width: A4.short, height: A4.long, across: 1,
              column: (5 / 4) * HALF_A4, alone: true },
  a4Pairs: { label: "A4, two across", width: A4.short, height: A4.long, across: 2 },
  a4LandscapePairs: { label: "A4 landscape, two across", width: A4.long, height: A4.short, across: 2 },
  a4: { label: "A4, one across", width: A4.short, height: A4.long, across: 1 },
  cardSized: { label: "A page per card", width: A4.short, height: null, across: 1 },
} satisfies Record<string, Sheet>;

export type SheetName = keyof typeof SHEETS;

/** `breaks` are where a page may cut the card, as fractions of its height. */
type Shot = { width: number; height: number; pixels: Uint8Array<ArrayBuffer>; breaks: number[] };

/** `from` and `to` are the part of the card drawn, as fractions of its height. */
type Slice = { shot: number; x: number; top: number; width: number; from: number; to: number };

type Page = { width: number; height: number; slices: Slice[] };

/**
 * Cards as one PDF, in the order given, laid out on `sheet`.
 *
 * Every card is drawn at the same width, the width of one column. A card too
 * tall for the page is cut between two of its rows and carries on at the top
 * of the next page, rather than shrunk to fit and left narrower than the rest.
 * The nodes are off-screen copies, for the reason `cardToPng` takes one.
 */
export async function cardsToPdf(nodes: HTMLElement[], sheet: Sheet, scale = 2): Promise<Blob> {
  const shots: Shot[] = [];
  for (const node of nodes) {
    const canvas = await toCanvas(node, { pixelRatio: scale, backgroundColor: "#ffffff" });
    shots.push({ width: canvas.width, height: canvas.height,
                 pixels: await deflate(rows(canvas)), breaks: breaks(node) });
  }
  return write(shots, lay(shots, sheet));
}

/** Above a phase, or between two rows — never through a row, and never
 *  between a phase's label and its first row. */
function breaks(card: HTMLElement): number[] {
  const box = card.getBoundingClientRect();
  return [...card.querySelectorAll(".phase, .step:not(:first-child)")]
    .map((node) => (node.getBoundingClientRect().top - box.top) / box.height)
    .sort((a, b) => a - b);
}

/** Rows of `across` cards down the page. A row that does not fit under the
 *  last one starts a new page; a card that does not fit on a whole page is cut
 *  at the last break that does, and carries on in its own column. Columns
 *  narrower than the page are centred on it. */
function lay(shots: Shot[], sheet: Sheet): Page[] {
  const width = sheet.column ?? (sheet.width - 2 * MARGIN - (sheet.across - 1) * GAP) / sheet.across;
  const left = (sheet.width - sheet.across * width - (sheet.across - 1) * GAP) / 2;
  const tall = (shot: Shot) => (width * shot.height) / shot.width;
  const { height } = sheet;
  if (height === null) {
    return shots.map((shot, index) => ({
      width: sheet.width, height: tall(shot) + 2 * MARGIN,
      slices: [{ shot: index, x: left, top: MARGIN, width, from: 0, to: 1 }],
    }));
  }

  const room = height - 2 * MARGIN;
  const pages: Page[] = [];
  const pageAt = (n: number) => (pages[n] ??= { width: sheet.width, height, slices: [] });
  let [page, y] = [0, 0];
  for (let first = 0; first < shots.length; first += sheet.across) {
    const row = shots.slice(first, first + sheet.across);
    if (y > 0 && (sheet.alone || y + Math.max(...row.map(tall)) > room)) [page, y] = [page + 1, 0];
    let end = { page, y };
    row.forEach((shot, column) => {
      const x = left + column * (width + GAP);
      let [at, top, from] = [page, y, 0];
      for (;;) {
        const fits = from + (room - top) / tall(shot);
        const to = fits >= 1 ? 1 : (shot.breaks.findLast((b) => b > from && b <= fits) ?? fits);
        pageAt(at).slices.push({ shot: first + column, x, top: MARGIN + top, width, from, to });
        if (to === 1) break;
        [at, top, from] = [at + 1, 0, to];
      }
      const bottom = top + (1 - from) * tall(shot);
      if (at > end.page || (at === end.page && bottom > end.y)) end = { page: at, y: bottom };
    });
    [page, y] = [end.page, end.y + GAP];
  }
  return pages;
}

/** RGB with a PNG "Up" filter byte ahead of every row, which is what
 *  `/Predictor 15` reads. Alpha is dropped: the canvas is painted on white,
 *  so it is opaque everywhere. */
function rows(canvas: HTMLCanvasElement): Uint8Array<ArrayBuffer> {
  const { width, height } = canvas;
  const rgba = canvas.getContext("2d")!.getImageData(0, 0, width, height).data;
  const stride = width * 3 + 1;
  const out = new Uint8Array(stride * height);
  for (let y = 0; y < height; y++) {
    out[y * stride] = 2;
    for (let x = 0; x < width; x++) {
      const from = (y * width + x) * 4;
      const to = y * stride + 1 + x * 3;
      for (let c = 0; c < 3; c++) {
        const above = y ? rgba[from + c - width * 4] : 0;
        out[to + c] = (rgba[from + c] - above) & 0xff;
      }
    }
  }
  return out;
}

const deflate = async (bytes: Uint8Array<ArrayBuffer>) => new Uint8Array(
  await new Response(new Blob([bytes]).stream().pipeThrough(new CompressionStream("deflate")))
    .arrayBuffer());

const pt = (value: number) => value.toFixed(2);

/** A slice is the whole card drawn under a clip, so a card cut across two
 *  pages is one image in the file, not two. */
function draw(page: Page, slice: Slice, shot: Shot): string {
  const tall = (slice.width * shot.height) / shot.width;
  const shown = (slice.to - slice.from) * tall;
  const top = page.height - slice.top;
  return `q ${pt(slice.x)} ${pt(top - shown)} ${pt(slice.width)} ${pt(shown)} re W n`
    + ` ${pt(slice.width)} 0 0 ${pt(tall)} ${pt(slice.x)} ${pt(top + slice.from * tall - tall)} cm`
    + ` /Im${slice.shot} Do Q`;
}

function write(shots: Shot[], pages: Page[]): Blob {
  const parts: BlobPart[] = [];
  const offsets: number[] = [];
  let length = 0;
  const put = (part: string | Uint8Array<ArrayBuffer>) => {
    const bytes = typeof part === "string" ? new TextEncoder().encode(part) : part;
    parts.push(bytes);
    length += bytes.length;
  };
  const object = (id: number, dictionary: string, stream?: Uint8Array<ArrayBuffer>) => {
    offsets[id] = length;
    put(`${id} 0 obj\n${dictionary}\n`);
    if (stream) {
      put("stream\n");
      put(stream);
      put("\nendstream\n");
    }
    put("endobj\n");
  };

  // High bytes mark the file as binary, so transfer tools leave the streams alone.
  put("%PDF-1.4\n");
  put(new Uint8Array([0x25, 0xe2, 0xe3, 0xcf, 0xd3, 0x0a]));

  const imageId = (index: number) => 3 + index;
  const pageId = (index: number) => 3 + shots.length + 2 * index;
  object(1, "<< /Type /Catalog /Pages 2 0 R >>");
  object(2, `<< /Type /Pages /Kids [${pages.map((_, n) => `${pageId(n)} 0 R`).join(" ")}]`
    + ` /Count ${pages.length} >>`);

  shots.forEach((shot, index) => object(imageId(index),
    `<< /Type /XObject /Subtype /Image /Width ${shot.width} /Height ${shot.height}`
    + ` /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode`
    + ` /DecodeParms << /Predictor 15 /Colors 3 /Columns ${shot.width} >>`
    + ` /Length ${shot.pixels.length} >>`, shot.pixels));

  pages.forEach((page, n) => {
    const used = [...new Set(page.slices.map((slice) => slice.shot))];
    const content = new TextEncoder().encode(
      page.slices.map((slice) => draw(page, slice, shots[slice.shot])).join("\n"));
    object(pageId(n), `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${pt(page.width)} ${pt(page.height)}]`
      + ` /Resources << /XObject << ${used.map((i) => `/Im${i} ${imageId(i)} 0 R`).join(" ")} >> >>`
      + ` /Contents ${pageId(n) + 1} 0 R >>`);
    object(pageId(n) + 1, `<< /Length ${content.length} >>`, content);
  });

  const xref = length;
  const size = pageId(pages.length);
  put(`xref\n0 ${size}\n0000000000 65535 f \n`);
  for (let id = 1; id < size; id++) put(`${String(offsets[id]).padStart(10, "0")} 00000 n \n`);
  put(`trailer\n<< /Size ${size} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`);
  return new Blob(parts, { type: "application/pdf" });
}
