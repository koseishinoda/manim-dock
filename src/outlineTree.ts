import * as vscode from "vscode";
import {
  FileOutline,
  OutlineEvent,
  OutlineMethod,
  OutlineScene,
  SidecarClient,
  SourceRange,
} from "./sidecar";

type OutlineNode = FileNode | SceneNode | MethodNode | EventNode;

class FileNode extends vscode.TreeItem {
  constructor(
    public readonly filePath: string,
    public readonly outline: FileOutline
  ) {
    super(vscode.workspace.asRelativePath(filePath), vscode.TreeItemCollapsibleState.Expanded);
    this.contextValue = "manimDock.file";
    this.iconPath = new vscode.ThemeIcon("file-code");
    if (outline.errors.length) {
      this.description = "parse error";
      this.tooltip = outline.errors.join("\n");
    }
  }
}

class SceneNode extends vscode.TreeItem {
  constructor(
    public readonly filePath: string,
    public readonly scene: OutlineScene
  ) {
    super(scene.name, vscode.TreeItemCollapsibleState.Expanded);
    this.contextValue = "manimDock.scene";
    this.description = scene.bases.join(", ");
    this.iconPath = new vscode.ThemeIcon("symbol-class");
    this.command = {
      command: "manimDock.revealInEditor",
      title: "Reveal",
      arguments: [filePath, scene.range],
    };
  }
}

class MethodNode extends vscode.TreeItem {
  constructor(
    public readonly filePath: string,
    public readonly method: OutlineMethod
  ) {
    super(
      method.name,
      method.events.length
        ? vscode.TreeItemCollapsibleState.Collapsed
        : vscode.TreeItemCollapsibleState.None
    );
    this.contextValue = "manimDock.method";
    this.iconPath = new vscode.ThemeIcon("symbol-method");
    this.command = {
      command: "manimDock.revealInEditor",
      title: "Reveal",
      arguments: [filePath, method.range],
    };
  }
}

class EventNode extends vscode.TreeItem {
  constructor(
    public readonly filePath: string,
    public readonly event: OutlineEvent
  ) {
    super(event.label, vscode.TreeItemCollapsibleState.None);
    this.contextValue = "manimDock.event";
    this.description = event.kind;
    this.iconPath = new vscode.ThemeIcon(
      event.kind === "next_section"
        ? "bookmark"
        : event.kind === "wait"
          ? "debug-pause"
          : "play"
    );
    this.command = {
      command: "manimDock.revealInEditor",
      title: "Reveal",
      arguments: [filePath, event.range],
    };
  }
}

export class OutlineProvider implements vscode.TreeDataProvider<OutlineNode> {
  private _onDidChangeTreeData = new vscode.EventEmitter<OutlineNode | undefined>();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;
  private cache = new Map<string, FileOutline>();

  constructor(private readonly sidecar: SidecarClient) {}

  refresh(): void {
    this.cache.clear();
    this._onDidChangeTreeData.fire(undefined);
  }

  getTreeItem(element: OutlineNode): vscode.TreeItem {
    return element;
  }

  async getChildren(element?: OutlineNode): Promise<OutlineNode[]> {
    if (!element) {
      const editor = vscode.window.activeTextEditor;
      if (!editor || editor.document.languageId !== "python") {
        return [];
      }
      const filePath = editor.document.uri.fsPath;
      const outline = await this.loadOutline(filePath, editor.document.getText());
      return [new FileNode(filePath, outline)];
    }

    if (element instanceof FileNode) {
      return element.outline.scenes.map(
        (scene) => new SceneNode(element.filePath, scene)
      );
    }

    if (element instanceof SceneNode) {
      return element.scene.methods.map(
        (method) => new MethodNode(element.filePath, method)
      );
    }

    if (element instanceof MethodNode) {
      return element.method.events.map(
        (event) => new EventNode(element.filePath, event)
      );
    }

    return [];
  }

  private async loadOutline(filePath: string, _text: string): Promise<FileOutline> {
    const cached = this.cache.get(filePath);
    if (cached) {
      return cached;
    }
    try {
      const outline = await this.sidecar.outline(filePath);
      this.cache.set(filePath, outline);
      return outline;
    } catch (err) {
      const failed: FileOutline = {
        path: filePath,
        scenes: [],
        errors: [String(err)],
      };
      this.cache.set(filePath, failed);
      return failed;
    }
  }
}

export async function revealRange(filePath: string, range: SourceRange): Promise<void> {
  const doc = await vscode.workspace.openTextDocument(filePath);
  const editor = await vscode.window.showTextDocument(doc, { preview: false });
  const start = new vscode.Position(Math.max(0, range.start_line - 1), 0);
  const endLine = Math.max(range.start_line, range.end_line) - 1;
  const end = doc.lineAt(Math.min(endLine, doc.lineCount - 1)).range.end;
  editor.selection = new vscode.Selection(start, start);
  editor.revealRange(new vscode.Range(start, end), vscode.TextEditorRevealType.InCenter);
}
