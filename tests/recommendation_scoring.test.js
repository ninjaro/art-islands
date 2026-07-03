const test = require("node:test");
const assert = require("node:assert/strict");

const {
  explanation,
  scoreRecommendations,
} = require("../public/recommendations.js");

test("scores unrated catalog items from liked tag overlap", () => {
  const catalog = [
    { id: 1, label: "Liked", date: "1980-01-01", tags: [[10, 100, 0], [20, 25, 0]] },
    { id: 2, label: "Disliked", date: "1970-01-01", tags: [[30, 100, 0], [10, 50, 0]] },
    { id: 3, label: "Best candidate", date: "1960-01-01", tags: [[10, 100, 0], [40, 50, 0]] },
    { id: 4, label: "Mixed candidate", date: "1950-01-01", tags: [[10, 100, 0], [30, 20, 0]] },
    { id: 5, label: "No evidence", date: "1940-01-01", tags: [[99, 100, 0]] },
  ];

  const results = scoreRecommendations(
    catalog,
    { "1": 1, "2": -1 },
    { recommendation: { likeWeight: 2, dislikeWeight: 1, limit: 10 } },
  );

  assert.deepEqual(results.map((result) => result.item.id), [3, 4]);
  assert.equal(results[0].likedSharedTags, 1);
  assert.equal(results[0].dislikedSharedTags, 1);
  assert.equal(explanation(results[0]), "1 shared liked tag, 1 shared disliked tag");
});

test("returns no recommendations without liked records", () => {
  const results = scoreRecommendations(
    [{ id: 1, label: "Only", date: "2000-01-01", tags: [[10, 100, 0]] }],
    { "1": -1 },
    {},
  );

  assert.deepEqual(results, []);
});

test("applies configured recommendation limit", () => {
  const catalog = [
    { id: 1, label: "Liked", date: "2000-01-01", tags: [[10, 100, 0]] },
    { id: 2, label: "A", date: "1990-01-01", tags: [[10, 100, 0]] },
    { id: 3, label: "B", date: "1991-01-01", tags: [[10, 100, 0]] },
  ];

  const results = scoreRecommendations(
    catalog,
    { "1": 1 },
    { recommendation: { likeWeight: 1, dislikeWeight: 1, limit: 1 } },
  );

  assert.equal(results.length, 1);
  assert.equal(results[0].item.id, 2);
});
