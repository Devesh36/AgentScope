import { ArrowUpRight, GitCommitHorizontal } from "lucide-react";
import { getPhaseHistory } from "@/lib/phase-history";

const repository = "https://github.com/Devesh36/AgentScope";
const dateLabel = (day: string) => new Intl.DateTimeFormat("en-GB", {
  day: "numeric", month: "short", year: "numeric", timeZone: "UTC",
}).format(new Date(`${day}T00:00:00Z`));

export function DevelopmentPhases() {
  const phases = getPhaseHistory();
  return (
    <section className="landing-phase-section" id="phase" aria-labelledby="phase-heading">
      <div className="landing-phase-intro">
        <div><span className="landing-kicker">BUILDING AGENTSCOPE, STEP BY STEP</span><h2 id="phase-heading">Phase</h2><p>How AgentScope took shape. Each phase records what changed, when it changed, and what it brought to the product.</p></div>
        <a className="landing-text-link" href={`${repository}/commits/main`}>Explore the source history <ArrowUpRight size={15} /></a>
      </div>
      <div className="landing-phase-caption"><span>{phases.length} development phases</span><span>Latest first · Dates in UTC</span></div>
      <ol className="landing-phase-timeline">
        {phases.map((phase, index) => (
          <li className="landing-phase-item" key={phase.id}>
            <span className="landing-phase-number" aria-hidden="true">{phase.number}</span>
            <article className="landing-phase-card" aria-labelledby={`phase-${phase.id}`}>
              <div className="landing-phase-header"><span className="landing-kicker">PHASE {phase.number}</span>{index === 0 && <span className="landing-phase-latest">LATEST UPDATE</span>}</div>
              <h3 id={`phase-${phase.id}`}>{phase.title}</h3><p>{phase.summary}</p>
              <ul className="landing-phase-changes">
                {phase.changes.map((change) => (
                  <li key={change.sha ?? change.subject}>
                    <div className="landing-phase-change-date"><time dateTime={change.date}>{dateLabel(change.date)}</time>{change.sha ? <a href={`${repository}/commit/${change.sha}`} aria-label={`View commit ${change.sha.slice(0, 7)}: ${change.title}`}><GitCommitHorizontal size={14} /><code>{change.sha.slice(0, 7)}</code><ArrowUpRight size={12} /></a> : <span>This update</span>}</div>
                    <div><h4>{change.title}</h4>{change.summary && <p>{change.summary}</p>}</div>
                  </li>
                ))}
              </ul>
            </article>
          </li>
        ))}
      </ol>
    </section>
  );
}
