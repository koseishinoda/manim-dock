import * as vscode from "vscode";
import { revealRange } from "./outlineTree";
import { ProposedPatchProvider, confirmAndApplyPatch } from "./patchConfirm";
import { SceneTimeline, SidecarClient, SourceRange } from "./sidecar";

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
      }
      return;
    }

    if (type === "resize") {
      await this.handleResize(rec);
    }
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
    .bar { flex: 0 0 auto; display: flex; gap: 12px; align-items: baseline; padding: 8px 12px;
      font-size: 12px; border-bottom: 1px solid #333; flex-wrap: wrap; }
    .bar strong { color: #eee; }
    .hint { opacity: 0.7; }
    #rows { flex: 1 1 auto; min-height: 0; padding: 12px; overflow: auto; box-sizing: border-box; }
    .row { display: grid; grid-template-columns: minmax(96px, 140px) minmax(0, 1fr) 56px; gap: 8px;
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
    .section-row .label { font-weight: 600; color: #ddd; }
  </style>
</head>
<body>
  <div class="bar">
    <strong id="title">Timeline</strong>
    <span class="hint">Drag the right edge of play/wait bars to change duration · confirm-diff before apply · constants stay code-owned</span>
  </div>
  <div id="rows"></div>
  <script>
    const vscode = acquireVsCodeApi();
    const rowsEl = document.getElementById('rows');
    const titleEl = document.getElementById('title');
    let timeline = null;

    function fmt(n) {
      return (Math.round(n * 100) / 100).toString();
    }

    function rebuild() {
      rowsEl.innerHTML = '';
      if (!timeline) return;
      const events = timeline.events || [];
      const total = Math.max(timeline.total_duration || 1, 0.01);
      titleEl.textContent = 'Timeline: ' + (timeline.scene || '') +
        ' · ' + fmt(total) + 's';

      for (const ev of events) {
        const row = document.createElement('div');
        row.className = 'row' + (ev.kind === 'next_section' ? ' section-row' : '');

        const label = document.createElement('div');
        label.className = 'label';
        label.title = (ev.note || '') + (ev.method ? ' @ ' + ev.method : '');
        label.textContent = ev.kind === 'next_section' ? ('§ ' + ev.label) : ev.label;
        label.addEventListener('click', () => {
          vscode.postMessage({ type: 'select', range: ev.range });
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

        row.appendChild(label);
        row.appendChild(track);
        row.appendChild(dur);
        rowsEl.appendChild(row);
      }
    }

    window.addEventListener('message', (event) => {
      const msg = event.data;
      if (msg && msg.type === 'timeline') {
        timeline = msg.timeline;
        rebuild();
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
