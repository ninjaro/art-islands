import { useMemo } from "react";
import { dateLabel } from "../lib/format";
import { explanation, scoreRecommendations } from "../lib/recommendations";
import type { AppData, Ratings, Settings } from "../lib/types";
import { KindIcon, RatingButtons, rowInteractionProps } from "../components/common";
import type { OpenHandler, RateHandler } from "../components/common";

export function RecommendationsView({
  data,
  ratings,
  settings,
  onOpen,
  onRate,
}: {
  data: AppData;
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
    () => (likedCount ? scoreRecommendations(data.catalog, ratings, settings) : []),
    [data, ratings, settings, likedCount],
  );

  if (!likedCount) {
    return <section className="empty">Like several works first to build recommendations.</section>;
  }
  if (!scored.length) {
    return <section className="empty">No unrated works have positive liked-tag evidence yet.</section>;
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
              <tr key={result.item.id} {...rowInteractionProps(result.item.id, result.item.label, onOpen)}>
                <td className="score-cell">{result.score.toFixed(2)}</td>
                <td className="date-cell">{dateLabel(result.item.date, result.item.datePrecision)}</td>
                <td className="label-cell">{result.item.label}</td>
                <td className="kind-cell">
                  <KindIcon kind={result.item.kind} />
                </td>
                <td className="why-cell">{explanation(result)}</td>
                <td className="rating-cell">
                  <RatingButtons
                    id={result.item.id}
                    label={result.item.label}
                    rating={ratings[String(result.item.id)] || 0}
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
