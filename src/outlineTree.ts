import * as vscode from "vscode";
import {
  FileOutline,
  OutlineEvent,
  OutlineMethod,
  OutlineScene,
  SidecarClient,
  SourceRange,
} from "./sidecar";

type OutlineNode = StatusNode | FileNode | SceneNode | MethodNode | EventNode;

class StatusNode extends vscode.TreeItem {
  constructor(message: string, detail?: string) {
    super(message, vscode.TreeItemCollapsibleState.None);
    this.contextValue = "manimDock.status";
    this.iconPath = new vscode.ThemeIcon("warning");
    // Show detail in the tree (not only tooltip) so Cursor users can read it.
    this.description = detail ? detail.replace(/\s+/g, " ").slice(0, 140) : undefined;
    this.tooltip = detail ?? message;
  }
}

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

export class SceneNode extends vscode.TreeItem {
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
    public readonly sceneName: string,
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

/** Duck-type tree / command args (instanceof can fail across command invocations). */
export function asSceneTarget(
  item: unknown
): { filePath: string; sceneName: string } | undefined {
  if (!item || typeof item !== "object") {
    return undefined;
  }
  const rec = item as {
    filePath?: unknown;
    scene?: { name?: unknown };
  };
  if (
    typeof rec.filePath === "string" &&
    rec.scene &&
    typeof rec.scene.name === "string"
  ) {
    return { filePath: rec.filePath, sceneName: rec.scene.name };
  }
  return undefined;
}

export function asMethodTarget(
  item: unknown
): { filePath: string; sceneName: string; methodName: string } | undefined {
  if (!item || typeof item !== "object") {
    return undefined;
  }
  const rec = item as {
    filePath?: unknown;
    sceneName?: unknown;
    method?: { name?: unknown };
  };
  if (
    typeof rec.filePath === "string" &&
    typeof rec.sceneName === "string" &&
    rec.method &&
    typeof rec.method.name === "string"
  ) {
    return {
      filePath: rec.filePath,
      sceneName: rec.sceneName,
      methodName: rec.method.name,
    };
  }
  return undefined;
}

function collectPythonCandidatePaths(lastFilePath?: string): string[] {
  const candidates: string[] = [];
  const active = vscode.window.activeTextEditor;
  if (active?.document.languageId === "python" && !active.document.isUntitled) {
    candidates.push(active.document.uri.fsPath);
  }
  for (const ed of vscode.window.visibleTextEditors) {
    if (ed.document.languageId === "python" && !ed.document.isUntitled) {
      candidates.push(ed.document.uri.fsPath);
    }
  }
  // Critical in Cursor: sidebar focus may clear active/visible editors.
  for (const doc of vscode.workspace.textDocuments) {
    if (doc.languageId === "python" && !doc.isUntitled) {
      candidates.push(doc.uri.fsPath);
    }
  }
  if (lastFilePath) {
    candidates.push(lastFilePath);
  }
  return [...new Set(candidates)];
}

export class OutlineProvider implements vscode.TreeDataProvider<OutlineNode> {
  private _onDidChangeTreeData = new vscode.EventEmitter<OutlineNode | undefined>();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;
  private cache = new Map<string, FileOutline>();
  private lastFilePath: string | undefined;
  private lastStatus: string | undefined;

  constructor(
    private readonly sidecar: SidecarClient,
    private readonly output?: vscode.OutputChannel
  ) {}

  refresh(): void {
    this.cache.clear();
    this._onDidChangeTreeData.fire(undefined);
  }

  getLastFilePath(): string | undefined {
    return this.lastFilePath;
  }

  async resolvePythonOutline(): Promise<
    | { filePath: string; outline: FileOutline }
    | { error: string }
  > {
    const candidates = collectPythonCandidatePaths(this.lastFilePath);
    const problems: string[] = [];

    for (const filePath of candidates) {
      const outline = await this.loadOutline(filePath);
      if (outline.errors.length) {
        problems.push(`${filePath}: ${outline.errors.join("; ")}`);
        continue;
      }
      if (outline.scenes.length) {
        this.lastFilePath = filePath;
        this.lastStatus = undefined;
        return { filePath, outline };
      }
      problems.push(`${filePath}: no Scene subclasses found`);
    }

    if (!candidates.length) {
      return {
        error:
          "Open a Manim .py file (e.g. examples/minimal_lesson/lesson.py), click in the editor, then refresh Outline.",
      };
    }
    return {
      error: problems.length
        ? problems.join("\n")
        : `No Scene classes found in:\n${candidates.join("\n")}`,
    };
  }

  getTreeItem(element: OutlineNode): vscode.TreeItem {
    return element;
  }

  async getChildren(element?: OutlineNode): Promise<OutlineNode[]> {
    if (!element) {
      const resolved = await this.resolvePythonOutline();
      if ("error" in resolved) {
        this.lastStatus = resolved.error;
        this.output?.appendLine(`[outline] ${resolved.error}`);
        void vscode.window.showErrorMessage(
          `Manim Dock outline failed — see Output “Manim Dock” or run “Manim Dock: Debug Sidecar”.`,
          "Open Output"
        ).then((choice) => {
          if (choice === "Open Output") {
            this.output?.show(true);
          }
        });
        const firstLine = resolved.error.split("\n")[0] ?? resolved.error;
        return [
          new StatusNode("No scene outline available", firstLine),
          new StatusNode(
            "Run: Manim Dock: Debug Sidecar",
            resolved.error
          ),
        ];
      }
      this.lastFilePath = resolved.filePath;
      return [new FileNode(resolved.filePath, resolved.outline)];
    }

    if (element instanceof StatusNode) {
      return [];
    }

    if (element instanceof FileNode) {
      if (element.outline.errors.length) {
        return element.outline.errors.map((e) => new StatusNode(e));
      }
      if (!element.outline.scenes.length) {
        return [new StatusNode("No Scene subclasses in this file")];
      }
      return element.outline.scenes.map(
        (scene) => new SceneNode(element.filePath, scene)
      );
    }

    if (element instanceof SceneNode) {
      return element.scene.methods.map(
        (method) => new MethodNode(element.filePath, element.scene.name, method)
      );
    }

    if (element instanceof MethodNode) {
      return element.method.events.map(
        (event) => new EventNode(element.filePath, event)
      );
    }

    return [];
  }

  private async loadOutline(filePath: string): Promise<FileOutline> {
    const cached = this.cache.get(filePath);
    if (cached) {
      return cached;
    }
    try {
      const outline = await this.sidecar.outline(filePath);
      this.cache.set(filePath, outline);
      if (!outline.errors.length && outline.scenes.length) {
        this.lastFilePath = filePath;
      }
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
