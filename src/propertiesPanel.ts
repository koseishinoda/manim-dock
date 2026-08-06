import * as vscode from "vscode";
import { revealRange } from "./outlineTree";
import { ProposedPatchProvider, confirmAndApplyPatch } from "./patchConfirm";
import { SidecarClient, SourceRange } from "./sidecar";

export type PropertiesSelection =
  | {
      kind: "mobject";
      name: string;
      anchorLine?: number;
      hasBuffHint?: boolean;
    }
  | {
      kind: "event";
      eventKind: string;
      line: number;
      duration: number;
    };

/**
 * Properties webview — shift / scale / buff / duration editors for Stage+Timeline selection.
 */
export class PropertiesPanel {
  public static readonly viewType = "manimDock.properties";
  private static current: PropertiesPanel | undefined;

  private readonly panel: vscode.WebviewPanel;
  private disposables: vscode.Disposable[] = [];
  private filePath: string | undefined;
  private sceneName: string | undefined;
  private selection: PropertiesSelection | undefined;

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
  ): Promise<PropertiesPanel> {
    ProposedPatchProvider.ensure(context);
    const column = vscode.ViewColumn.Beside;

    if (PropertiesPanel.current) {
      PropertiesPanel.current.panel.reveal(column);
      await PropertiesPanel.current.load(filePath, sceneName);
      return PropertiesPanel.current;
    }

    const panel = vscode.window.createWebviewPanel(
      PropertiesPanel.viewType,
      `Properties: ${sceneName}`,
      column,
      {
        enableScripts: true,
        retainContextWhenHidden: true,
      }
    );
    PropertiesPanel.current = new PropertiesPanel(
      panel,
      context,
      sidecar,
      output
    );
    await PropertiesPanel.current.load(filePath, sceneName);
    return PropertiesPanel.current;
  }

  async load(filePath: string, sceneName: string): Promise<void> {
    this.filePath = filePath;
    this.sceneName = sceneName;
    this.panel.title = `Properties: ${sceneName}`;
    this.pushState();
  }

  static setSelection(
    filePath: string,
    selection: PropertiesSelection
  ): void {
    const cur = PropertiesPanel.current;
    if (!cur?.filePath || cur.filePath !== filePath) {
      return;
    }
    cur.selection = selection;
    cur.pushState();
  }

  static refreshIfOpen(filePath?: string): void {
    const cur = PropertiesPanel.current;
    if (!cur?.filePath) {
      return;
    }
    if (filePath && cur.filePath !== filePath) {
      return;
    }
    cur.pushState();
  }

  private pushState(): void {
    void this.panel.webview.postMessage({
      type: "state",
      scene: this.sceneName ?? "",
      filePath: this.filePath ?? "",
      selection: this.selection ?? null,
    });
  }

  private async onMessage(msg: unknown): Promise<void> {
    if (!msg || typeof msg !== "object") {
      return;
    }
    const rec = msg as Record<string, unknown>;
    const type = rec.type;

    if (type === "ready") {
      this.pushState();
      return;
    }

    if (type === "jump") {
      if (!this.filePath || !this.selection) {
        return;
      }
      if (this.selection.kind === "mobject" && this.selection.anchorLine) {
        await revealRange(this.filePath, {
          start_line: this.selection.anchorLine,
          end_line: this.selection.anchorLine,
        } as SourceRange);
      } else if (this.selection.kind === "event") {
        await revealRange(this.filePath, {
          start_line: this.selection.line,
          end_line: this.selection.line,
        } as SourceRange);
      }
      return;
    }

    if (type === "applyShift") {
      await this.applyShift(rec);
      return;
    }
    if (type === "applyScale") {
      await this.applyScale(rec);
      return;
    }
    if (type === "applyBuff") {
      await this.applyBuff(rec);
      return;
    }
    if (type === "applyDuration") {
      await this.applyDuration(rec);
    }
  }

  private async applyShift(rec: Record<string, unknown>): Promise<void> {
    if (!this.filePath || this.selection?.kind !== "mobject") {
      return;
    }
    const dx = Number(rec.dx ?? 0);
    const dy = Number(rec.dy ?? 0);
    if (Math.abs(dx) < 1e-9 && Math.abs(dy) < 1e-9) {
      return;
    }
    const doc = await vscode.workspace.openTextDocument(this.filePath);
    let proposal;
    try {
      proposal = await this.sidecar.proposeShift(
        this.filePath,
        this.selection.name,
        dx,
        dy,
        doc.getText(),
        this.selection.anchorLine
      );
    } catch (err) {
      void vscode.window.showErrorMessage(
        `Manim Dock patch failed: ${String(err)}`
      );
      return;
    }
    await this.confirmProposal(proposal, "properties");
  }

  private async applyScale(rec: Record<string, unknown>): Promise<void> {
    if (!this.filePath || this.selection?.kind !== "mobject") {
      return;
    }
    const factor = Number(rec.factor ?? 1);
    const doc = await vscode.workspace.openTextDocument(this.filePath);
    let proposal;
    try {
      proposal = await this.sidecar.proposeScale(
        this.filePath,
        this.selection.name,
        factor,
        doc.getText(),
        this.selection.anchorLine
      );
    } catch (err) {
      void vscode.window.showErrorMessage(
        `Manim Dock patch failed: ${String(err)}`
      );
      return;
    }
    await this.confirmProposal(proposal, "properties");
  }

  private async applyBuff(rec: Record<string, unknown>): Promise<void> {
    if (!this.filePath || this.selection?.kind !== "mobject") {
      return;
    }
    const buff = Number(rec.buff ?? 0);
    const doc = await vscode.workspace.openTextDocument(this.filePath);
    let proposal;
    try {
      proposal = await this.sidecar.proposeBuff(
        this.filePath,
        this.selection.name,
        buff,
        doc.getText(),
        this.selection.anchorLine
      );
    } catch (err) {
      void vscode.window.showErrorMessage(
        `Manim Dock patch failed: ${String(err)}`
      );
      return;
    }
    await this.confirmProposal(proposal, "properties");
  }

  private async applyDuration(rec: Record<string, unknown>): Promise<void> {
    if (!this.filePath || this.selection?.kind !== "event") {
      return;
    }
    const duration = Number(rec.duration ?? 0);
    if (duration < 0) {
      return;
    }
    const kind = this.selection.eventKind;
    if (kind !== "play" && kind !== "wait") {
      void vscode.window.showWarningMessage(
        "Manim Dock: duration edits apply to play/wait only."
      );
      return;
    }
    const doc = await vscode.workspace.openTextDocument(this.filePath);
    let proposal;
    try {
      proposal = await this.sidecar.proposeDuration(
        this.filePath,
        kind,
        this.selection.line,
        duration,
        doc.getText()
      );
    } catch (err) {
      void vscode.window.showErrorMessage(
        `Manim Dock timing patch failed: ${String(err)}`
      );
      return;
    }
    await this.confirmProposal(proposal, "properties");
  }

  private async confirmProposal(
    proposal: {
      ok: boolean;
      path: string;
      original: string;
      proposed: string;
      diff: string;
      error: string | null;
      summary: string;
    },
    channel: string
  ): Promise<void> {
    if (!proposal.ok) {
      void vscode.window.showWarningMessage(
        `Manim Dock: ${proposal.error ?? "patch failed"}`
      );
      return;
    }
    const applied = await confirmAndApplyPatch(
      this.context,
      {
        path: proposal.path,
        original: proposal.original,
        proposed: proposal.proposed,
        summary: proposal.summary,
        diff: proposal.diff,
      },
      this.output,
      channel
    );
    if (applied) {
      // Document save triggers Stage/Timeline refresh via extension host.
      this.pushState();
    }
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
  <title>Manim Dock Properties</title>
  <style>
    html, body { margin: 0; height: 100%; background: #1a1b1e; color: #c8c8c8;
      font-family: var(--vscode-font-family, system-ui, sans-serif);
      display: flex; flex-direction: column; overflow: hidden; }
    .bar { flex: 0 0 auto; display: flex; gap: 12px; align-items: baseline; padding: 8px 12px;
      font-size: 12px; border-bottom: 1px solid #333; flex-wrap: wrap; }
    .bar strong { color: #eee; }
    .hint { opacity: 0.7; }
    #body { flex: 1 1 auto; min-height: 0; padding: 12px; overflow: auto; box-sizing: border-box;
      font-size: 12px; }
    .empty { opacity: 0.65; }
    .field { display: grid; grid-template-columns: 88px minmax(0, 1fr); gap: 8px;
      align-items: center; margin-bottom: 8px; }
    .field label { opacity: 0.85; }
    .row-actions { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; margin-top: 4px; }
    input[type="number"] {
      width: 72px; background: #111214; color: #e8e8e8; border: 1px solid #444;
      border-radius: 2px; padding: 4px 6px; font: inherit;
    }
    button {
      background: #2d4a6f; color: #e8e8e8; border: 1px solid #7eb6ff;
      border-radius: 2px; padding: 4px 10px; font: inherit; cursor: pointer;
    }
    button.secondary { background: #2a2a2e; border-color: #666; }
    button:hover { filter: brightness(1.08); }
    .name { color: #eee; font-weight: 600; margin-bottom: 10px; }
    .muted { opacity: 0.65; font-size: 11px; margin-top: 8px; }
  </style>
</head>
<body>
  <div class="bar">
    <strong id="title">Properties</strong>
    <span class="hint">Select a Stage proxy or Timeline beat · patches confirm before apply</span>
  </div>
  <div id="body"><div class="empty">No selection</div></div>
  <script>
    const vscode = acquireVsCodeApi();
    const bodyEl = document.getElementById('body');
    const titleEl = document.getElementById('title');
    let state = { scene: '', selection: null };

    function numVal(id, fallback) {
      const el = document.getElementById(id);
      if (!el) return fallback;
      const n = Number(el.value);
      return Number.isFinite(n) ? n : fallback;
    }

    function render() {
      titleEl.textContent = 'Properties' + (state.scene ? ': ' + state.scene : '');
      const sel = state.selection;
      if (!sel) {
        bodyEl.innerHTML = '<div class="empty">No selection — click a Stage proxy or Timeline row</div>';
        return;
      }
      if (sel.kind === 'mobject') {
        const buffDisabled = sel.hasBuffHint ? '' : 'disabled title="No arrange/next_to buff site detected"';
        bodyEl.innerHTML =
          '<div class="name">' + escapeHtml(sel.name) + '</div>' +
          '<div class="field"><label>Shift dx</label><input id="dx" type="number" step="0.1" value="0" /></div>' +
          '<div class="field"><label>Shift dy</label><input id="dy" type="number" step="0.1" value="0" /></div>' +
          '<div class="row-actions"><button id="applyShift">Apply shift</button></div>' +
          '<div class="field" style="margin-top:12px"><label>Scale</label><input id="factor" type="number" step="0.1" value="1.2" /></div>' +
          '<div class="row-actions"><button id="applyScale">Apply scale</button></div>' +
          '<div class="field" style="margin-top:12px"><label>Buff</label><input id="buff" type="number" step="0.05" value="0.25" ' + buffDisabled + ' /></div>' +
          '<div class="row-actions"><button id="applyBuff" ' + buffDisabled + '>Apply buff</button></div>' +
          '<div class="row-actions" style="margin-top:12px"><button class="secondary" id="jump">Jump to source</button></div>' +
          (sel.hasBuffHint ? '' : '<div class="muted">Buff needs an arrange/next_to (or SurroundingRectangle) call with buff=</div>');
        document.getElementById('applyShift').onclick = () => {
          vscode.postMessage({ type: 'applyShift', dx: numVal('dx', 0), dy: numVal('dy', 0) });
        };
        document.getElementById('applyScale').onclick = () => {
          vscode.postMessage({ type: 'applyScale', factor: numVal('factor', 1) });
        };
        const buffBtn = document.getElementById('applyBuff');
        if (buffBtn && !sel.hasBuffHint) {
          // keep disabled
        } else if (buffBtn) {
          buffBtn.onclick = () => {
            vscode.postMessage({ type: 'applyBuff', buff: numVal('buff', 0.25) });
          };
        }
        document.getElementById('jump').onclick = () => {
          vscode.postMessage({ type: 'jump' });
        };
        return;
      }
      if (sel.kind === 'event') {
        const editable = sel.eventKind === 'play' || sel.eventKind === 'wait';
        bodyEl.innerHTML =
          '<div class="name">' + escapeHtml(sel.eventKind) + ' · L' + sel.line + '</div>' +
          '<div class="field"><label>Duration</label><input id="duration" type="number" step="0.05" min="0" value="' +
            Number(sel.duration || 0) + '" ' + (editable ? '' : 'disabled') + ' /></div>' +
          '<div class="row-actions"><button id="applyDuration" ' + (editable ? '' : 'disabled') +
            '>Apply duration</button>' +
            '<button class="secondary" id="jump">Jump to source</button></div>' +
          (editable ? '' : '<div class="muted">Only play/wait durations are editable</div>');
        const durBtn = document.getElementById('applyDuration');
        if (durBtn && editable) {
          durBtn.onclick = () => {
            vscode.postMessage({ type: 'applyDuration', duration: numVal('duration', 0) });
          };
        }
        document.getElementById('jump').onclick = () => {
          vscode.postMessage({ type: 'jump' });
        };
      }
    }

    function escapeHtml(s) {
      return String(s).replace(/[&<>"']/g, (c) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
      })[c]);
    }

    window.addEventListener('message', (event) => {
      const msg = event.data;
      if (msg && msg.type === 'state') {
        state = msg;
        render();
      }
    });
    vscode.postMessage({ type: 'ready' });
  </script>
</body>
</html>`;
  }

  dispose(): void {
    PropertiesPanel.current = undefined;
    while (this.disposables.length) {
      this.disposables.pop()?.dispose();
    }
  }
}
