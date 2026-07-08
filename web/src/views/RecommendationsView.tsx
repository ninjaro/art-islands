import { useMemo } from "react";
import type { DomainModel } from "../lib/domain";
import type { FeatureIndex } from "../lib/features";
import { factorPhrase } from "../lib/features";
import { dateLabel } from "../lib/format";
import { scoreRecommendations } from "../lib/recommendations";
import type { Ratings, Settings } from "../lib/types";
import { KindIcon, RatingButtons, rowInteractionProps } from "../components/common";
import type { OpenHandler, RateHandler } from "../components/common";

export function RecommendationsView({
  domain,
  index,
  ratings,
  settings,
  onOpen,
  onRate,
}: {
  domain: DomainModel;
  index: FeatureIndex;
  ratings: Ratings;
  settings: Settings;
  onOpen: OpenHandler;
  onRate: RateHandler;
}) {
  const likedCount = useMemo(
    () => Object.values(ratings).filter((value) => value === 1).length,
    [ratings],
  );
  const scored = useMemo(
    () => (likedCount ? scoreRecommendations(domain, index, ratings, settings) : []),
    [domain, index, ratings, settings, likedCount],
  );

  if (!likedCount) {
    return (
      <section className="empty">
        Like several works first to build recommendations — the Browse tab is a good place to start. Liked works
        contribute their concepts, contributors, and content profile as positive evidence; dislikes subtract.
      </section>
    );
  }
  if (!scored.length) {
    return (
      <section className="empty">
        No unrated works share positive evidence with your liked works yet. Try liking a few more, or different,
        works.
      </section>
    );
  }

  return (
    <section className="recommendation-view">
      <div className="recommendation-head">
        <h2>Recommendations</h2>
        <span>{scored.length.toLocaleString()} shown</span>
      </div>
      <div className="table-wrap recommendation-table">
        <table>
          <thead>
            <tr>
              <th>Score</th>
              <th>Date</th>
              <th>Work</th>
              <th className="kind-head">
                <span className="visually-hidden">Kind</span>
              </th>
              <th>Why</th>
              <th>Rating</th>
            </tr>
          </thead>
          <tbody>
            {scored.map((result) => (
              <tr key={result.work.id} {...rowInteractionProps(result.work.id, result.work.label, onOpen)}>
                <td className="score-cell">{result.score.toFixed(2)}</td>
                <td className="date-cell">
                  {result.work.primaryDate
                    ? dateLabel(result.work.primaryDate.value, result.work.primaryDate.precision)
                    : ""}
                </td>
                <td className="label-cell">{result.work.label}</td>
                <td className="kind-cell">
                  <KindIcon broadKind={result.work.broadKind} label={result.work.typeLabel} />
                </td>
                <td className="why-cell">
                  {result.positive.slice(0, 2).map((factor) => (
                    <span key={factor.id} className="evidence positive">
                      {factorPhrase(factor)}
                    </span>
                  ))}
                  {result.negative.length ? (
                    <span className="evidence negative">− {factorPhrase(result.negative[0])}</span>
                  ) : null}
                </td>
                <td className="rating-cell">
                  <RatingButtons
                    id={result.work.id}
                    label={result.work.label}
                    rating={ratings[String(result.work.id)] || 0}
                    onRate={onRate}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
