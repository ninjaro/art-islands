import { useState } from "react";
import type { NormalizedConceptAssignment, NormalizedContributor, WorkViewModel } from "../lib/domain";
import { roleLabel } from "../lib/domain";
import { advisoryLevel, dateLabel, imageUrl } from "../lib/format";
import { KindIcon, RatingButtons } from "./common";
import type { RateHandler } from "./common";

const ROLE_DISPLAY_ORDER = [
  "director",
  "creator",
  "author",
  "screenwriter",
  "composer",
  "lyricist",
  "music_artist",
  "cast_member",
  "voice_actor",
  "performer",
  "producer",
  "production_company",
  "record_label",
  "distributor",
  "publisher",
  "broadcaster",
];

const CATEGORY_DISPLAY_ORDER = [
  "genre",
  "theme",
  "keyword",
  "style",
  "mood",
  "motif",
  "movement",
  "setting",
  "subject",
  "technique",
  "trope",
  "audience",
  "format",
  "franchise",
  "period",
  "language",
  "country",
];

function orderedKeys(keys: string[], preferred: string[], last?: string): string[] {
  const rank = new Map(preferred.map((key, index) => [key, index]));
  return [...keys].sort((a, b) => {
    if (last) {
      if (a === last && b !== last) return 1;
      if (b === last && a !== last) return -1;
    }
    const rankA = rank.get(a) ?? preferred.length;
    const rankB = rank.get(b) ?? preferred.length;
    return rankA - rankB || a.localeCompare(b);
  });
}

function ContributorNames({ contributors }: { contributors: NormalizedContributor[] }) {
  const [expanded, setExpanded] = useState(false);
  const limit = 8;
  const shown = expanded ? contributors : contributors.slice(0, limit);
  return (
    <>
      {shown
        .map((contributor) =>
          contributor.characterLabel ? `${contributor.label} (${contributor.characterLabel})` : contributor.label,
        )
        .join(", ")}
      {contributors.length > limit ? (
        <button type="button" className="inline-toggle" onClick={() => setExpanded((value) => !value)}>
          {expanded ? "Show fewer" : `Show all (${contributors.length})`}
        </button>
      ) : null}
    </>
  );
}

function ContributorSection({ work }: { work: WorkViewModel }) {
  const roles = orderedKeys(Object.keys(work.contributorsByRole), ROLE_DISPLAY_ORDER);
  return (
    <section className="work-section" aria-label="Contributors">
      <h3>Contributors</h3>
      <dl className="contributor-roles">
        {roles.map((role) => (
          <div key={role} className="contributor-role">
            <dt>{roleLabel(role)}</dt>
            <dd>
              <ContributorNames contributors={work.contributorsByRole[role]} />
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function MeasurementSection({ work }: { work: WorkViewModel }) {
  const rows = work.measurements.filter((measurement) => measurement.type !== "duration");
  if (!work.duration && !rows.length) return null;
  return (
    <section className="work-section" aria-label="Measurements">
      <h3>Details</h3>
      <ul className="measurement-list">
        {work.duration ? <li>Duration: {work.duration.label}</li> : null}
        {rows.map((measurement, index) => (
          <li key={`${measurement.type}-${index}`}>
            {measurement.type.replace(/_/g, " ")}: {measurement.number ?? measurement.text}
            {measurement.unit ? ` ${measurement.unit}` : ""}
            {measurement.qualifier ? ` (${measurement.qualifier})` : ""}
          </li>
        ))}
      </ul>
    </section>
  );
}

function ContentGuideSection({ work }: { work: WorkViewModel }) {
  return (
    <section className="work-section" aria-label="Parental and content guide">
      <h3>Content guide</h3>
      {work.ageRatings.length ? (
        <ul className="rating-list">
          {work.ageRatings.map((rating, index) => (
            <li key={index}>
              <strong>{rating.system}:</strong> {rating.certificate}
              {rating.minimumAge !== undefined ? ` (${rating.minimumAge}+)` : ""}
              {rating.edition ? ` — ${rating.edition}` : ""}
              {rating.descriptors.length ? (
                <span className="chips inline-chips">
                  {rating.descriptors.map((descriptor) => (
                    <span key={descriptor} className="chip">
                      {descriptor}
                    </span>
                  ))}
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
      {work.advisories.length ? (
        <ul className="advisory-list">
          {work.advisories.slice(0, 12).map((advisory) => {
            const level = advisoryLevel(advisory.intensity);
            return (
              <li key={advisory.categoryId} className={level ? `advisory ${level}` : "advisory"}>
                <span className="advisory-category">{advisory.category}</span>
                {level ? <span className="advisory-level">{level}</span> : null}
                {advisory.uncertainty !== undefined && advisory.uncertainty >= 30 ? (
                  <span className="advisory-uncertain">uncertain</span>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : null}
      {work.restrictions.length ? (
        <ul className="restriction-list">
          {work.restrictions.map((restriction, index) => (
            <li key={index}>
              {restriction.type.replace(/_/g, " ")}
              {restriction.countryCode ? ` · ${restriction.countryCode}` : ""}
              {restriction.region ? ` · ${restriction.region}` : ""}
              {restriction.startDate || restriction.endDate
                ? ` · ${restriction.startDate ?? "…"}–${restriction.endDate ?? "…"}`
                : ""}
              {restriction.status ? ` (${restriction.status})` : ""}
              {restriction.reason ? `: ${restriction.reason}` : ""}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

function ConceptCategory({ label, concepts }: { label: string; concepts: NormalizedConceptAssignment[] }) {
  const [expanded, setExpanded] = useState(false);
  const limit = 12;
  const shown = expanded ? concepts : concepts.slice(0, limit);
  return (
    <details className="work-section concept-category" open={label === "Genre"}>
      <summary>
        {label} ({concepts.length})
      </summary>
      <div className="chips">
        {shown.map((concept) => (
          <span
            key={concept.conceptId}
            className={concept.polarity < 0 ? "chip negative" : "chip"}
            title={concept.description || ""}
            aria-label={
              concept.polarity < 0 ? `${concept.label}, excluded` : `${concept.label}, weight ${concept.weight}`
            }
          >
            {concept.label} {concept.weight}
          </span>
        ))}
      </div>
      {concepts.length > limit ? (
        <button type="button" className="inline-toggle" onClick={() => setExpanded((value) => !value)}>
          {expanded ? "Show fewer" : `Show all (${concepts.length})`}
        </button>
      ) : null}
    </details>
  );
}

function ConceptSections({ work }: { work: WorkViewModel }) {
  const categories = orderedKeys(Object.keys(work.conceptsByCategory), CATEGORY_DISPLAY_ORDER, "other");
  return (
    <section className="work-section" aria-label="Concepts">
      <h3>Concepts</h3>
      {categories.map((category) => (
        <ConceptCategory
          key={category}
          label={work.conceptsByCategory[category][0].categoryLabel}
          concepts={work.conceptsByCategory[category]}
        />
      ))}
    </section>
  );
}

function ReferenceSection({ work }: { work: WorkViewModel }) {
  const seen = new Set<string>();
  const references = work.identifiers.filter((identifier) => {
    const key = `${identifier.label}:${identifier.url || identifier.value}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  return (
    <section className="work-section" aria-label="External references">
      <h3>References</h3>
      <div className="ref-list">
        {references.map((identifier) =>
          identifier.url ? (
            <a key={`${identifier.scheme}-${identifier.value}`} href={identifier.url} target="_blank" rel="noreferrer">
              {identifier.label}
            </a>
          ) : (
            <span key={`${identifier.scheme}-${identifier.value}`}>{identifier.label}</span>
          ),
        )}
      </div>
    </section>
  );
}

export function WorkDetails({
  work,
  rating,
  onRate,
}: {
  work: WorkViewModel;
  rating: number;
  onRate: RateHandler;
}) {
  const image = imageUrl(work.image ?? null);
  const hasContentGuide = work.ageRatings.length > 0 || work.advisories.length > 0 || work.restrictions.length > 0;
  return (
    <div className="entity-body">
      {image ? (
        <img className="entity-image" src={image} alt={work.label} loading="lazy" />
      ) : (
        <div className="entity-image placeholder" />
      )}
      <div className="entity-main">
        <section className="work-overview" aria-label="Overview">
          <div className="entity-meta">
            <KindIcon broadKind={work.broadKind} label={work.typeLabel} />
            <span>{work.primaryDate ? dateLabel(work.primaryDate.value, work.primaryDate.precision) : "undated"}</span>
            {work.duration ? <span>{work.duration.label}</span> : null}
          </div>
          {work.description ? <p className="work-description">{work.description}</p> : null}
          <RatingButtons id={work.id} label={work.label} rating={rating} onRate={onRate} />
        </section>
        {Object.keys(work.contributorsByRole).length ? <ContributorSection work={work} /> : null}
        <MeasurementSection work={work} />
        {hasContentGuide ? <ContentGuideSection work={work} /> : null}
        {work.concepts.length ? <ConceptSections work={work} /> : null}
        {work.identifiers.length ? <ReferenceSection work={work} /> : null}
      </div>
    </div>
  );
}
