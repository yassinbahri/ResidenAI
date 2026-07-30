import { DiffResponse } from "../lib/api";

function lineClass(line: string): string {
  if (line.startsWith("+++") || line.startsWith("---")) return "diff-file-header";
  if (line.startsWith("@@")) return "diff-hunk-header";
  if (line.startsWith("+")) return "diff-added";
  if (line.startsWith("-")) return "diff-removed";
  return "diff-context";
}

export function DiffView({ diff }: { diff: DiffResponse }) {
  if (diff.is_first_version) {
    return (
      <div className="diff-view">
        <p className="diff-first-version-note">First captured version - no prior content to compare against.</p>
        <pre className="diff-content">
          {diff.diff_lines.map((line, i) => (
            <div key={i} className="diff-context">
              {line}
            </div>
          ))}
        </pre>
      </div>
    );
  }

  if (diff.diff_lines.length === 0) {
    return <p className="diff-first-version-note">No textual difference from the previous version.</p>;
  }

  return (
    <div className="diff-view">
      <pre className="diff-content">
        {diff.diff_lines.map((line, i) => (
          <div key={i} className={lineClass(line)}>
            {line}
          </div>
        ))}
      </pre>
    </div>
  );
}
