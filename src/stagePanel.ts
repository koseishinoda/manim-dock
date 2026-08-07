import * as path from "path";
import * as vscode from "vscode";
import { applyAlignPatches } from "./alignApply";
import { revealRange } from "./outlineTree";
import { ProposedPatchProvider, confirmAndApplyPatch } from "./patchConfirm";
import { PropertiesPanel } from "./propertiesPanel";
import { LayoutItem, SceneLayout, ScrubPosition, SidecarClient } from "./sidecar";
import { TimelinePanel } from "./timelinePanel";

/**
 * Konva Stage webview — heuristic layout proxies; drag → confirm-diff → apply.
 */
export class StagePanel {
  public static readonly viewType = "manimDock.stage";
  private static current: StagePanel | undefined;

  private readonly panel: vscode.WebviewPanel;
  private disposables: vscode.Disposable[] = [];
  private filePath: string | undefined;
  private sceneName: string | undefined;
  private layout: SceneLayout | undefined;
  /** After scrub_layout fails once, skip further calls until refresh. */
  private scrubLayoutAvailable: boolean | undefined;

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
  ): Promise<StagePanel> {
    StagePanel.ensureProposedProvider(context);
    const column = vscode.ViewColumn.Beside;

    if (StagePanel.current) {
      StagePanel.current.panel.reveal(column);
      await StagePanel.current.load(filePath, sceneName);
      return StagePanel.current;
    }

    const mediaRoot = vscode.Uri.file(path.join(context.extensionPath, "media"));
    const panel = vscode.window.createWebviewPanel(
      StagePanel.viewType,
      `Stage: ${sceneName}`,
      column,
      {
        enableScripts: true,
        retainContextWhenHidden: true,
        localResourceRoots: [mediaRoot],
      }
    );
    StagePanel.current = new StagePanel(panel, context, sidecar, output);
    await StagePanel.current.load(filePath, sceneName);
    return StagePanel.current;
  }

  async load(filePath: string, sceneName: string): Promise<void> {
    this.filePath = filePath;
    this.sceneName = sceneName;
    this.panel.title = `Stage: ${sceneName}`;
    await this.refresh();
  }

  static refreshIfOpen(filePath?: string): void {
    const cur = StagePanel.current;
    if (!cur?.filePath) {
      return;
    }
    if (filePath && cur.filePath !== filePath) {
      return;
    }
    void cur.refresh();
  }

  static highlightLine(filePath: string, line: number): void {
    const cur = StagePanel.current;
    if (!cur?.filePath || cur.filePath !== filePath) {
      return;
    }
    void cur.panel.webview.postMessage({ type: "highlightLine", line });
  }

  /** Scrub approximate visibility / positions for Timeline playhead. */
  static scrub(
    filePath: string,
    time: number,
    activeUntilLine?: number
  ): void {
    const cur = StagePanel.current;
    if (!cur?.filePath || cur.filePath !== filePath) {
      return;
    }
    void cur.scrubAsync(time, activeUntilLine);
  }

  private async scrubAsync(
    time: number,
    activeUntilLine?: number
  ): Promise<void> {
    let positions: Record<string, ScrubPosition> | undefined;
    if (
      this.scrubLayoutAvailable !== false &&
      typeof activeUntilLine === "number" &&
      this.filePath &&
      this.sceneName
    ) {
      try {
        const doc = await vscode.workspace.openTextDocument(this.filePath);
        positions = await this.sidecar.scrubLayout(
          this.filePath,
          this.sceneName,
          activeUntilLine,
          doc.getText()
        );
        this.scrubLayoutAvailable = true;
      } catch {
        // Sidecar scrub optional — fall back to opacity-by-line in the webview.
        this.scrubLayoutAvailable = false;
        positions = undefined;
      }
    }
    void this.panel.webview.postMessage({
      type: "scrub",
      time,
      activeUntilLine,
      positions,
    });
  }

  async refresh(): Promise<void> {
    if (!this.filePath || !this.sceneName) {
      return;
    }
    try {
      const doc = await vscode.workspace.openTextDocument(this.filePath);
      this.layout = await this.sidecar.layout(
        this.filePath,
        this.sceneName,
        doc.getText()
      );
      this.scrubLayoutAvailable = undefined;
      void this.panel.webview.postMessage({ type: "layout", layout: this.layout });
      if (this.layout.errors.length) {
        this.output.appendLine(`[stage] ${this.layout.errors.join("; ")}`);
      }
      // Recompute scrub from current Timeline playhead against the new source.
      TimelinePanel.reemitScrubIfOpen(this.filePath);
    } catch (err) {
      this.output.appendLine(`[stage] ${String(err)}`);
      void vscode.window.showErrorMessage(`Manim Dock Stage failed: ${String(err)}`);
    }
  }

  private static hasBuffHint(item: LayoutItem): boolean {
    return item.layout_calls.some(
      (c) =>
        c.kind === "arrange" ||
        c.kind === "next_to" ||
        /buff\s*=/.test(c.code)
    );
  }

  private static hasFontHint(item: LayoutItem): boolean {
    const kind = (item.mobject_kind || "").toLowerCase();
    if (
      kind === "text" ||
      kind === "markuptext" ||
      kind === "mathtex" ||
      kind === "tex"
    ) {
      return true;
    }
    return item.layout_calls.some((c) => /font_size\s*=/.test(c.code));
  }

  private static hasLagHint(item: LayoutItem): boolean {
    return item.layout_calls.some(
      (c) =>
        /lag_ratio\s*=/.test(c.code) ||
        /LaggedStart/.test(c.code) ||
        /AnimationGroup/.test(c.code)
    );
  }

  private static isOpaque(item: LayoutItem): boolean {
    return (
      item.mobject_kind === "unknown" ||
      (!item.editable && item.mobject_kind === "unknown")
    );
  }

  /** Sync selection into Properties only if the user already opened it. */
  private syncSelectionToPropertiesIfOpen(
    primary: LayoutItem,
    selectedNames: string[]
  ): void {
    if (!this.filePath || !PropertiesPanel.isOpenFor(this.filePath)) {
      return;
    }
    PropertiesPanel.setSelection(this.filePath, {
      kind: "mobject",
      name: primary.name,
      selectedNames,
      anchorLine: primary.range.start_line,
      hasBuffHint: StagePanel.hasBuffHint(primary),
      hasFontHint: StagePanel.hasFontHint(primary),
      hasLagHint: StagePanel.hasLagHint(primary),
      isOpaque: StagePanel.isOpaque(primary),
    });
  }

  private async onMessage(msg: unknown): Promise<void> {
    if (!msg || typeof msg !== "object") {
      return;
    }
    const rec = msg as Record<string, unknown>;
    const type = rec.type;

    if (type === "ready") {
      if (this.layout) {
        void this.panel.webview.postMessage({ type: "layout", layout: this.layout });
      }
      return;
    }

    if (type === "select") {
      // Stage-owned selection only — no editor jump / Properties auto-open.
      const name = String(rec.name ?? "");
      const selectedNames = Array.isArray(rec.selectedNames)
        ? (rec.selectedNames as unknown[])
            .map((n) => String(n))
            .filter(Boolean)
        : name
          ? [name]
          : [];
      const primaryName =
        typeof rec.primary === "string" && rec.primary
          ? rec.primary
          : selectedNames[selectedNames.length - 1] || name;
      const item = this.layout?.items.find((i) => i.name === primaryName);
      if (item && this.filePath) {
        // Keep Timeline in sync with the chip's source range (no editor steal).
        TimelinePanel.highlightLine(this.filePath, item.range.start_line);
        this.syncSelectionToPropertiesIfOpen(
          item,
          selectedNames.length ? selectedNames : [item.name]
        );
      }
      return;
    }

    if (type === "jump") {
      const name = String(rec.name ?? "");
      const item = this.layout?.items.find((i) => i.name === name);
      if (item && this.filePath) {
        await revealRange(this.filePath, item.range, {
          preserveFocus: true,
          preview: true,
        });
      }
      return;
    }

    if (type === "align") {
      if (!this.filePath || !this.sceneName) {
        return;
      }
      const mode = String(rec.mode ?? "");
      const names = Array.isArray(rec.selectedNames)
        ? (rec.selectedNames as unknown[]).map((n) => String(n)).filter(Boolean)
        : [];
      this.output.appendLine(
        `[stage] align ${mode} names=[${names.join(", ")}]`
      );
      if (names.length < 2) {
        void vscode.window.showWarningMessage(
          "Manim Dock: Shift/Ctrl-click at least two Stage chips, then Align."
        );
        return;
      }
      const applied = await applyAlignPatches(
        this.context,
        this.sidecar,
        this.output,
        this.filePath,
        this.sceneName,
        names,
        mode,
        "stage"
      );
      if (applied) {
        await this.refresh();
      }
      return;
    }

    if (type === "dragEnd") {
      await this.handleDragEnd(rec);
    }
  }

  private async handleDragEnd(rec: Record<string, unknown>): Promise<void> {
    if (!this.filePath || !this.sceneName) {
      return;
    }
    const name = String(rec.name ?? "");
    const dx = Number(rec.dx ?? 0);
    const dy = Number(rec.dy ?? 0);
    const anchorLine =
      typeof rec.anchorLine === "number" ? rec.anchorLine : undefined;

    if (!name || (Math.abs(dx) < 1e-6 && Math.abs(dy) < 1e-6)) {
      return;
    }

    const doc = await vscode.workspace.openTextDocument(this.filePath);
    const source = doc.getText();

    let proposal;
    try {
      proposal = await this.sidecar.proposeShift(
        this.filePath,
        name,
        dx,
        dy,
        source,
        anchorLine
      );
    } catch (err) {
      void vscode.window.showErrorMessage(`Manim Dock patch failed: ${String(err)}`);
      await this.refresh();
      return;
    }

    if (!proposal.ok) {
      void vscode.window.showWarningMessage(
        `Manim Dock: could not patch ${name}: ${proposal.error ?? "unknown"}`
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
      "stage"
    );
    await this.refresh();
  }

  private getHtml(): string {
    const konvaUri = this.panel.webview.asWebviewUri(
      vscode.Uri.file(path.join(this.context.extensionPath, "media", "konva.min.js"))
    );
    const csp = [
      "default-src 'none'",
      `script-src ${this.panel.webview.cspSource} 'unsafe-inline'`,
      "style-src 'unsafe-inline'",
      "img-src data:",
    ].join("; ");

    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta http-equiv="Content-Security-Policy" content="${csp}" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Manim Dock Stage</title>
  <style>
    html, body { margin: 0; height: 100%; background: #1a1b1e; color: #c8c8c8;
      font-family: var(--vscode-font-family, system-ui, sans-serif); overflow: hidden;
      display: flex; flex-direction: column; }
    .bar { flex: 0 0 auto; display: flex; gap: 12px; align-items: baseline; padding: 8px 12px;
      font-size: 12px; border-bottom: 1px solid #333; flex-wrap: wrap; }
    .bar strong { color: #eee; font-weight: 600; }
    .hint { opacity: 0.7; }
    .sel-bar { flex: 0 0 auto; display: none; gap: 6px; align-items: center; padding: 6px 12px;
      font-size: 11px; border-bottom: 1px solid #333; flex-wrap: wrap; background: #15161a; }
    .sel-bar.visible { display: flex; }
    .sel-bar .sel-info { color: #ffe08a; margin-right: 4px; }
    .sel-bar button {
      background: #2a2a2e; color: #ddd; border: 1px solid #555; border-radius: 2px;
      padding: 2px 8px; font: inherit; cursor: pointer;
    }
    .sel-bar button:hover:not(:disabled) { border-color: #7eb6ff; color: #fff; }
    .sel-bar button:disabled { opacity: 0.35; cursor: not-allowed; }
    #stage-host { flex: 1 1 auto; width: 100%; min-height: 0; position: relative; overflow: hidden; }
  </style>
</head>
<body>
  <div class="bar">
    <strong id="title">Stage</strong>
    <span class="hint">Click selects · Shift/Ctrl multi-select · Align on bar · Jump only if you ask · Open Properties separately</span>
  </div>
  <div id="selBar" class="sel-bar">
    <span class="sel-info" id="selInfo">0 selected</span>
    <button type="button" id="jumpBtn" class="jump">Jump</button>
    <button type="button" data-mode="left">Left</button>
    <button type="button" data-mode="center_x">Center X</button>
    <button type="button" data-mode="right">Right</button>
    <button type="button" data-mode="top">Top</button>
    <button type="button" data-mode="center_y">Center Y</button>
    <button type="button" data-mode="bottom">Bottom</button>
    <button type="button" data-mode="distribute_x">Distribute X</button>
    <button type="button" data-mode="distribute_y">Distribute Y</button>
  </div>
  <div id="stage-host"></div>
  <script src="${konvaUri}"></script>
  <script>
    const vscode = acquireVsCodeApi();
    const host = document.getElementById('stage-host');
    const titleEl = document.getElementById('title');
    const selBar = document.getElementById('selBar');
    const selInfo = document.getElementById('selInfo');
    let stage, layer, frameRect, world;
    let layout = null;
    let proxies = new Map();
    let selectedNames = [];
    let pendingHighlightLine = null;
    let scrubTime = null;
    let scrubUntilLine = null;
    let scrubPositions = null;

    document.querySelectorAll('#selBar button[data-mode]').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (selectedNames.length < 2) {
          selInfo.textContent = 'Shift/Ctrl-click a second chip to Align';
          return;
        }
        vscode.postMessage({
          type: 'align',
          mode: btn.getAttribute('data-mode'),
          selectedNames: selectedNames.slice(),
        });
      });
    });
    const jumpBtn = document.getElementById('jumpBtn');
    if (jumpBtn) {
      jumpBtn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        const name = selectedNames[selectedNames.length - 1];
        if (!name) return;
        vscode.postMessage({ type: 'jump', name: name });
      });
    }
    let manimMap = null; // { unit, minMX, maxMY, offX, offY, halfW, halfH }

    function isOpaqueItem(item) {
      return item && (item.mobject_kind === 'unknown' || item.note === 'opaque');
    }

    function kindLabel(item) {
      if (isOpaqueItem(item)) return 'opaque';
      return item.mobject_kind || '';
    }

    function rebuild() {
      if (!layout) return;
      const fw = layout.frame_width || 14.222;
      const fh = layout.frame_height || 8;
      const w = Math.max(1, host.clientWidth || 640);
      const h = Math.max(1, host.clientHeight || 360);
      const hostPad = 12;
      const items = layout.items || [];

      const logicalW = 1280;
      const logicalH = logicalW * (fh / fw);
      const halfW = 56;
      const halfH = 22;
      const fontSize = 12;

      // Camera is always the Manim frame. Expanding to item AABB made runaway
      // .shift() outliers shrink the whole Stage ("collapsed" sync).
      const minMX = -fw / 2;
      const maxMX = fw / 2;
      const minMY = -fh / 2;
      const maxMY = fh / 2;
      const spanX = Math.max(maxMX - minMX, 1e-6);
      const spanY = Math.max(maxMY - minMY, 1e-6);
      const innerW = logicalW - 2 * halfW;
      const innerH = logicalH - 2 * halfH;
      const unit = Math.min(innerW / spanX, innerH / spanY);
      const offX = halfW + (innerW - spanX * unit) / 2;
      const offY = halfH + (innerH - spanY * unit) / 2;
      manimMap = { unit: unit, minMX: minMX, maxMY: maxMY, offX: offX, offY: offY, halfW: halfW, halfH: halfH };

      function manimToLocal(x, y) {
        return {
          x: offX + (x - minMX) * unit,
          y: offY + (maxMY - y) * unit,
        };
      }

      if (stage) stage.destroy();
      stage = new Konva.Stage({ container: 'stage-host', width: w, height: h });
      layer = new Konva.Layer();
      stage.add(layer);

      world = new Konva.Group();
      layer.add(world);

      frameRect = new Konva.Rect({
        x: 0, y: 0, width: logicalW, height: logicalH,
        stroke: '#5a5a5a', strokeWidth: 2, fill: '#111214'
      });
      world.add(frameRect);

      const originLocal = manimToLocal(0, 0);
      world.add(new Konva.Line({
        points: [0, originLocal.y, logicalW, originLocal.y],
        stroke: '#2a2a2e', strokeWidth: 1
      }));
      world.add(new Konva.Line({
        points: [originLocal.x, 0, originLocal.x, logicalH],
        stroke: '#2a2a2e', strokeWidth: 1
      }));

      proxies = new Map();
      updateTitle(items.length);

      for (const item of items) {
        const opaque = isOpaqueItem(item);
        const pos = manimToLocal(item.x || 0, item.y || 0);
        const group = new Konva.Group({
          x: pos.x, y: pos.y, draggable: !!item.editable,
          name: item.name,
          dragBoundFunc: (abs) => {
            const transform = world.getAbsoluteTransform().copy().invert();
            const local = transform.point(abs);
            const clamped = {
              x: Math.min(logicalW - halfW, Math.max(halfW, local.x)),
              y: Math.min(logicalH - halfH, Math.max(halfH, local.y)),
            };
            return world.getAbsoluteTransform().point(clamped);
          },
        });
        group.setAttr('startLine', item.range && item.range.start_line);
        group.setAttr('endLine', item.range && item.range.end_line);
        group.setAttr('editable', !!item.editable);
        group.setAttr('opaque', opaque);
        group.setAttr('baseX', item.x || 0);
        group.setAttr('baseY', item.y || 0);
        const box = new Konva.Rect({
          x: -halfW, y: -halfH, width: halfW * 2, height: halfH * 2,
          fill: item.editable ? '#2d4a6f' : '#3a3a3a',
          stroke: item.editable ? '#7eb6ff' : '#666',
          strokeWidth: 1,
          dash: opaque ? [6, 4] : undefined,
          cornerRadius: 4, opacity: 0.92,
          name: 'chip'
        });
        group.add(box);
        group.add(new Konva.Text({
          text: item.name + '\\n' + kindLabel(item),
          fontSize: fontSize, fill: '#e8e8e8', align: 'center', verticalAlign: 'middle',
          width: halfW * 2, height: halfH * 2, x: -halfW, y: -halfH, listening: false,
          name: 'label'
        }));

        let startLocal = { x: 0, y: 0 };
        group.on('dragstart', () => {
          // Scrub overrides must not fight the drag or snap the chip back.
          scrubPositions = null;
          startLocal = { x: group.x(), y: group.y() };
        });
        group.on('dragend', () => {
          const dxLocal = group.x() - startLocal.x;
          const dyLocal = group.y() - startLocal.y;
          const dx = dxLocal / unit;
          const dy = -dyLocal / unit;
          scrubPositions = null;
          vscode.postMessage({
            type: 'dragEnd',
            name: item.name,
            dx: dx,
            dy: dy,
            anchorLine: item.range && item.range.start_line,
            x: (item.x || 0) + dx,
            y: (item.y || 0) + dy
          });
        });
        group.on('click', (evt) => {
          // Ignore the second click of a double-click (avoids extra editor churn).
          if (evt.evt && evt.evt.detail > 1) {
            return;
          }
          const toggle = !!(evt.evt && (evt.evt.shiftKey || evt.evt.metaKey || evt.evt.ctrlKey));
          updateSelection(item.name, toggle);
        });
        group.on('dblclick', (evt) => {
          evt.cancelBubble = true;
          if (evt.evt) {
            evt.evt.preventDefault();
            evt.evt.stopPropagation();
          }
        });
        world.add(group);
        proxies.set(item.name, group);
      }

      layer.batchDraw();
      const bounds = world.getClientRect({ skipTransform: true });
      const fit = Math.min(
        (w - hostPad * 2) / Math.max(bounds.width, 1),
        (h - hostPad * 2) / Math.max(bounds.height, 1)
      );
      world.scale({ x: fit, y: fit });
      world.position({
        x: (w - bounds.width * fit) / 2 - bounds.x * fit,
        y: (h - bounds.height * fit) / 2 - bounds.y * fit,
      });
      applyScrubVisuals();
      applySelectionStrokes();
      updateSelBar();
      layer.draw();
      if (pendingHighlightLine != null) {
        highlightLine(pendingHighlightLine);
      }
    }

    function updateTitle(itemCount) {
      let text = 'Stage: ' + (layout && layout.scene || '') + ' (' + itemCount + ' items)';
      if (scrubTime != null) {
        text += ' · scrub t=' + (Math.round(scrubTime * 100) / 100) + 's';
      }
      if (selectedNames.length > 1) {
        text += ' · ' + selectedNames.length + ' selected';
      }
      titleEl.textContent = text;
    }

    function updateSelection(name, toggle) {
      if (toggle) {
        const idx = selectedNames.indexOf(name);
        if (idx >= 0) {
          selectedNames.splice(idx, 1);
        } else {
          selectedNames.push(name);
        }
      } else {
        selectedNames = [name];
      }
      applySelectionStrokes();
      if (layer) layer.draw();
      updateTitle((layout && layout.items || []).length);
      updateSelBar();
      const primary = selectedNames.length
        ? selectedNames[selectedNames.length - 1]
        : name;
      vscode.postMessage({
        type: 'select',
        name: primary,
        primary: primary,
        selectedNames: selectedNames.slice(),
      });
    }

    function updateSelBar() {
      if (!selBar || !selInfo) return;
      const n = selectedNames.length;
      const canAlign = n >= 2;
      selBar.querySelectorAll('button[data-mode]').forEach((btn) => {
        btn.disabled = !canAlign;
      });
      if (jumpBtn) jumpBtn.disabled = n !== 1;
      if (n >= 2) {
        selBar.classList.add('visible');
        selInfo.textContent = n + ' selected — Align / Distribute:';
      } else if (n === 1) {
        selBar.classList.add('visible');
        selInfo.textContent = selectedNames[0] + ' — Jump · Shift/Ctrl-click another to align';
      } else {
        selBar.classList.remove('visible');
      }
    }

    function applySelectionStrokes() {
      for (const [name, group] of proxies) {
        const box = group.findOne('.chip');
        if (!box) continue;
        const editable = !!group.getAttr('editable');
        const opaque = !!group.getAttr('opaque');
        const selected = selectedNames.indexOf(name) >= 0;
        if (selected) {
          box.stroke('#ffe08a');
          box.strokeWidth(3);
        } else {
          box.stroke(editable ? '#7eb6ff' : '#666');
          box.strokeWidth(1);
        }
        box.dash(opaque ? [6, 4] : undefined);
      }
    }

    function applyScrubVisuals() {
      if (!manimMap) {
        for (const [, group] of proxies) {
          const start = group.getAttr('startLine') || 0;
          let opacity = 1;
          if (scrubUntilLine != null && start > scrubUntilLine) {
            opacity = 0.35;
          }
          group.opacity(opacity);
        }
        if (layout) updateTitle((layout.items || []).length);
        return;
      }
      const { unit, minMX, maxMY, offX, offY } = manimMap;
      for (const [name, group] of proxies) {
        const start = group.getAttr('startLine') || 0;
        const pos = scrubPositions && scrubPositions[name];
        if (pos && typeof pos.x === 'number' && typeof pos.y === 'number') {
          group.position({
            x: offX + (pos.x - minMX) * unit,
            y: offY + (maxMY - pos.y) * unit,
          });
          group.opacity(typeof pos.opacity === 'number' ? pos.opacity : 1);
        } else {
          const baseX = group.getAttr('baseX') || 0;
          const baseY = group.getAttr('baseY') || 0;
          group.position({
            x: offX + (baseX - minMX) * unit,
            y: offY + (maxMY - baseY) * unit,
          });
          let opacity = 1;
          if (scrubUntilLine != null && start > scrubUntilLine) {
            opacity = 0.35;
          }
          group.opacity(opacity);
        }
      }
      if (layout) updateTitle((layout.items || []).length);
    }

    function highlightLine(line) {
      pendingHighlightLine = line;
      let best = null;
      let bestDist = Infinity;
      for (const [, group] of proxies) {
        const start = group.getAttr('startLine') || 0;
        const end = group.getAttr('endLine') || start;
        if (line >= start && line <= end) {
          best = group;
          bestDist = 0;
        } else if (bestDist > 0) {
          const dist = Math.min(Math.abs(line - start), Math.abs(line - end));
          if (dist < bestDist && dist <= 3) {
            best = group;
            bestDist = dist;
          }
        }
      }
      applySelectionStrokes();
      if (best) {
        const name = best.name();
        if (selectedNames.indexOf(name) < 0) {
          const box = best.findOne('.chip');
          if (box) {
            box.stroke('#ffe08a');
            box.strokeWidth(2);
          }
        }
      }
      if (layer) layer.draw();
    }

    window.addEventListener('message', (event) => {
      const msg = event.data;
      if (msg && msg.type === 'layout') {
        layout = msg.layout;
        selectedNames = selectedNames.filter((n) =>
          (layout.items || []).some((i) => i.name === n)
        );
        // Drop stale scrub position overrides — they were computed before this
        // layout (e.g. pre-drag) and would snap chips back after a Stage patch.
        scrubPositions = null;
        rebuild();
      } else if (msg && msg.type === 'highlightLine') {
        highlightLine(msg.line);
      } else if (msg && msg.type === 'scrub') {
        scrubTime = typeof msg.time === 'number' ? msg.time : null;
        scrubUntilLine = typeof msg.activeUntilLine === 'number' ? msg.activeUntilLine : null;
        scrubPositions = msg.positions && typeof msg.positions === 'object' ? msg.positions : null;
        applyScrubVisuals();
        applySelectionStrokes();
        if (layer) layer.draw();
      }
    });
    window.addEventListener('resize', () => rebuild());
    vscode.postMessage({ type: 'ready' });
  </script>
</body>
</html>`;
  }

  dispose(): void {
    StagePanel.current = undefined;
    while (this.disposables.length) {
      this.disposables.pop()?.dispose();
    }
  }
}
