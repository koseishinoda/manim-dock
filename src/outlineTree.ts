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
    public readonly scene: OutlineScene,
    checked: boolean = false
  ) {
    super(scene.name, vscode.TreeItemCollapsibleState.Expanded);
    this.contextValue = "manimDock.scene";
    this.description = scene.bases.join(", ");
    this.iconPath = new vscode.ThemeIcon("symbol-class");
    this.checkboxState = checked
      ? vscode.TreeItemCheckboxState.Checked
      : vscode.TreeItemCheckboxState.Unchecked;
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
    const targets = event.targets?.filter(Boolean) ?? [];
    // Grey secondary: mobject bindings (label already includes anim + target when known).
    this.description =
      targets.length > 0 ? targets.join(", ") : event.kind;
    this.tooltip = targets.length
      ? `${event.label}\ntargets: ${targets.join(", ")}`
      : event.label;
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
    sceneName?: unknown;
  };
  if (
    typeof rec.filePath === "string" &&
    rec.scene &&
    typeof rec.scene.name === "string"
  ) {
    return { filePath: rec.filePath, sceneName: rec.scene.name };
  }
  // MethodNode (and similar): filePath + sceneName
  if (typeof rec.filePath === "string" && typeof rec.sceneName === "string") {
    return { filePath: rec.filePath, sceneName: rec.sceneName };
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
  /** Per-file scene names checked for concatenated render (session). */
  private concatChecked = new Map<string, Set<string>>();
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

  isSceneChecked(filePath: string, sceneName: string): boolean {
    return this.concatChecked.get(filePath)?.has(sceneName) ?? false;
  }

  setSceneChecked(filePath: string, sceneName: string, checked: boolean): void {
    let set = this.concatChecked.get(filePath);
    if (!set) {
      set = new Set();
      this.concatChecked.set(filePath, set);
    }
    if (checked) {
      set.add(sceneName);
    } else {
      set.delete(sceneName);
    }
  }

  /** Checked scenes in outline / file declaration order. */
  getCheckedScenes(filePath: string): string[] {
    const checked = this.concatChecked.get(filePath);
    if (!checked?.size) {
      return [];
    }
    const outline = this.cache.get(filePath);
    if (!outline?.scenes.length) {
      return [...checked];
    }
    return outline.scenes
      .map((s) => s.name)
      .filter((name) => checked.has(name));
  }

  async selectAllScenesForConcat(filePath?: string): Promise<number> {
    const path = filePath ?? this.lastFilePath;
    if (!path) {
      return 0;
    }
    const outline = await this.loadOutline(path);
    const set = new Set(outline.scenes.map((s) => s.name));
    this.concatChecked.set(path, set);
    this._onDidChangeTreeData.fire(undefined);
    return set.size;
  }

  clearConcatSelection(filePath?: string): void {
    const path = filePath ?? this.lastFilePath;
    if (!path) {
      this.concatChecked.clear();
    } else {
      this.concatChecked.delete(path);
    }
    this._onDidChangeTreeData.fire(undefined);
  }

  /** Drop checks for scenes that no longer exist after a refresh/load. */
  private pruneConcatSelection(filePath: string, outline: FileOutline): void {
    const set = this.concatChecked.get(filePath);
    if (!set?.size) {
      return;
    }
    const live = new Set(outline.scenes.map((s) => s.name));
    for (const name of [...set]) {
      if (!live.has(name)) {
        set.delete(name);
      }
    }
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
      this.pruneConcatSelection(element.filePath, element.outline);
      return element.outline.scenes.map(
        (scene) =>
          new SceneNode(
            element.filePath,
            scene,
            this.isSceneChecked(element.filePath, scene.name)
          )
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
      this.pruneConcatSelection(filePath, outline);
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

export async function revealRange(
  filePath: string,
  range: SourceRange,
  options?: { preserveFocus?: boolean; preview?: boolean }
): Promise<void> {
  const doc = await vscode.workspace.openTextDocument(filePath);
  // Prefer an existing text-editor column for this file so Stage/Timeline
  // webviews are not replaced when selection sync jumps to source.
  let column: vscode.ViewColumn | undefined;
  for (const ed of vscode.window.visibleTextEditors) {
    if (ed.document.uri.fsPath === filePath && ed.viewColumn != null) {
      column = ed.viewColumn;
      break;
    }
  }
  if (column == null) {
    column =
      vscode.window.activeTextEditor?.viewColumn ?? vscode.ViewColumn.One;
  }
  const editor = await vscode.window.showTextDocument(doc, {
    viewColumn: column,
    preserveFocus: options?.preserveFocus ?? false,
    preview: options?.preview ?? true,
  });
  const start = new vscode.Position(Math.max(0, range.start_line - 1), 0);
  const endLine = Math.max(range.start_line, range.end_line) - 1;
  const end = doc.lineAt(Math.min(endLine, doc.lineCount - 1)).range.end;
  editor.selection = new vscode.Selection(start, start);
  editor.revealRange(
    new vscode.Range(start, end),
    vscode.TextEditorRevealType.InCenter
  );
}
