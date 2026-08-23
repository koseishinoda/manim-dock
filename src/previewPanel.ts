import * as path from "path";
import * as vscode from "vscode";

/**
 * Thin built-in preview for render output (video or still).
 * Not a Sideview clone — coexist with Skill / Sideview for richer playback.
 */
export class PreviewPanel {
  public static readonly viewType = "manimDock.preview";
  private static current: PreviewPanel | undefined;

  private readonly panel: vscode.WebviewPanel;
  private disposables: vscode.Disposable[] = [];

  private constructor(panel: vscode.WebviewPanel) {
    this.panel = panel;
    this.panel.onDidDispose(() => this.dispose(), null, this.disposables);
  }

  static show(mediaPath: string, title?: string): void {
    const column = vscode.ViewColumn.Beside;
    if (PreviewPanel.current) {
      PreviewPanel.current.panel.reveal(column);
      PreviewPanel.current.setMedia(mediaPath, title);
      return;
    }

    const panel = vscode.window.createWebviewPanel(
      PreviewPanel.viewType,
      title ?? "Manim Dock Preview",
      column,
      {
        enableScripts: true,
        retainContextWhenHidden: true,
        localResourceRoots: [vscode.Uri.file(path.dirname(mediaPath))],
      }
    );
    PreviewPanel.current = new PreviewPanel(panel);
    PreviewPanel.current.setMedia(mediaPath, title);
  }

  private setMedia(mediaPath: string, title?: string): void {
    const dir = path.dirname(mediaPath);
    this.panel.title = title ?? path.basename(mediaPath);
    this.panel.webview.options = {
      enableScripts: true,
      localResourceRoots: [vscode.Uri.file(dir)],
    };
    const uri = this.panel.webview.asWebviewUri(vscode.Uri.file(mediaPath));
    const ext = path.extname(mediaPath).toLowerCase();
    const isImage = [".png", ".jpg", ".jpeg", ".gif", ".webp"].includes(ext);
    const csp = [
      "default-src 'none'",
      `media-src ${this.panel.webview.cspSource} file:`,
      `img-src ${this.panel.webview.cspSource} file: data:`,
      "style-src 'unsafe-inline'",
    ].join("; ");

    const mediaEl = isImage
      ? `<img class="still" alt="${escapeHtml(path.basename(mediaPath))}" src="${uri}" />`
      : `<video controls autoplay src="${uri}"></video>`;

    this.panel.webview.html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta http-equiv="Content-Security-Policy" content="${csp}" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Manim Dock Preview</title>
  <style>
    html, body {
      margin: 0;
      padding: 0;
      height: 100%;
      background: #1e1e1e;
      color: #ccc;
      font-family: var(--vscode-font-family, sans-serif);
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }
    .wrap {
      display: flex;
      flex-direction: column;
      flex: 1 1 auto;
      min-height: 0;
      box-sizing: border-box;
      padding: 12px;
      gap: 8px;
    }
    .meta {
      flex: 0 0 auto;
      font-size: 12px;
      opacity: 0.8;
      word-break: break-all;
    }
    video, img.still {
      flex: 1 1 auto;
      min-height: 0;
      width: 100%;
      object-fit: contain;
      background: #000;
    }
    .hint {
      flex: 0 0 auto;
      font-size: 11px;
      opacity: 0.65;
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="meta">${escapeHtml(mediaPath)}</div>
    ${mediaEl}
    <div class="hint">Thin Dock preview — use Manim Sideview for a richer player if you prefer.</div>
  </div>
</body>
</html>`;
  }

  dispose(): void {
    PreviewPanel.current = undefined;
    while (this.disposables.length) {
      this.disposables.pop()?.dispose();
    }
  }
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
