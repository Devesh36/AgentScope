import Image from "next/image";
import screenshots from "@/lib/terminal-screenshots.json";

export function TerminalTour() {
  return (
    <div className="docs-terminal-tour">
      <div className="docs-note">
        <strong>Actual terminal sessions, clearly labeled.</strong>
        <p>Captured with AgentScope 0.4.0 on 12 October 2026. Interactive terminal output is rendered in a terminal emulator. Chat and monitored calls use a genuine local model; the incident and recovery steps use labeled synthetic telemetry.</p>
      </div>
      <div className="docs-resource-links">
        <a href="/docs-assets/terminal-tour/agentscope-terminal-tour.pdf" download>Download the complete PDF tour</a>
      </div>
      <p>Expand a step to see its screenshot. Select the image or full-size link to read the terminal output in detail.</p>
      {screenshots.map((capture, index) => {
        const source = `/docs-assets/terminal-tour/${capture.name}.png`;
        return (
          <details className="docs-tour-step" key={capture.name} open={index === 0}>
            <summary>
              <span className="docs-tour-number">{String(index + 1).padStart(2, "0")}</span>
              <span className="docs-tour-title">{capture.title}</span>
              <span className={`docs-tour-kind${capture.kind === "Synthetic demo" ? " docs-tour-synthetic" : ""}`}>{capture.kind}</span>
              <span className="docs-tour-toggle" aria-hidden="true" />
            </summary>
            <figure className="docs-terminal-shot">
              <a href={source} target="_blank" rel="noopener noreferrer" aria-label={`Open ${capture.title} screenshot at full size`}>
                <Image src={source} alt={`${capture.title}: ${capture.caption}`} width={capture.width} height={capture.height} unoptimized loading="lazy" />
              </a>
              <figcaption>{capture.caption}</figcaption>
            </figure>
            <a className="docs-tour-full" href={source} target="_blank" rel="noopener noreferrer" aria-label={`Open full-size capture: ${capture.title}`}>Open full-size capture</a>
          </details>
        );
      })}
    </div>
  );
}
