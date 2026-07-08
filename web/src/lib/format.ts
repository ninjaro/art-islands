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

export function formatDuration(seconds: number): string {
  const total = Math.max(0, Math.round(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.round((total - hours * 3600) / 60);
  if (hours && minutes) return `${hours} h ${minutes} min`;
  if (hours) return `${hours} h`;
  return `${Math.max(1, minutes)} min`;
}

export function advisoryLevel(intensity?: number): "mild" | "moderate" | "high" | null {
  if (intensity === undefined || intensity === null) return null;
  return intensity >= 67 ? "high" : intensity >= 34 ? "moderate" : "mild";
}

/** Animation duration honoring the user's reduced-motion preference. */
export function motionDuration(ms: number): number {
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
    ? 0
    : ms;
}

const SCHEME_INFO: Record<string, { label: string; url: (value: string) => string }> = {
  wikidata: { label: "Wikidata", url: (v) => `https://www.wikidata.org/wiki/${v}` },
  imdb_title: { label: "IMDb", url: (v) => `https://www.imdb.com/title/${v}/` },
  imdb_name: { label: "IMDb", url: (v) => `https://www.imdb.com/name/${v}/` },
  imdb_company: { label: "IMDb", url: (v) => `https://www.imdb.com/company/${v}/` },
  tmdb_movie: { label: "TMDB", url: (v) => `https://www.themoviedb.org/movie/${v}` },
  tmdb_tv: { label: "TMDB", url: (v) => `https://www.themoviedb.org/tv/${v}` },
  musicbrainz_release_group: { label: "MusicBrainz", url: (v) => `https://musicbrainz.org/release-group/${v}` },
  musicbrainz_artist: { label: "MusicBrainz", url: (v) => `https://musicbrainz.org/artist/${v}` },
  musicbrainz_recording: { label: "MusicBrainz", url: (v) => `https://musicbrainz.org/recording/${v}` },
  musicbrainz_work: { label: "MusicBrainz", url: (v) => `https://musicbrainz.org/work/${v}` },
  discogs_release: { label: "Discogs", url: (v) => `https://www.discogs.com/release/${v}` },
  discogs_master: { label: "Discogs", url: (v) => `https://www.discogs.com/master/${v}` },
  discogs_artist: { label: "Discogs", url: (v) => `https://www.discogs.com/artist/${v}` },
};

export function schemeLabel(scheme: string): string {
  return SCHEME_INFO[scheme]?.label ?? scheme.replace(/_/g, " ");
}

export function identifierUrl(scheme: string, value: string): string {
  return SCHEME_INFO[scheme]?.url(value) ?? "";
}

