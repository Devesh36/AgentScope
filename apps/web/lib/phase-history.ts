import { execFileSync } from "node:child_process";
import recorded from "./development-phases.json" with { type: "json" };

type Change = Omit<(typeof recorded.commits)[number], "sha"> & { sha: string | null };

// The snapshot preserves the complete curated history in shallow checkouts and
// Docker builds. Git supplies exact hashes/dates and includes newer commits.
export function mergePhaseHistory(log: string) {
  const changes: Change[] = recorded.commits.map((change) => ({ ...change }));
  for (const line of log.trim().split("\n")) {
    const [sha, timestamp, ...subjectParts] = line.split("\t");
    const subject = subjectParts.join("\t");
    if (!/^[a-f0-9]{40}$/.test(sha) || !timestamp || !subject) continue;
    const date = new Date(timestamp);
    if (Number.isNaN(date.getTime())) continue;
    const existing = changes.find((change) => change.sha === sha || (!change.sha && change.subject === subject));
    const day = date.toISOString().slice(0, 10);
    if (existing) {
      existing.sha = sha;
      existing.date = day;
    } else {
      changes.push({ sha, date: day, subject, phase: "ongoing", title: subject, summary: "" });
    }
  }
  const phases = [...recorded.phases];
  if (changes.some((change) => change.phase === "ongoing")) {
    phases.push({ id: "ongoing", title: "Continued development", summary: "The latest recorded changes to AgentScope." });
  }
  return phases.map((phase, index) => ({
    ...phase,
    number: String(index + 1).padStart(2, "0"),
    changes: changes.filter((change) => change.phase === phase.id).sort((a, b) => b.date.localeCompare(a.date)),
  })).filter((phase) => phase.changes.length).reverse();
}

export function getPhaseHistory() {
  let log = "";
  try {
    log = execFileSync("git", ["log", "--reverse", "--format=%H%x09%cI%x09%s"], {
      cwd: process.cwd(), encoding: "utf8", timeout: 5000,
      maxBuffer: 4 * 1024 * 1024, stdio: ["ignore", "pipe", "ignore"],
    });
  } catch {
    // A Git-free deployment still renders the checked-in development record.
  }
  return mergePhaseHistory(log);
}
