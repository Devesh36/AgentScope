import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { test } from "node:test";
import { mergePhaseHistory } from "../apps/web/lib/phase-history.ts";

const recorded = JSON.parse(readFileSync(new URL("../apps/landing/lib/development-phases.json", import.meta.url)));
const flatten = (phases) => phases.flatMap((phase) => phase.changes);
const gitLog = execFileSync("git", ["log", "--reverse", "--format=%H%x09%cI%x09%s"], { encoding: "utf8" });

test("both independently deployed apps use the same history and renderer", () => {
  for (const file of ["lib/development-phases.json", "lib/phase-history.ts", "components/development-phases.tsx"]) {
    assert.equal(readFileSync(new URL(`../apps/landing/${file}`, import.meta.url), "utf8"), readFileSync(new URL(`../apps/web/${file}`, import.meta.url), "utf8"));
  }
});

test("every source commit appears exactly once with its UTC date", () => {
  const changes = flatten(mergePhaseHistory(gitLog));
  for (const line of gitLog.trim().split("\n")) {
    const [sha, timestamp] = line.split("\t");
    const matches = changes.filter((change) => change.sha === sha);
    assert.equal(matches.length, 1);
    assert.equal(matches[0].date, new Date(timestamp).toISOString().slice(0, 10));
  }
});

test("Git-free and shallow builds preserve the curated history", () => {
  for (const log of ["", gitLog.trim().split("\n").at(-1)]) {
    const changes = flatten(mergePhaseHistory(log));
    assert.equal(changes.length, recorded.commits.length);
    for (const change of recorded.commits) assert(changes.some((entry) => entry.subject === change.subject));
  }
});

test("future commits are included automatically without duplicating the prepared update", () => {
  const prepared = recorded.commits.find((change) => change.sha === null);
  const resolvedSha = "a".repeat(40);
  const newSha = "b".repeat(40);
  const previousLog = gitLog.trim().split("\n").filter((line) => !line.endsWith(`\t${prepared.subject}`)).join("\n");
  const phases = mergePhaseHistory(`${previousLog}\n${resolvedSha}\t2026-10-10T09:00:00Z\t${prepared.subject}\n${newSha}\t2026-10-11T00:30:00+02:00\tImprove trace filtering\n`);
  const changes = flatten(phases);
  assert.equal(changes.filter((change) => change.subject === prepared.subject).length, 1);
  assert.equal(changes.find((change) => change.subject === prepared.subject).sha, resolvedSha);
  assert.equal(phases[0].id, "ongoing");
  assert.equal(changes.find((change) => change.sha === newSha).date, "2026-10-10");
});
