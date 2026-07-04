import type { RefEntry } from "./types";

export const KIND_LABELS: Record<number, string> = {
  0: "unknown",
  1: "film",
  2: "music release",
  3: "person",
  4: "group",
  5: "organization",
  6: "video game",
  7: "work",
  8: "genre",
};

export function kindLabel(kind: number): string {
  return KIND_LABELS[kind] || "unknown";
}

export function dateLabel(date: string | null, precision: number): string {
  if (!date) return "";
  if (precision === 1) return date.slice(0, 4);
  if (precision === 2) return date.slice(0, 7);
  return date;
}

export function yearLabel(date: string | null): string {
  return date ? date.slice(0, 4) : "";
}

export function imageUrl(image: string | null): string {
  if (!image) return "";
  return `https://commons.wikimedia.org/wiki/Special:Redirect/file/${encodeURIComponent(image)}`;
}

export function externalUrl(ref: RefEntry): string {
  const [kind, value] = ref;
  if (kind === "wikidata") return `https://www.wikidata.org/wiki/${value}`;
  if (kind === "imdb") return `https://www.imdb.com/title/${value}/`;
  if (kind === "tmdb") return `https://www.themoviedb.org/movie/${value}`;
  if (kind === "musicbrainz") return `https://musicbrainz.org/release-group/${value}`;
  if (kind === "discogs") return `https://www.discogs.com/release/${value}`;
  return "";
}
