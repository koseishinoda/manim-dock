import * as vscode from "vscode";
import { revealRange } from "./outlineTree";
import { ProposedPatchProvider, confirmAndApplyPatch } from "./patchConfirm";
import { PropertiesPanel } from "./propertiesPanel";
import { SceneTimeline, SidecarClient, SourceRange, TimelineEvent } from "./sidecar";
import { StagePanel } from "./stagePanel";

/**
 * Timeline webview — beat bars; drag duration edge → confirm-diff → apply.
 */
export class TimelinePanel {
  public static readonly viewType = "manimDock.timeline";
  private static current: TimelinePanel | undefined;

  private readonly panel: vscode.WebviewPanel;
  private disposables: vscode.Disposable[] = [];
  private filePath: string | undefined;
  private sceneName: string | undefined;
  private timeline: SceneTimeline | undefined;

  private constructor(
    panel: vscode.WebviewPanel,
    private readonly context: vscode.ExtensionContext,
    private readonly sidecar: SidecarClient,
    private readonly output: vscode.OutputChannel
  ) {
    this.panel = panel;
    this.panel.onDidDispose(() => this.dispose(), null, this.disposables);
    this.panel.webview.onDidReceiveMessage(
      (msg) => {
        void this.onMessage(msg);
      },
      null,
      this.disposables
    );
    this.panel.webview.html = this.getHtml();
  }

  static async open(
    context: vscode.ExtensionContext,
    sidecar: SidecarClient,
    output: vscode.OutputChannel,
    filePath: string,
    sceneName: string
  ): Promise<TimelinePanel> {
    ProposedPatchProvider.ensure(context);
    const column = vscode.ViewColumn.Beside;

    if (TimelinePanel.current) {
      TimelinePanel.current.panel.reveal(column);
      await TimelinePanel.current.load(filePath, sceneName);
      return TimelinePanel.current;
    }

    const panel = vscode.window.createWebviewPanel(
      TimelinePanel.viewType,
      `Timeline: ${sceneName}`,
      column,
      {
        enableScripts: true,
        retainContextWhenHidden: true,
      }
    );
    TimelinePanel.current = new TimelinePanel(panel, context, sidecar, output);
    await TimelinePanel.current.load(filePath, sceneName);
    return TimelinePanel.current;
  }

  async load(filePath: string, sceneName: string): Promise<void> {
    this.filePath = filePath;
    this.sceneName = sceneName;
    this.panel.title = `Timeline: ${sceneName}`;
    await this.refresh();
  }

  static refreshIfOpen(filePath?: string): void {
    const cur = TimelinePanel.current;
    if (!cur?.filePath) {
      return;
    }
    if (filePath && cur.filePath !== filePath) {
      return;
    }
    void cur.refresh();
  }

  static highlightLine(filePath: string, line: number): void {
    const cur = TimelinePanel.current;
    if (!cur?.filePath || cur.filePath !== filePath) {
      return;
    }
    void cur.panel.webview.postMessage({ type: "highlightLine", line });
  }

  async refresh(): Promise<void> {
    if (!this.filePath || !this.sceneName) {
      return;
    }
    try {
      const doc = await vscode.workspace.openTextDocument(this.filePath);
      this.timeline = await this.sidecar.timeline(
        this.filePath,
        this.sceneName,
        doc.getText()
      );
      void this.panel.webview.postMessage({
        type: "timeline",
        timeline: this.timeline,
      });
      if (this.timeline.errors.length) {
        this.output.appendLine(`[timeline] ${this.timeline.errors.join("; ")}`);
      }
    } catch (err) {
      this.output.appendLine(`[timeline] ${String(err)}`);
      void vscode.window.showErrorMessage(
        `Manim Dock Timeline failed: ${String(err)}`
      );
    }
  }

  private activeUntilLineAt(time: number): number | undefined {
    const events = this.timeline?.events ?? [];
    let covering: TimelineEvent | undefined;
    let lastStarted: TimelineEvent | undefined;
    for (const ev of events) {
      if (ev.kind === "next_section") {
        continue;
      }
      const start = ev.start ?? 0;
      const end = start + (ev.duration ?? 0);
      if (time >= start && time <= end + 1e-9) {
        covering = ev;
      }
      if (time >= start) {
        lastStarted = ev;
      }
    }
    const pick = covering ?? lastStarted;
    if (!pick) {
      return undefined;
    }
    // Prefer end_line of covering event; else start_line + duration proxy via end_line.
    return pick.range.end_line || pick.range.start_line;
  }

  private async onMessage(msg: unknown): Promise<void> {
    if (!msg || typeof msg !== "object") {
      return;
    }
    const rec = msg as Record<string, unknown>;
    const type = rec.type;

    if (type === "ready") {
      if (this.timeline) {
        void this.panel.webview.postMessage({
          type: "timeline",
          timeline: this.timeline,
        });
      }
      return;
    }

    if (type === "select") {
      const range = rec.range as SourceRange | undefined;
      if (range && this.filePath) {
        await revealRange(this.filePath, range);
        const kind = String(rec.kind ?? "");
        const line = Number(rec.line ?? range.start_line ?? 0);
        const duration = Number(rec.duration ?? 0);
        if (kind === "play" || kind === "wait" || kind === "next_section") {
          PropertiesPanel.setSelection(this.filePath, {
            kind: "event",
            eventKind: kind,
            line,
            duration,
          });
        }
      }
      return;
    }

    if (type === "scrub") {
      const time = Number(rec.time ?? 0);
      if (!this.filePath || !Number.isFinite(time)) {
        return;
      }
      const activeUntilLine = this.activeUntilLineAt(time);
      StagePanel.scrub(this.filePath, time, activeUntilLine);
      return;
    }

    if (type === "reorder") {
      await this.handleReorder(rec);
      return;
    }

    if (type === "resize") {
      await this.handleResize(rec);
    }
  }

  private async handleReorder(rec: Record<string, unknown>): Promise<void> {
    if (!this.filePath) {
      return;
    }
    const lineA = Number(rec.lineA ?? 0);
    const lineB = Number(rec.lineB ?? 0);
    if (!lineA || !lineB || lineA === lineB) {
      return;
    }

    const doc = await vscode.workspace.openTextDocument(this.filePath);
    let proposal;
    try {
      proposal = await this.sidecar.proposeReorder(
        this.filePath,
        lineA,
        lineB,
        doc.getText()
      );
    } catch (err) {
      void vscode.window.showErrorMessage(
        `Manim Dock reorder failed: ${String(err)}`
      );
      await this.refresh();
      return;
    }

    if (!proposal.ok) {
      void vscode.window.showWarningMessage(
        `Manim Dock: could not reorder: ${proposal.error ?? "unknown"}`
      );
      await this.refresh();
      return;
    }

    await confirmAndApplyPatch(
      this.context,
      {
        path: this.filePath,
        original: proposal.original,
        proposed: proposal.proposed,
        summary: proposal.summary,
        diff: proposal.diff,
      },
      this.output,
      "timeline"
    );
    await this.refresh();
  }

  private async handleResize(rec: Record<string, unknown>): Promise<void> {
    if (!this.filePath) {
      return;
    }
    const kind = String(rec.kind ?? "");
    const line = Number(rec.line ?? 0);
    const duration = Number(rec.duration ?? 0);
    if ((kind !== "play" && kind !== "wait") || !line || duration < 0) {
      return;
    }

    PropertiesPanel.setSelection(this.filePath, {
      kind: "event",
      eventKind: kind,
      line,
      duration,
    });

    const doc = await vscode.workspace.openTextDocument(this.filePath);
    const source = doc.getText();

    let proposal;
    try {
      proposal = await this.sidecar.proposeDuration(
        this.filePath,
        kind,
        line,
        duration,
        source
      );
    } catch (err) {
      void vscode.window.showErrorMessage(
        `Manim Dock timing patch failed: ${String(err)}`
      );
      await this.refresh();
      return;
    }

    if (!proposal.ok) {
      void vscode.window.showWarningMessage(
        `Manim Dock: could not patch timing: ${proposal.error ?? "unknown"}`
      );
      await this.refresh();
      return;
    }

    await confirmAndApplyPatch(
      this.context,
      {
        path: this.filePath,
        original: proposal.original,
        proposed: proposal.proposed,
        summary: proposal.summary,
        diff: proposal.diff,
      },
      this.output,
      "timeline"
    );
    await this.refresh();
  }

  private getHtml(): string {
    const csp = [
      "default-src 'none'",
      "script-src 'unsafe-inline'",
      "style-src 'unsafe-inline'",
    ].join("; ");

    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta http-equiv="Content-Security-Policy" content="${csp}" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Manim Dock Timeline</title>
  <style>
    html, body { margin: 0; height: 100%; background: #1a1b1e; color: #c8c8c8;
      font-family: var(--vscode-font-family, system-ui, sans-serif);
      display: flex; flex-direction: column; overflow: hidden; }
    .bar { flex: 0 0 auto; display: flex; gap: 12px; align-items: center; padding: 8px 12px;
      font-size: 12px; border-bottom: 1px solid #333; flex-wrap: wrap; }
    .bar strong { color: #eee; }
    .hint { opacity: 0.7; }
    .scrub-wrap { display: flex; align-items: center; gap: 8px; min-width: 160px; flex: 1 1 180px; }
    .scrub-wrap input[type="range"] { flex: 1 1 auto; min-width: 80px; }
    #scrubLabel { font-variant-numeric: tabular-nums; opacity: 0.85; min-width: 48px; }
    #rows { flex: 1 1 auto; min-height: 0; padding: 12px; overflow: auto; box-sizing: border-box; }
    .row { display: grid; grid-template-columns: minmax(96px, 140px) minmax(0, 1fr) 56px 52px; gap: 8px;
      align-items: center; margin-bottom: 6px; font-size: 12px; }
    .label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; cursor: pointer; min-width: 0; }
    .label:hover { color: #fff; }
    .track { position: relative; height: 22px; width: 100%; min-width: 0;
      background: #111214; border: 1px solid #333; border-radius: 3px; box-sizing: border-box; }
    .block { position: absolute; top: 1px; bottom: 1px; border-radius: 2px; box-sizing: border-box; }
    .block.play { background: #2d4a6f; border: 1px solid #7eb6ff; }
    .block.wait { background: #3d3a2d; border: 1px solid #c9b56a; }
    .block.section { background: transparent; border-left: 2px solid #888; width: 0 !important; min-width: 0; padding: 0; }
    .block.locked { opacity: 0.55; }
    .handle { position: absolute; right: 0; top: 0; bottom: 0; width: 8px; cursor: ew-resize; }
    .dur { text-align: right; opacity: 0.85; font-variant-numeric: tabular-nums; white-space: nowrap; }
    .reorder { display: flex; gap: 2px; justify-content: flex-end; }
    .reorder button {
      background: #2a2a2e; color: #ddd; border: 1px solid #555; border-radius: 2px;
      padding: 0 6px; font: inherit; cursor: pointer; line-height: 18px;
    }
    .reorder button:disabled { opacity: 0.35; cursor: default; }
    .section-row .label { font-weight: 600; color: #ddd; }
    .row.active { outline: 1px solid #ffe08a; outline-offset: 2px; border-radius: 2px; }
    .row.active .label { color: #ffe08a; }
  </style>
</head>
<body>
  <div class="bar">
    <strong id="title">Timeline</strong>
    <div class="scrub-wrap">
      <span>Scrub</span>
      <input id="scrub" type="range" min="0" max="1" step="0.01" value="0" />
      <span id="scrubLabel">0s</span>
    </div>
    <span class="hint">Scrub syncs Stage · ↑↓ reorder adjacent play/wait · drag edge for duration · confirm-diff</span>
  </div>
  <div id="rows"></div>
  <script>
    const vscode = acquireVsCodeApi();
    const rowsEl = document.getElementById('rows');
    const titleEl = document.getElementById('title');
    const scrubEl = document.getElementById('scrub');
    const scrubLabel = document.getElementById('scrubLabel');
    let timeline = null;
    let pendingHighlightLine = null;

    function fmt(n) {
      return (Math.round(n * 100) / 100).toString();
    }

    function isBeat(ev) {
      return ev.kind === 'play' || ev.kind === 'wait';
    }

    function rebuild() {
      rowsEl.innerHTML = '';
      if (!timeline) return;
      const events = timeline.events || [];
      const total = Math.max(timeline.total_duration || 1, 0.01);
      titleEl.textContent = 'Timeline: ' + (timeline.scene || '') +
        ' · ' + fmt(total) + 's';
      scrubEl.max = String(total);
      scrubEl.step = String(Math.max(0.01, total / 200));
      if (Number(scrubEl.value) > total) {
        scrubEl.value = String(total);
      }
      scrubLabel.textContent = fmt(Number(scrubEl.value)) + 's';

      const beatIndices = [];
      events.forEach((ev, i) => {
        if (isBeat(ev)) beatIndices.push(i);
      });

      for (let i = 0; i < events.length; i++) {
        const ev = events[i];
        const row = document.createElement('div');
        row.className = 'row' + (ev.kind === 'next_section' ? ' section-row' : '');
        row.dataset.startLine = String(ev.range && ev.range.start_line || 0);
        row.dataset.endLine = String(ev.range && ev.range.end_line || 0);
        row.dataset.method = ev.method || '';

        const label = document.createElement('div');
        label.className = 'label';
        label.title = (ev.note || '') + (ev.method ? ' @ ' + ev.method : '');
        label.textContent = ev.kind === 'next_section' ? ('§ ' + ev.label) : ev.label;
        label.addEventListener('click', () => {
          vscode.postMessage({
            type: 'select',
            range: ev.range,
            kind: ev.kind,
            line: ev.range && ev.range.start_line,
            duration: ev.duration || 0
          });
        });

        const track = document.createElement('div');
        track.className = 'track';

        // Percentage of total duration — always stays inside the track box.
        const leftPct = Math.max(0, Math.min(100, ((ev.start || 0) / total) * 100));
        const widthPct = ev.kind === 'next_section'
          ? 0
          : Math.max(0.5, Math.min(100 - leftPct, ((ev.duration || 0) / total) * 100));

        const block = document.createElement('div');
        block.className = 'block ' + ev.kind + (ev.editable ? '' : ' locked');
        block.style.left = leftPct + '%';
        block.style.width = widthPct + '%';
        track.appendChild(block);

        const dur = document.createElement('div');
        dur.className = 'dur';
        if (ev.kind === 'next_section') {
          dur.textContent = '';
        } else {
          dur.textContent = fmt(ev.duration || 0) + 's';
          if (!ev.editable) dur.title = ev.note || 'not editable';
        }

        if (ev.editable && (ev.kind === 'play' || ev.kind === 'wait')) {
          const handle = document.createElement('div');
          handle.className = 'handle';
          block.appendChild(handle);
          let startX = 0;
          let startPct = 0;
          handle.addEventListener('mousedown', (e) => {
            e.preventDefault();
            e.stopPropagation();
            startX = e.clientX;
            startPct = widthPct;
            const trackW = Math.max(1, track.getBoundingClientRect().width);
            const onMove = (ev2) => {
              const deltaPct = ((ev2.clientX - startX) / trackW) * 100;
              const next = Math.max(0.5, Math.min(100 - leftPct, startPct + deltaPct));
              block.style.width = next + '%';
              dur.textContent = fmt((next / 100) * total) + 's';
            };
            const onUp = (ev2) => {
              window.removeEventListener('mousemove', onMove);
              window.removeEventListener('mouseup', onUp);
              const deltaPct = ((ev2.clientX - startX) / trackW) * 100;
              const next = Math.max(0.5, Math.min(100 - leftPct, startPct + deltaPct));
              const rounded = Math.round(((next / 100) * total) * 100) / 100;
              if (Math.abs(rounded - (ev.duration || 0)) < 0.01) {
                rebuild();
                return;
              }
              vscode.postMessage({
                type: 'resize',
                kind: ev.kind,
                line: ev.range && ev.range.start_line,
                duration: rounded,
                id: ev.id
              });
            };
            window.addEventListener('mousemove', onMove);
            window.addEventListener('mouseup', onUp);
          });
        }

        const reorder = document.createElement('div');
        reorder.className = 'reorder';
        if (isBeat(ev)) {
          const posAmongBeats = beatIndices.indexOf(i);
          const up = document.createElement('button');
          up.textContent = '↑';
          up.title = 'Swap with previous play/wait';
          up.disabled = posAmongBeats <= 0;
          up.addEventListener('click', (e) => {
            e.stopPropagation();
            if (posAmongBeats <= 0) return;
            const prev = events[beatIndices[posAmongBeats - 1]];
            vscode.postMessage({
              type: 'reorder',
              lineA: ev.range && ev.range.start_line,
              lineB: prev.range && prev.range.start_line
            });
          });
          const down = document.createElement('button');
          down.textContent = '↓';
          down.title = 'Swap with next play/wait';
          down.disabled = posAmongBeats < 0 || posAmongBeats >= beatIndices.length - 1;
          down.addEventListener('click', (e) => {
            e.stopPropagation();
            if (posAmongBeats < 0 || posAmongBeats >= beatIndices.length - 1) return;
            const next = events[beatIndices[posAmongBeats + 1]];
            vscode.postMessage({
              type: 'reorder',
              lineA: ev.range && ev.range.start_line,
              lineB: next.range && next.range.start_line
            });
          });
          reorder.appendChild(up);
          reorder.appendChild(down);
        }

        row.appendChild(label);
        row.appendChild(track);
        row.appendChild(dur);
        row.appendChild(reorder);
        rowsEl.appendChild(row);
      }
      if (pendingHighlightLine != null) {
        highlightLine(pendingHighlightLine);
      }
    }

    function highlightLine(line) {
      pendingHighlightLine = line;
      const rows = rowsEl.querySelectorAll('.row');
      let best = null;
      let bestDist = Infinity;
      rows.forEach((row) => {
        row.classList.remove('active');
        const start = Number(row.dataset.startLine || 0);
        const end = Number(row.dataset.endLine || start);
        if (line >= start && line <= end) {
          best = row;
          bestDist = 0;
        } else if (bestDist > 0) {
          const dist = Math.min(Math.abs(line - start), Math.abs(line - end));
          if (dist < bestDist && dist <= 2) {
            best = row;
            bestDist = dist;
          }
        }
      });
      if (best) {
        best.classList.add('active');
        best.scrollIntoView({ block: 'nearest' });
      }
    }

    scrubEl.addEventListener('input', () => {
      const time = Number(scrubEl.value) || 0;
      scrubLabel.textContent = fmt(time) + 's';
      vscode.postMessage({ type: 'scrub', time: time });
    });

    window.addEventListener('message', (event) => {
      const msg = event.data;
      if (msg && msg.type === 'timeline') {
        timeline = msg.timeline;
        rebuild();
      } else if (msg && msg.type === 'highlightLine') {
        highlightLine(msg.line);
      }
    });
    vscode.postMessage({ type: 'ready' });
  </script>
</body>
</html>`;
  }

  dispose(): void {
    TimelinePanel.current = undefined;
    while (this.disposables.length) {
      this.disposables.pop()?.dispose();
    }
  }
}
