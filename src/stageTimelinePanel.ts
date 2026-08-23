import * as fs from "fs";
import * as path from "path";
import * as vscode from "vscode";
import { revealRange } from "./outlineTree";
import { ProposedPatchProvider, confirmAndApplyPatch } from "./patchConfirm";
import {
  SceneTimeline,
  SidecarClient,
  SourceRange,
  TimelineEvent,
} from "./sidecar";

/** Writable cache for Manim stills — must be listed in webview localResourceRoots. */
function snapshotCacheDir(context: vscode.ExtensionContext): string {
  const dir = path.join(context.globalStorageUri.fsPath, "snapshots");
  fs.mkdirSync(dir, { recursive: true });
  return dir;
}

/**
 * Unified Stage + Timeline webview — Manim still on top, beat strip beneath.
 * Opened only via `manimDock.openStageTimeline` (one command, one icon).
 */
export class StageTimelinePanel {
  public static readonly viewType = "manimDock.stageTimeline";
  private static current: StageTimelinePanel | undefined;

  private readonly panel: vscode.WebviewPanel;
  private disposables: vscode.Disposable[] = [];
  private filePath: string | undefined;
  private sceneName: string | undefined;
  private timeline: SceneTimeline | undefined;
  private lastScrubTime = 0;
  /** Debounced Manim still capture (Phase 12). */
  private snapshotTimer: ReturnType<typeof setTimeout> | undefined;
  private snapshotGeneration = 0;
  private snapshotAvailable: boolean | undefined;
  private snapshotFailNotified = false;

  private webviewReady = false;

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

  static ensureProposedProvider(context: vscode.ExtensionContext): void {
    ProposedPatchProvider.ensure(context);
  }

  static async open(
    context: vscode.ExtensionContext,
    sidecar: SidecarClient,
    output: vscode.OutputChannel,
    filePath: string,
    sceneName: string
  ): Promise<StageTimelinePanel> {
    StageTimelinePanel.ensureProposedProvider(context);
    const column = vscode.ViewColumn.Beside;

    if (StageTimelinePanel.current) {
      StageTimelinePanel.current.panel.reveal(column, false);
      await StageTimelinePanel.current.load(filePath, sceneName);
      return StageTimelinePanel.current;
    }

    const mediaRoot = vscode.Uri.file(path.join(context.extensionPath, "media"));
    const snapRoot = vscode.Uri.file(snapshotCacheDir(context));
    const panel = vscode.window.createWebviewPanel(
      StageTimelinePanel.viewType,
      `Stage & Timeline: ${sceneName}`,
      column,
      {
        enableScripts: true,
        retainContextWhenHidden: true,
        localResourceRoots: [mediaRoot, snapRoot],
      }
    );
    panel.reveal(column, false);
    StageTimelinePanel.current = new StageTimelinePanel(
      panel,
      context,
      sidecar,
      output
    );
    await StageTimelinePanel.current.load(filePath, sceneName);
    return StageTimelinePanel.current;
  }

  async load(filePath: string, sceneName: string): Promise<void> {
    const sceneChanged =
      this.filePath !== filePath || this.sceneName !== sceneName;
    this.filePath = filePath;
    this.sceneName = sceneName;
    this.panel.title = `Stage & Timeline: ${sceneName}`;
    if (sceneChanged) {
      this.lastScrubTime = 0;
    }
    // Do not reset HTML on every open. Re-assigning identical HTML often does
    // not remount the webview script, so clearing webviewReady would leave the
    // panel stuck until close/reopen (SV-013).
    if (!this.webviewReady) {
      this.panel.webview.html = this.getHtml();
    }
    await this.refresh();
    // Outline / editor cursor → scrub + still at that line (reuse & first open).
    this.syncScrubToEditor();
  }

  static refreshIfOpen(filePath?: string): void {
    const cur = StageTimelinePanel.current;
    if (!cur?.filePath) {
      return;
    }
    if (filePath && cur.filePath !== filePath) {
      return;
    }
    void cur.refresh();
  }

  static highlightLine(filePath: string, line: number): void {
    const cur = StageTimelinePanel.current;
    if (!cur?.filePath || cur.filePath !== filePath || line < 1) {
      return;
    }
    cur.scrubToSourceLine(line);
  }

  async refresh(): Promise<void> {
    if (!this.filePath || !this.sceneName) {
      return;
    }
    this.postStatus("Loading Stage…", "Loading Timeline…");
    try {
      const doc = await vscode.workspace.openTextDocument(this.filePath);
      const source = doc.getText();
      this.timeline = await this.sidecar.timeline(
        this.filePath,
        this.sceneName,
        source
      );
      this.snapshotAvailable = undefined;
      this.snapshotGeneration += 1;
      if (this.snapshotTimer) {
        clearTimeout(this.snapshotTimer);
        this.snapshotTimer = undefined;
      }
      this.pushPayload();
      if (this.timeline.errors.length) {
        this.output.appendLine(`[timeline] ${this.timeline.errors.join("; ")}`);
      }
      await this.scrubAsync(this.lastScrubTime);
    } catch (err) {
      const text = String(err);
      this.output.appendLine(`[stage-timeline] ${text}`);
      this.postStatus(`Stage failed: ${text}`, `Timeline failed: ${text}`);
      void vscode.window.showErrorMessage(
        `Manim Dock Stage & Timeline failed: ${text}`
      );
    }
  }

  /** Send timeline only after the webview has posted `ready`. */
  private pushPayload(): void {
    if (!this.webviewReady) {
      return;
    }
    if (!this.timeline) {
      return;
    }
    void this.panel.webview.postMessage({
      type: "payload",
      timeline: this.timeline,
    });
  }

  private postStatus(stage: string, timeline: string): void {
    if (!this.webviewReady) {
      return;
    }
    void this.panel.webview.postMessage({
      type: "status",
      stage,
      timeline,
    });
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
    return pick.range.end_line || pick.range.start_line;
  }

  private async scrubAsync(time: number): Promise<void> {
    if (!this.filePath || !this.sceneName) {
      return;
    }
    this.lastScrubTime = time;
    // No beat yet (t=0 before first play) → line 0.
    const activeUntilLine = this.activeUntilLineAt(time) ?? 0;
    void this.panel.webview.postMessage({
      type: "scrub",
      time,
      activeUntilLine,
    });
    this.scheduleSnapshot(activeUntilLine);
  }

  /** Prefer an editor already showing this file (Outline reveal). */
  private syncScrubToEditor(): boolean {
    if (!this.filePath) {
      return false;
    }
    let editor: vscode.TextEditor | undefined;
    for (const ed of vscode.window.visibleTextEditors) {
      if (ed.document.uri.fsPath === this.filePath) {
        editor = ed;
        break;
      }
    }
    if (!editor && vscode.window.activeTextEditor?.document.uri.fsPath === this.filePath) {
      editor = vscode.window.activeTextEditor;
    }
    if (!editor) {
      return false;
    }
    this.scrubToSourceLine(editor.selection.active.line + 1);
    return true;
  }

  /**
   * Outline section / editor caret → highlight Timeline row, move scrub, capture still.
   * Snapshot stays debounced via scheduleSnapshot.
   */
  private scrubToSourceLine(line: number): void {
    if (!this.filePath || !this.sceneName || line < 1) {
      return;
    }
    void this.panel.webview.postMessage({ type: "highlightLine", line });
    const time = this.timeAtSourceLine(line);
    if (time != null) {
      this.lastScrubTime = time;
    }
    const scrubTime = this.lastScrubTime;
    void this.panel.webview.postMessage({
      type: "scrub",
      time: scrubTime,
      activeUntilLine: line,
    });
    this.scheduleSnapshot(line);
  }

  /** Timeline time for a 1-based source line (section / play / wait). */
  private timeAtSourceLine(line: number): number | undefined {
    const events = this.timeline?.events ?? [];
    let best: TimelineEvent | undefined;
    let bestScore = Infinity;
    for (const ev of events) {
      const startLine = ev.range?.start_line ?? 0;
      const endLine = ev.range?.end_line ?? startLine;
      if (!startLine && !endLine) {
        continue;
      }
      let dist: number;
      if (line >= startLine && line <= endLine) {
        dist = 0;
      } else {
        dist = Math.min(Math.abs(line - startLine), Math.abs(line - endLine));
        if (dist > 8) {
          continue;
        }
      }
      // Prefer section markers and beats over other kinds when tied.
      const kindBonus =
        ev.kind === "next_section" ? 0 : ev.kind === "play" || ev.kind === "wait" ? 0.05 : 0.2;
      const score = dist + kindBonus;
      if (score < bestScore) {
        bestScore = score;
        best = ev;
      }
    }
    if (!best) {
      return undefined;
    }
    return best.start ?? 0;
  }

  private scheduleSnapshot(activeUntilLine: number): void {
    if (this.snapshotAvailable === false) {
      void this.panel.webview.postMessage({
        type: "snapshot",
        ok: false,
        activeUntilLine,
        error:
          "Manim still disabled — interpreter has no manim (set manimDock.pythonPath to the repo .venv)",
      });
      return;
    }
    if (this.snapshotTimer) {
      clearTimeout(this.snapshotTimer);
    }
    const generation = ++this.snapshotGeneration;
    void this.panel.webview.postMessage({
      type: "snapshot",
      ok: false,
      pending: true,
      activeUntilLine,
    });
    this.snapshotTimer = setTimeout(() => {
      this.snapshotTimer = undefined;
      void this.fetchSnapshot(generation, activeUntilLine);
    }, 700);
  }

  private notifySnapshotFail(err: string): void {
    this.output.appendLine(`[stage-snapshot] FAIL ${err}`);
    if (!this.snapshotFailNotified) {
      this.snapshotFailNotified = true;
      void vscode.window.showWarningMessage(
        `Manim Dock Stage still failed: ${err.slice(0, 180)}`
      );
    }
  }

  private async fetchSnapshot(
    generation: number,
    activeUntilLine: number
  ): Promise<void> {
    if (!this.filePath || !this.sceneName) {
      return;
    }
    if (generation !== this.snapshotGeneration) {
      this.output.appendLine(
        `[stage-snapshot] skip stale gen=${generation} current=${this.snapshotGeneration}`
      );
      return;
    }
    const cacheDir = snapshotCacheDir(this.context);
    try {
      const doc = await vscode.workspace.openTextDocument(this.filePath);
      this.output.appendLine(
        `[stage-snapshot] capturing line=${activeUntilLine} scene=${this.sceneName} cache=${cacheDir}`
      );
      const result = await this.sidecar.snapshotAtLine(
        this.filePath,
        this.sceneName,
        activeUntilLine,
        doc.getText(),
        "l",
        90,
        cacheDir
      );
      if (generation !== this.snapshotGeneration) {
        this.output.appendLine(
          `[stage-snapshot] drop late result gen=${generation}`
        );
        return;
      }
      if (!result.ok || !result.png_path) {
        const err = result.error || "snapshot returned no PNG";
        if (
          /manim executable not found|No module named ['\"]manim['\"]/i.test(err)
        ) {
          this.snapshotAvailable = false;
        }
        void this.panel.webview.postMessage({
          type: "snapshot",
          ok: false,
          activeUntilLine,
          error: err,
        });
        this.notifySnapshotFail(err);
        if (result.log_tail) {
          this.output.appendLine(result.log_tail.slice(-1200));
        }
        return;
      }
      this.snapshotAvailable = true;
      const imageUri = String(
        this.panel.webview.asWebviewUri(vscode.Uri.file(result.png_path))
      );
      if (generation !== this.snapshotGeneration) {
        return;
      }
      void this.panel.webview.postMessage({
        type: "snapshot",
        ok: true,
        activeUntilLine,
        imageUri,
        width: result.width,
        height: result.height,
        cached: result.cached,
      });
      this.output.appendLine(
        `[stage-snapshot] OK cached=${result.cached} ${result.png_path}`
      );
    } catch (err) {
      if (generation !== this.snapshotGeneration) {
        return;
      }
      const message = String(err);
      if (
        /manim executable not found|No module named ['\"]manim['\"]/i.test(
          message
        )
      ) {
        this.snapshotAvailable = false;
      }
      void this.panel.webview.postMessage({
        type: "snapshot",
        ok: false,
        activeUntilLine,
        error: message,
      });
      this.notifySnapshotFail(message);
    }
  }

  private async onMessage(msg: unknown): Promise<void> {
    if (!msg || typeof msg !== "object") {
      return;
    }
    const rec = msg as Record<string, unknown>;
    const type = rec.type;

    if (type === "ready") {
      this.webviewReady = true;
      this.output.appendLine("[stage-timeline] webview ready");
      this.pushPayload();
      // Prefer editor/Outline caret; otherwise restore last scrub (messages may
      // have been sent before the webview could receive them).
      if (!this.syncScrubToEditor()) {
        void this.scrubAsync(this.lastScrubTime);
      }
      return;
    }

    if (type === "jumpScrubLine") {
      const line = Number(rec.line ?? 0);
      if (this.filePath && line > 0) {
        await revealRange(
          this.filePath,
          { start_line: line, end_line: line },
          { preserveFocus: false, preview: true }
        );
      }
      return;
    }

    if (type === "selectBeat") {
      const range = rec.range as SourceRange | undefined;
      if (range && this.filePath) {
        await revealRange(this.filePath, range, {
          preserveFocus: false,
          preview: true,
        });
      }
      return;
    }

    if (type === "scrub") {
      const time = Number(rec.time ?? 0);
      if (!Number.isFinite(time)) {
        return;
      }
      await this.scrubAsync(time);
      return;
    }

    if (type === "reorder") {
      await this.handleReorder(rec);
      return;
    }

    if (type === "resize") {
      await this.handleResize(rec);
      return;
    }
  }

  private async handleReorder(rec: Record<string, unknown>): Promise<void> {
    if (!this.filePath) {
      return;
    }
    const lineA = Number(rec.lineA ?? 0);
    const lineB = Number(rec.lineB ?? 0);
    const kind = String(rec.kind ?? "beat");
    if (!lineA || !lineB || lineA === lineB) {
      return;
    }
    if (kind !== "beat" && kind !== "section") {
      return;
    }

    const doc = await vscode.workspace.openTextDocument(this.filePath);
    let proposal;
    try {
      proposal =
        kind === "section"
          ? await this.sidecar.proposeSectionReorder(
              this.filePath,
              lineA,
              lineB,
              doc.getText()
            )
          : await this.sidecar.proposeReorder(
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
    const scriptUri = this.panel.webview
      .asWebviewUri(
        vscode.Uri.file(
          path.join(this.context.extensionPath, "media", "stageTimeline.js")
        )
      )
      .toString();
    const csp = [
      "default-src 'none'",
      `script-src ${this.panel.webview.cspSource}`,
      "style-src 'unsafe-inline'",
      `img-src ${this.panel.webview.cspSource}`,
    ].join("; ");

    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta http-equiv="Content-Security-Policy" content="${csp}" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Manim Dock Stage & Timeline</title>
  <style>
    html, body { margin: 0; height: 100%; width: 100%; background: #1a1b1e; color: #c8c8c8;
      font-family: var(--vscode-font-family, system-ui, sans-serif); overflow: hidden;
      display: flex; flex-direction: column; box-sizing: border-box; }
    body { min-height: 100vh; }
    .bar { flex: 0 0 auto; display: flex; gap: 12px; align-items: center; padding: 8px 12px;
      font-size: 12px; border-bottom: 1px solid #333; flex-wrap: wrap; }
    .bar strong { color: #eee; font-weight: 600; }
    #stage-section { flex: 1 1 55%; min-height: 180px; display: flex; flex-direction: column; min-width: 0; }
    #stage-host {
      flex: 1 1 auto; width: 100%; min-height: 160px; position: relative; overflow: hidden;
      background: #111214; container-type: size; display: grid; place-items: center; padding: 12px;
      box-sizing: border-box;
    }
    #stage-frame {
      position: relative;
      aspect-ratio: 16 / 9;
      width: min(100cqw - 24px, (100cqh - 24px) * 16 / 9);
      max-width: 100%;
      max-height: 100%;
      background: #0d0e10;
      border: 1px solid #5a5a5a;
      box-sizing: border-box;
      cursor: pointer;
    }
    #stage-still {
      display: block; width: 100%; height: 100%; object-fit: contain;
      background: #111214; transition: opacity 0.15s ease;
    }
    #stage-still.pending { opacity: 0.45; }
    #stage-still[hidden] { display: none; }
    #stage-host .placeholder {
      position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
      padding: 16px; text-align: center; color: #8a8a8a; font-size: 12px; pointer-events: none;
    }
    #stage-host .placeholder[hidden] { display: none; }
    #timeline-section { flex: 1 1 40%; min-height: 180px; max-height: none; display: flex; flex-direction: column;
      border-top: 1px solid #333; min-width: 0; overflow: hidden; }
    #scrub-host {
      flex: 0 0 auto; padding: 8px 12px 6px; box-sizing: border-box;
      background: #1a1b1e; border-bottom: 1px solid #333; z-index: 3;
      position: relative; isolation: isolate;
    }
    #rows { flex: 1 1 auto; min-height: 80px; padding: 8px 12px 12px; overflow: auto; box-sizing: border-box;
      background: #1a1b1e; position: relative; z-index: 0; }
    #rows .placeholder { color: #8a8a8a; font-size: 12px; padding: 12px 0; }
    .scrub-row, .row {
      display: grid;
      grid-template-columns: minmax(96px, 160px) minmax(0, 1fr) 56px;
      gap: 8px;
      align-items: center;
      font-size: 12px;
      box-sizing: border-box;
    }
    .scrub-row {
      margin: 0; padding: 0;
      background: #1a1b1e;
    }
    .scrub-row .scrub-gutter { color: #c8c8c8; opacity: 1; }
    .scrub-row .scrub-track { min-width: 0; }
    .scrub-row input[type="range"] { width: 100%; margin: 0; display: block; }
    #scrubLabel { text-align: right; font-variant-numeric: tabular-nums; color: #c8c8c8; opacity: 1; }
    .row { margin-bottom: 6px; transition: transform 0.15s ease, box-shadow 0.15s ease; }
    .row.sortable { cursor: grab; touch-action: none; }
    .row.sortable:active { cursor: grabbing; }
    .row.sortable-dragging {
      opacity: 0.92; z-index: 4; position: relative;
      box-shadow: 0 6px 16px rgba(0,0,0,0.45); background: #22232a;
      transition: none;
    }
    .row.sortable-ghost { opacity: 0.35; }
    .section-group {
      margin: 0 0 10px 0; padding: 4px 4px 2px 4px;
      border-left: 2px solid #444; border-radius: 2px;
      transition: transform 0.15s ease, box-shadow 0.15s ease, opacity 0.15s ease;
    }
    .section-group.sortable { cursor: grab; touch-action: none; }
    .section-group.sortable-dragging {
      opacity: 0.95; z-index: 4; position: relative;
      box-shadow: 0 8px 20px rgba(0,0,0,0.5); background: #1e1f26;
      transition: none;
    }
    .section-group.sortable-ghost { opacity: 0.4; }
    .section-group .row { margin-bottom: 4px; }
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
    .row.active { outline: 1px solid #ffe08a; outline-offset: 2px; border-radius: 2px; }
    .row.active .label { color: #ffe08a; }
  </style>
</head>
<body>
  <div class="bar">
    <strong id="title">Stage & Timeline</strong>
  </div>
  <div id="stage-section">
    <div id="stage-host">
      <div id="stage-frame">
        <img id="stage-still" alt="Manim still" hidden draggable="false" />
        <div class="placeholder" id="stagePlaceholder">Starting…</div>
      </div>
    </div>
  </div>
  <div id="timeline-section">
    <div id="scrub-host"></div>
    <div id="rows"><div class="placeholder" id="rowsPlaceholder">Starting…</div></div>
  </div>
  <script src="${scriptUri}"></script>
</body>
</html>`;
  }

  dispose(): void {
    // Closing the unified panel clears scrub state with the webview (SV-008).
    StageTimelinePanel.current = undefined;
    this.timeline = undefined;
    this.webviewReady = false;
    this.lastScrubTime = 0;
    this.snapshotAvailable = undefined;
    this.snapshotGeneration += 1;
    if (this.snapshotTimer) {
      clearTimeout(this.snapshotTimer);
      this.snapshotTimer = undefined;
    }
    while (this.disposables.length) {
      this.disposables.pop()?.dispose();
    }
  }
}
