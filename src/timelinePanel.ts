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
  private lastScrubTime = 0;

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

  static highlightTime(filePath: string, time: number): void {
    const cur = TimelinePanel.current;
    if (!cur?.filePath || cur.filePath !== filePath) {
      return;
    }
    void cur.panel.webview.postMessage({ type: "highlightTime", time });
  }

  /** After Stage reloads layout, push a fresh scrub so overrides match new source. */
  static reemitScrubIfOpen(filePath: string): void {
    const cur = TimelinePanel.current;
    if (!cur?.filePath || cur.filePath !== filePath) {
      return;
    }
    const time = cur.lastScrubTime;
    const activeUntilLine = cur.activeUntilLineAt(time);
    StagePanel.scrub(filePath, time, activeUntilLine);
    TimelinePanel.highlightTime(filePath, time);
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
        await revealRange(this.filePath, range, {
          preserveFocus: true,
          preview: true,
        });
        const kind = String(rec.kind ?? "");
        const line = Number(rec.line ?? range.start_line ?? 0);
        const duration = Number(rec.duration ?? 0);
        if (
          PropertiesPanel.isOpenFor(this.filePath) &&
          (kind === "play" || kind === "wait" || kind === "next_section")
        ) {
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
      this.lastScrubTime = time;
      const activeUntilLine = this.activeUntilLineAt(time);
      StagePanel.scrub(this.filePath, time, activeUntilLine);
      TimelinePanel.highlightTime(this.filePath, time);
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
    #rows { flex: 1 1 auto; min-height: 0; padding: 12px; overflow: auto; box-sizing: border-box; }
    .scrub-row, .row {
      display: grid;
      grid-template-columns: minmax(96px, 140px) minmax(0, 1fr) 56px;
      gap: 8px;
      align-items: center;
      font-size: 12px;
      box-sizing: border-box;
    }
    .scrub-row {
      position: sticky; top: 0; z-index: 5;
      margin: 0 0 10px 0; padding: 8px 0;
      /* Fully opaque — rows scrolling underneath must not show through. */
      background: #1a1b1e;
      background-color: rgb(26, 27, 30);
      opacity: 1;
      border-bottom: 1px solid #333;
      box-shadow: 0 8px 0 0 #1a1b1e;
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
    <strong id="title">Timeline</strong>
    <span class="hint">Scrub syncs Stage · drag beats within a section · drag a § group to swap with a neighbor section · drag bar edge for duration</span>
  </div>
  <div id="rows"></div>
  <script>
    const vscode = acquireVsCodeApi();
    const rowsEl = document.getElementById('rows');
    const titleEl = document.getElementById('title');
    let scrubEl = null;
    let scrubLabel = null;
    let timeline = null;
    let pendingHighlightLine = null;
    let pendingHighlightTime = null;
    let scrubTime = 0;
    let reorderArmed = false;

    function fmt(n) {
      return (Math.round(n * 100) / 100).toString();
    }

    function isBeat(ev) {
      return ev.kind === 'play' || ev.kind === 'wait';
    }

    function eventSection(ev) {
      return (ev && ev.section != null) ? String(ev.section) : '';
    }

    function sectionGroups() {
      return Array.from(rowsEl.querySelectorAll(':scope > .section-group'));
    }

    /**
     * Beat reorder: live insertBefore among peers in one section group.
     * Section reorder: live swap of whole .section-group blocks (header + beats), neighbor-only.
     */
    function bindBeatSortable(row, opts) {
      row.classList.add('sortable');
      const grip = row.querySelector('.label') || row;
      let startY = 0;
      let fromPos = opts.pos;
      let active = false;
      let moved = false;

      const peerRows = () => {
        const group = row.closest('.section-group') || rowsEl;
        return Array.from(group.querySelectorAll('.row')).filter((el) => {
          return el.dataset.sortKind === 'beat' && el.dataset.section === opts.section;
        });
      };

      const onPointerMove = (e) => {
        if (!active) return;
        const dy = e.clientY - startY;
        if (!moved && Math.abs(dy) < 4) return;
        moved = true;
        reorderArmed = true;
        row.classList.add('sortable-dragging');
        row.style.transform = 'translateY(' + dy + 'px)';
        const peers = peerRows();
        const idx = peers.indexOf(row);
        if (idx < 0) return;
        const rect = row.getBoundingClientRect();
        const midY = rect.top + rect.height / 2;
        const parent = row.parentElement;
        for (let i = 0; i < peers.length; i++) {
          const other = peers[i];
          if (other === row) continue;
          const or = other.getBoundingClientRect();
          const oMid = or.top + or.height / 2;
          if (midY < oMid && i < idx) {
            parent.insertBefore(row, other);
            startY = e.clientY;
            row.style.transform = '';
            break;
          }
          if (midY > oMid && i > idx) {
            parent.insertBefore(other, row);
            startY = e.clientY;
            row.style.transform = '';
            break;
          }
        }
      };

      const endPointer = (e) => {
        if (!active) return;
        active = false;
        window.removeEventListener('pointermove', onPointerMove);
        window.removeEventListener('pointerup', endPointer);
        window.removeEventListener('pointercancel', endPointer);
        row.classList.remove('sortable-dragging');
        row.style.transform = '';
        try { row.releasePointerCapture(e.pointerId); } catch (_) {}
        if (!moved) {
          reorderArmed = false;
          return;
        }
        const peers = peerRows();
        const toPos = peers.indexOf(row);
        const list = opts.list;
        if (toPos < 0 || toPos === fromPos || !list[fromPos] || !list[toPos]) {
          reorderArmed = false;
          rebuild();
          return;
        }
        vscode.postMessage({
          type: 'reorder',
          kind: 'beat',
          lineA: list[fromPos].range && list[fromPos].range.start_line,
          lineB: list[toPos].range && list[toPos].range.start_line
        });
        setTimeout(() => { reorderArmed = false; }, 0);
      };

      grip.addEventListener('pointerdown', (e) => {
        if (e.button != null && e.button !== 0) return;
        if (e.target && e.target.closest && e.target.closest('.handle')) return;
        e.stopPropagation(); // don't start section-group drag
        active = true;
        moved = false;
        fromPos = opts.pos;
        startY = e.clientY;
        try { row.setPointerCapture(e.pointerId); } catch (_) {}
        window.addEventListener('pointermove', onPointerMove);
        window.addEventListener('pointerup', endPointer);
        window.addEventListener('pointercancel', endPointer);
      });
    }

    function bindSectionGroupSortable(group, opts) {
      group.classList.add('sortable');
      const grip = group.querySelector('.section-row .label') || group;
      let startY = 0;
      let fromPos = opts.pos;
      let active = false;
      let moved = false;

      const onPointerMove = (e) => {
        if (!active) return;
        const dy = e.clientY - startY;
        if (!moved && Math.abs(dy) < 4) return;
        moved = true;
        reorderArmed = true;
        group.classList.add('sortable-dragging');
        group.style.transform = 'translateY(' + dy + 'px)';

        const peers = sectionGroups();
        const idx = peers.indexOf(group);
        if (idx < 0) return;
        // Neighbor-only: swap with adjacent group when crossing its midline.
        const prev = peers[idx - 1];
        const next = peers[idx + 1];
        const midY = group.getBoundingClientRect().top + group.getBoundingClientRect().height / 2;
        if (prev) {
          const pr = prev.getBoundingClientRect();
          if (midY < pr.top + pr.height / 2) {
            rowsEl.insertBefore(group, prev);
            startY = e.clientY;
            group.style.transform = '';
            return;
          }
        }
        if (next) {
          const nr = next.getBoundingClientRect();
          if (midY > nr.top + nr.height / 2) {
            rowsEl.insertBefore(next, group);
            startY = e.clientY;
            group.style.transform = '';
          }
        }
      };

      const endPointer = (e) => {
        if (!active) return;
        active = false;
        window.removeEventListener('pointermove', onPointerMove);
        window.removeEventListener('pointerup', endPointer);
        window.removeEventListener('pointercancel', endPointer);
        group.classList.remove('sortable-dragging');
        group.style.transform = '';
        try { group.releasePointerCapture(e.pointerId); } catch (_) {}
        if (!moved) {
          reorderArmed = false;
          return;
        }
        const peers = sectionGroups();
        const toPos = peers.indexOf(group);
        const list = opts.list;
        if (toPos < 0 || toPos === fromPos || Math.abs(toPos - fromPos) !== 1
            || !list[fromPos] || !list[toPos]) {
          reorderArmed = false;
          rebuild();
          return;
        }
        vscode.postMessage({
          type: 'reorder',
          kind: 'section',
          lineA: list[fromPos].range && list[fromPos].range.start_line,
          lineB: list[toPos].range && list[toPos].range.start_line
        });
        setTimeout(() => { reorderArmed = false; }, 0);
      };

      grip.addEventListener('pointerdown', (e) => {
        if (e.button != null && e.button !== 0) return;
        if (e.target && e.target.closest && e.target.closest('.handle')) return;
        // Beats handle their own drag (stopPropagation). § label starts group drag.
        if (e.target && e.target.closest && e.target.closest('.row.beat')) return;
        active = true;
        moved = false;
        fromPos = opts.pos;
        startY = e.clientY;
        try { group.setPointerCapture(e.pointerId); } catch (_) {}
        window.addEventListener('pointermove', onPointerMove);
        window.addEventListener('pointerup', endPointer);
        window.addEventListener('pointercancel', endPointer);
      });
    }

    function rebuild() {
      rowsEl.innerHTML = '';
      if (!timeline) return;
      const events = timeline.events || [];
      const total = Math.max(timeline.total_duration || 1, 0.01);
      titleEl.textContent = 'Timeline: ' + (timeline.scene || '') +
        ' · ' + fmt(total) + 's';

      const scrubRow = document.createElement('div');
      scrubRow.className = 'scrub-row';
      scrubRow.innerHTML =
        '<div class="scrub-gutter">Scrub</div>' +
        '<div class="scrub-track"><input id="scrub" type="range" min="0" max="1" step="0.01" value="0" /></div>' +
        '<div id="scrubLabel">0s</div>';
      rowsEl.appendChild(scrubRow);
      scrubEl = document.getElementById('scrub');
      scrubLabel = document.getElementById('scrubLabel');
      scrubEl.max = String(total);
      scrubEl.step = String(Math.max(0.01, total / 200));
      const t0 = Math.max(0, Math.min(total, scrubTime || 0));
      scrubEl.value = String(t0);
      scrubLabel.textContent = fmt(t0) + 's';
      scrubEl.addEventListener('input', () => {
        const time = Number(scrubEl.value) || 0;
        scrubTime = time;
        scrubLabel.textContent = fmt(time) + 's';
        vscode.postMessage({ type: 'scrub', time: time });
      });
      // Keep Stage scrub overrides in sync after Timeline rebuild / source patch.
      vscode.postMessage({ type: 'scrub', time: t0 });

      // Group events into section blocks (matches propose_section_reorder).
      const groups = [];
      let cur = { section: '', sectionEv: null, beats: [] };
      events.forEach((ev, i) => {
        if (ev.kind === 'next_section') {
          if (cur.sectionEv || cur.beats.length) groups.push(cur);
          cur = { section: eventSection(ev) || String(ev.label || ''), sectionEv: ev, beats: [] };
        } else if (isBeat(ev)) {
          cur.beats.push({ ev: ev, index: i });
        }
      });
      if (cur.sectionEv || cur.beats.length) groups.push(cur);

      const sectionMarkers = groups
        .filter((g) => g.sectionEv)
        .map((g) => g.sectionEv);

      function buildRow(ev, eventIndex) {
        const row = document.createElement('div');
        row.className = 'row' + (ev.kind === 'next_section' ? ' section-row' : '') +
          (isBeat(ev) ? ' beat' : '');
        row.dataset.startLine = String(ev.range && ev.range.start_line || 0);
        row.dataset.endLine = String(ev.range && ev.range.end_line || 0);
        row.dataset.method = ev.method || '';
        row.dataset.eventIndex = String(eventIndex);
        row.dataset.eventId = String(ev.id || eventIndex);
        row.dataset.kind = ev.kind || '';
        row.dataset.section = eventSection(ev);
        row.dataset.start = String(ev.start || 0);
        row.dataset.duration = String(ev.duration || 0);

        const label = document.createElement('div');
        label.className = 'label';
        const dragHint = isBeat(ev)
          ? ' · drag to reorder within this section'
          : (ev.kind === 'next_section'
            ? ' · drag this section group to swap with a neighbor'
            : '');
        label.title = (ev.note || '') + (ev.method ? ' @ ' + ev.method : '') + dragHint;
        label.textContent = ev.kind === 'next_section' ? ('§ ' + ev.label) : ev.label;
        label.addEventListener('click', () => {
          if (reorderArmed) return;
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
        return row;
      }

      groups.forEach((g) => {
        const groupEl = document.createElement('div');
        groupEl.className = 'section-group';
        groupEl.dataset.section = g.section;

        if (g.sectionEv) {
          const secIdx = events.indexOf(g.sectionEv);
          const secRow = buildRow(g.sectionEv, secIdx >= 0 ? secIdx : 0);
          secRow.dataset.sortKind = 'section';
          groupEl.appendChild(secRow);
          const pos = sectionMarkers.indexOf(g.sectionEv);
          if (pos >= 0) {
            bindSectionGroupSortable(groupEl, {
              pos: pos,
              list: sectionMarkers
            });
          }
        }

        const beatList = g.beats.map((b) => b.ev);
        g.beats.forEach((b, beatPos) => {
          const beatRow = buildRow(b.ev, b.index);
          beatRow.dataset.sortKind = 'beat';
          bindBeatSortable(beatRow, {
            pos: beatPos,
            section: eventSection(b.ev),
            list: beatList
          });
          groupEl.appendChild(beatRow);
        });

        rowsEl.appendChild(groupEl);
      });
      if (pendingHighlightTime != null) {
        highlightTime(pendingHighlightTime);
      } else if (pendingHighlightLine != null) {
        highlightLine(pendingHighlightLine);
      }
    }

    function clearActive() {
      rowsEl.querySelectorAll('.row.active').forEach((row) => {
        row.classList.remove('active');
      });
    }

    function setActiveRow(row) {
      clearActive();
      if (!row) return;
      row.classList.add('active');
      row.scrollIntoView({ block: 'nearest' });
    }

    function highlightLine(line) {
      pendingHighlightLine = line;
      pendingHighlightTime = null;
      const rows = Array.from(rowsEl.querySelectorAll('.row'));
      let best = null;
      let bestScore = Infinity;
      rows.forEach((row) => {
        const start = Number(row.dataset.startLine || 0);
        const end = Number(row.dataset.endLine || start);
        const kind = row.dataset.kind || '';
        if (!start && !end) return;
        let dist;
        if (line >= start && line <= end) {
          dist = 0;
        } else {
          dist = Math.min(Math.abs(line - start), Math.abs(line - end));
          if (dist > 3) return;
        }
        // Prefer play/wait over section markers at equal distance.
        const kindPenalty = (kind === 'play' || kind === 'wait') ? 0 : 0.4;
        const score = dist + kindPenalty;
        if (score < bestScore) {
          best = row;
          bestScore = score;
        }
      });
      setActiveRow(best);
    }

    function highlightTime(time) {
      pendingHighlightTime = time;
      const rows = Array.from(rowsEl.querySelectorAll('.row'));
      let covering = null;
      let lastStarted = null;
      rows.forEach((row) => {
        const kind = row.dataset.kind || '';
        if (kind === 'next_section') return;
        const start = Number(row.dataset.start || 0);
        const dur = Number(row.dataset.duration || 0);
        const end = start + dur;
        if (time >= start && time <= end + 1e-9) covering = row;
        if (time >= start) lastStarted = row;
      });
      setActiveRow(covering || lastStarted);
    }

    window.addEventListener('message', (event) => {
      const msg = event.data;
      if (msg && msg.type === 'timeline') {
        timeline = msg.timeline;
        rebuild();
      } else if (msg && msg.type === 'highlightLine') {
        highlightLine(msg.line);
      } else if (msg && msg.type === 'highlightTime') {
        highlightTime(Number(msg.time) || 0);
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
