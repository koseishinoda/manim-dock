import * as path from "path";
import * as vscode from "vscode";
import { revealRange } from "./outlineTree";
import { SceneLayout, SidecarClient } from "./sidecar";

interface PendingPatch {
  path: string;
  original: string;
  proposed: string;
  summary: string;
  diff: string;
}

/**
 * Konva Stage webview — heuristic layout proxies; drag → confirm-diff → apply.
 */
export class StagePanel {
  public static readonly viewType = "manimDock.stage";
  private static current: StagePanel | undefined;
  private static proposedProvider: ProposedPatchProvider | undefined;

  private readonly panel: vscode.WebviewPanel;
  private disposables: vscode.Disposable[] = [];
  private filePath: string | undefined;
  private sceneName: string | undefined;
  private layout: SceneLayout | undefined;
  private pending: PendingPatch | undefined;

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

  static ensureProposedProvider(context: vscode.ExtensionContext): ProposedPatchProvider {
    if (!StagePanel.proposedProvider) {
      StagePanel.proposedProvider = new ProposedPatchProvider();
      context.subscriptions.push(
        vscode.workspace.registerTextDocumentContentProvider(
          ProposedPatchProvider.scheme,
          StagePanel.proposedProvider
        )
      );
    }
    return StagePanel.proposedProvider;
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

    this.pending = {
      path: this.filePath,
      original: proposal.original,
      proposed: proposal.proposed,
      summary: proposal.summary,
      diff: proposal.diff,
    };

    const provider = StagePanel.ensureProposedProvider(this.context);
    const proposedUri = provider.set(this.filePath, proposal.proposed);
    await vscode.commands.executeCommand(
      "vscode.diff",
      vscode.Uri.file(this.filePath),
      proposedUri,
      `Manim Dock: ${proposal.summary}`
    );

    const choice = await vscode.window.showInformationMessage(
      `Apply layout patch?\n${proposal.summary}`,
      { modal: true, detail: truncate(proposal.diff, 1200) },
      "Apply",
      "Cancel"
    );

    if (choice === "Apply") {
      await this.applyPending();
    } else {
      this.pending = undefined;
      await this.refresh();
    }
  }

  private async applyPending(): Promise<void> {
    if (!this.pending) {
      return;
    }
    const uri = vscode.Uri.file(this.pending.path);
    const doc = await vscode.workspace.openTextDocument(uri);
    const current = doc.getText();
    if (current !== this.pending.original) {
      void vscode.window.showErrorMessage(
        "Manim Dock: file changed since the patch was proposed. Refresh Stage and try again."
      );
      this.pending = undefined;
      await this.refresh();
      return;
    }

    const edit = new vscode.WorkspaceEdit();
    const start = new vscode.Position(0, 0);
    const end = doc.lineAt(doc.lineCount - 1).range.end;
    edit.replace(uri, new vscode.Range(start, end), this.pending.proposed);
    const ok = await vscode.workspace.applyEdit(edit);
    if (!ok) {
      void vscode.window.showErrorMessage("Manim Dock: failed to apply patch edit.");
      return;
    }
    await doc.save();
    this.output.appendLine(`[stage] applied ${this.pending.summary}`);
    void vscode.window.showInformationMessage(
      `Manim Dock: applied ${this.pending.summary}`
    );
    this.pending = undefined;
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
      font-family: var(--vscode-font-family, system-ui, sans-serif); overflow: hidden; }
    .bar { display: flex; gap: 12px; align-items: baseline; padding: 8px 12px;
      font-size: 12px; border-bottom: 1px solid #333; flex-wrap: wrap; }
    .bar strong { color: #eee; font-weight: 600; }
    .hint { opacity: 0.7; }
    #stage-host { width: 100%; height: calc(100% - 40px); }
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

    function manimToScreen(x, y, fw, fh, pad, scale) {
      // Manim: origin center, +y up. Screen: origin top-left, +y down.
      const sx = pad + (fw / 2 + x) * scale;
      const sy = pad + (fh / 2 - y) * scale;
      return { x: sx, y: sy };
    }

    function screenDeltaToManim(dx, dy, scale) {
      return { dx: dx / scale, dy: -dy / scale };
    }

    function rebuild() {
      if (!layout) return;
      const fw = layout.frame_width || 14.222;
      const fh = layout.frame_height || 8;
      const w = host.clientWidth || 640;
      const h = host.clientHeight || 360;
      const pad = 24;
      const scale = Math.min((w - pad * 2) / fw, (h - pad * 2) / fh);

      if (stage) stage.destroy();
      stage = new Konva.Stage({ container: 'stage-host', width: w, height: h });
      layer = new Konva.Layer();
      stage.add(layer);

      frameRect = new Konva.Rect({
        x: pad, y: pad, width: fw * scale, height: fh * scale,
        stroke: '#5a5a5a', strokeWidth: 1, fill: '#111214'
      });
      layer.add(frameRect);

      // Axes crosshair
      const cx = pad + (fw / 2) * scale;
      const cy = pad + (fh / 2) * scale;
      layer.add(new Konva.Line({ points: [pad, cy, pad + fw * scale, cy], stroke: '#2a2a2e', strokeWidth: 1 }));
      layer.add(new Konva.Line({ points: [cx, pad, cx, pad + fh * scale], stroke: '#2a2a2e', strokeWidth: 1 }));

      proxies = new Map();
      const items = layout.items || [];
      titleEl.textContent = 'Stage: ' + (layout.scene || '') + ' (' + items.length + ' items)';

      for (const item of items) {
        const pos = manimToScreen(item.x || 0, item.y || 0, fw, fh, pad, scale);
        const group = new Konva.Group({
          x: pos.x, y: pos.y, draggable: !!item.editable,
          name: item.name
        });
        const box = new Konva.Rect({
          x: -48, y: -18, width: 96, height: 36,
          fill: item.editable ? '#2d4a6f' : '#3a3a3a',
          stroke: item.editable ? '#7eb6ff' : '#666',
          strokeWidth: 1, cornerRadius: 4, opacity: 0.92
        });
        const label = new Konva.Text({
          text: item.name + '\\n' + (item.mobject_kind || ''),
          fontSize: 11, fill: '#e8e8e8', align: 'center',
          width: 96, x: -48, y: -14, listening: false
        });
        group.add(box);
        group.add(label);

        let start = { x: 0, y: 0 };
        group.on('dragstart', () => {
          start = { x: group.x(), y: group.y() };
        });
        group.on('dragend', () => {
          const d = screenDeltaToManim(group.x() - start.x, group.y() - start.y, scale);
          vscode.postMessage({
            type: 'dragEnd',
            name: item.name,
            dx: d.dx,
            dy: d.dy,
            anchorLine: item.range && item.range.start_line,
            x: item.x + d.dx,
            y: item.y + d.dy
          });
        });
        group.on('click', () => {
          vscode.postMessage({ type: 'select', name: item.name });
        });
        layer.add(group);
        proxies.set(item.name, group);
      }
      layer.draw();
    }

    window.addEventListener('message', (event) => {
      const msg = event.data;
      if (msg && msg.type === 'layout') {
        layout = msg.layout;
        rebuild();
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

class ProposedPatchProvider implements vscode.TextDocumentContentProvider {
  static readonly scheme = "manim-dock-proposed";
  private content = new Map<string, string>();
  private _onDidChange = new vscode.EventEmitter<vscode.Uri>();
  readonly onDidChange = this._onDidChange.event;

  set(filePath: string, proposed: string): vscode.Uri {
    const uri = vscode.Uri.parse(
      `${ProposedPatchProvider.scheme}:${filePath}?t=${Date.now()}`
    );
    this.content.set(uri.toString(), proposed);
    this._onDidChange.fire(uri);
    return uri;
  }

  provideTextDocumentContent(uri: vscode.Uri): string {
    return this.content.get(uri.toString()) ?? "";
  }
}

function truncate(text: string, max: number): string {
  if (text.length <= max) {
    return text;
  }
  return text.slice(0, max) + "\n…";
}
