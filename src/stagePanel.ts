import * as path from "path";
import * as vscode from "vscode";
import { revealRange } from "./outlineTree";
import { ProposedPatchProvider, confirmAndApplyPatch } from "./patchConfirm";
import { PropertiesPanel } from "./propertiesPanel";
import { SceneLayout, SidecarClient } from "./sidecar";

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

  /** Scrub approximate visibility: dim proxies defined after activeUntilLine. */
  static scrub(
    filePath: string,
    time: number,
    activeUntilLine?: number
  ): void {
    const cur = StagePanel.current;
    if (!cur?.filePath || cur.filePath !== filePath) {
      return;
    }
    void cur.panel.webview.postMessage({
      type: "scrub",
      time,
      activeUntilLine,
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
      void this.panel.webview.postMessage({ type: "layout", layout: this.layout });
      if (this.layout.errors.length) {
        this.output.appendLine(`[stage] ${this.layout.errors.join("; ")}`);
      }
    } catch (err) {
      this.output.appendLine(`[stage] ${String(err)}`);
      void vscode.window.showErrorMessage(`Manim Dock Stage failed: ${String(err)}`);
    }
  }

  private static hasBuffHint(item: {
    layout_calls: { kind: string; code: string }[];
  }): boolean {
    return item.layout_calls.some(
      (c) =>
        c.kind === "arrange" ||
        c.kind === "next_to" ||
        /buff\s*=/.test(c.code)
    );
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
      const name = String(rec.name ?? "");
      const item = this.layout?.items.find((i) => i.name === name);
      if (item && this.filePath) {
        await revealRange(this.filePath, item.range);
        PropertiesPanel.setSelection(this.filePath, {
          kind: "mobject",
          name: item.name,
          anchorLine: item.range.start_line,
          hasBuffHint: StagePanel.hasBuffHint(item),
        });
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
    #stage-host { flex: 1 1 auto; width: 100%; min-height: 0; position: relative; overflow: hidden; }
  </style>
</head>
<body>
  <div class="bar">
    <strong id="title">Stage</strong>
    <span class="hint">Drag proxies · positions are heuristic (not a live Manim snapshot) · patches confirm before apply</span>
  </div>
  <div id="stage-host"></div>
  <script src="${konvaUri}"></script>
  <script>
    const vscode = acquireVsCodeApi();
    const host = document.getElementById('stage-host');
    const titleEl = document.getElementById('title');
    let stage, layer, frameRect;
    let layout = null;
    let proxies = new Map();
    let pendingHighlightLine = null;
    let scrubTime = null;
    let scrubUntilLine = null;

    function rebuild() {
      if (!layout) return;
      const fw = layout.frame_width || 14.222;
      const fh = layout.frame_height || 8;
      const w = Math.max(1, host.clientWidth || 640);
      const h = Math.max(1, host.clientHeight || 360);
      const hostPad = 12;
      const items = layout.items || [];

      // Logical Manim frame (fixed 16:9 workspace). Everything is built here, then
      // the whole world is uniformly scaled to fit the host — no clipping.
      const logicalW = 1280;
      const logicalH = logicalW * (fh / fw);
      const halfW = 56;
      const halfH = 22;
      const fontSize = 12;

      // Domain covers the Manim frame and every item; mapped into the INNER
      // rect so a full chip at either extreme still lies inside the frame.
      let minMX = -fw / 2;
      let maxMX = fw / 2;
      let minMY = -fh / 2;
      let maxMY = fh / 2;
      for (const item of items) {
        minMX = Math.min(minMX, item.x || 0);
        maxMX = Math.max(maxMX, item.x || 0);
        minMY = Math.min(minMY, item.y || 0);
        maxMY = Math.max(maxMY, item.y || 0);
      }
      const spanX = Math.max(maxMX - minMX, 1e-6);
      const spanY = Math.max(maxMY - minMY, 1e-6);
      const innerW = logicalW - 2 * halfW;
      const innerH = logicalH - 2 * halfH;
      const unit = Math.min(innerW / spanX, innerH / spanY);
      const offX = halfW + (innerW - spanX * unit) / 2;
      const offY = halfH + (innerH - spanY * unit) / 2;

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

      const world = new Konva.Group();
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
        const pos = manimToLocal(item.x || 0, item.y || 0);
        const group = new Konva.Group({
          x: pos.x, y: pos.y, draggable: !!item.editable,
          name: item.name,
          dragBoundFunc: (abs) => {
            // abs is stage-absolute; convert to world-local for clamping.
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
        const box = new Konva.Rect({
          x: -halfW, y: -halfH, width: halfW * 2, height: halfH * 2,
          fill: item.editable ? '#2d4a6f' : '#3a3a3a',
          stroke: item.editable ? '#7eb6ff' : '#666',
          strokeWidth: 1, cornerRadius: 4, opacity: 0.92,
          name: 'chip'
        });
        group.add(box);
        group.add(new Konva.Text({
          text: item.name + '\\n' + (item.mobject_kind || ''),
          fontSize: fontSize, fill: '#e8e8e8', align: 'center', verticalAlign: 'middle',
          width: halfW * 2, height: halfH * 2, x: -halfW, y: -halfH, listening: false
        }));

        let startLocal = { x: 0, y: 0 };
        group.on('dragstart', () => {
          startLocal = { x: group.x(), y: group.y() };
        });
        group.on('dragend', () => {
          const dxLocal = group.x() - startLocal.x;
          const dyLocal = group.y() - startLocal.y;
          const dx = dxLocal / unit;
          const dy = -dyLocal / unit;
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
        group.on('click', () => {
          vscode.postMessage({ type: 'select', name: item.name });
        });
        world.add(group);
        proxies.set(item.name, group);
      }

      // Uniformly scale+center the whole world into the host.
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
      applyScrubOpacity();
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
      titleEl.textContent = text;
    }

    function applyScrubOpacity() {
      for (const [, group] of proxies) {
        const start = group.getAttr('startLine') || 0;
        let opacity = 1;
        if (scrubUntilLine != null && start > scrubUntilLine) {
          opacity = 0.35;
        }
        group.opacity(opacity);
      }
      if (layout) {
        updateTitle((layout.items || []).length);
      }
    }

    function highlightLine(line) {
      pendingHighlightLine = line;
      let best = null;
      let bestDist = Infinity;
      for (const [, group] of proxies) {
        const start = group.getAttr('startLine') || 0;
        const end = group.getAttr('endLine') || start;
        const box = group.findOne('.chip');
        if (!box) continue;
        const editable = box.fill() === '#2d4a6f';
        box.stroke(editable ? '#7eb6ff' : '#666');
        box.strokeWidth(1);
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
      if (best) {
        const box = best.findOne('.chip');
        if (box) {
          box.stroke('#ffe08a');
          box.strokeWidth(3);
        }
        layer.draw();
      }
    }

    window.addEventListener('message', (event) => {
      const msg = event.data;
      if (msg && msg.type === 'layout') {
        layout = msg.layout;
        rebuild();
      } else if (msg && msg.type === 'highlightLine') {
        highlightLine(msg.line);
      } else if (msg && msg.type === 'scrub') {
        scrubTime = typeof msg.time === 'number' ? msg.time : null;
        scrubUntilLine = typeof msg.activeUntilLine === 'number' ? msg.activeUntilLine : null;
        applyScrubOpacity();
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
