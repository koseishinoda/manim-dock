import * as fs from "fs";
import * as path from "path";
import * as vscode from "vscode";
import {
  asMethodTarget,
  asSceneTarget,
  OutlineProvider,
  revealRange,
} from "./outlineTree";
import { ProposedPatchProvider } from "./patchConfirm";
import { PreviewPanel } from "./previewPanel";
import { RenderOptions, SidecarClient, SourceRange } from "./sidecar";
import { StageTimelinePanel } from "./stageTimelinePanel";

const SIDEVIEW_EXT_ID = "Rickaym.manim-sideview";
const SIDEVIEW_RUN_CMD = "manim-sideview.run";
const SIDEVIEW_MARKETPLACE =
  "https://marketplace.visualstudio.com/items?itemName=Rickaym.manim-sideview";

export function activate(context: vscode.ExtensionContext): void {
  const sidecar = new SidecarClient(context.extensionPath);
  const output = vscode.window.createOutputChannel("Manim Dock");
  const outlineProvider = new OutlineProvider(sidecar, output);
  const outlineTree = vscode.window.createTreeView("manimDock.outline", {
    treeDataProvider: outlineProvider,
    showCollapseAll: true,
  });
  ProposedPatchProvider.ensure(context);
  const patchModeStatus = vscode.window.createStatusBarItem(
    vscode.StatusBarAlignment.Right,
    90
  );
  patchModeStatus.command = "manimDock.setPatchMode";
  patchModeStatus.tooltip = "Manim Dock: Set Patch Mode (confirm | auto)";
  const refreshPatchModeStatus = (): void => {
    const mode =
      vscode.workspace.getConfiguration("manimDock").get<string>("patchMode") ||
      "confirm";
    patchModeStatus.text = `$(edit) Patch: ${mode}`;
    patchModeStatus.show();
  };
  refreshPatchModeStatus();

  context.subscriptions.push(
    output,
    patchModeStatus,
    outlineTree,
    vscode.commands.registerCommand("manimDock.refreshOutline", () => {
      output.appendLine("Refreshing outline…");
      outlineProvider.refresh();
    }),
    vscode.commands.registerCommand(
      "manimDock.revealInEditor",
      async (filePath: string, range: SourceRange) => {
        await revealRange(filePath, range);
      }
    ),
    vscode.commands.registerCommand("manimDock.debugSidecar", async () => {
      const editor = vscode.window.activeTextEditor;
      const sample =
        editor?.document.languageId === "python"
          ? editor.document.uri.fsPath
          : vscode.workspace.workspaceFolders?.[0]
            ? `${vscode.workspace.workspaceFolders[0].uri.fsPath}/examples/minimal_lesson/lesson.py`
            : undefined;
      const report = await sidecar.debugReport(sample);
      output.clear();
      output.appendLine(report);
      output.show(true);
      const doc = await vscode.workspace.openTextDocument({
        content: report + "\n",
        language: "plaintext",
      });
      await vscode.window.showTextDocument(doc, { preview: true });
    }),
    vscode.commands.registerCommand(
      "manimDock.renderScene",
      async (item?: unknown) => {
        await renderSceneCommand(sidecar, outlineProvider, output, item);
      }
    ),
    vscode.commands.registerCommand(
      "manimDock.renderWithSections",
      async (item?: unknown) => {
        await renderSceneCommand(sidecar, outlineProvider, output, item, {
          saveSections: true,
          titleSuffix: " (sections)",
        });
      }
    ),
    vscode.commands.registerCommand(
      "manimDock.renderSkipToSection",
      async (item?: unknown) => {
        await renderSkipToSectionCommand(
          sidecar,
          outlineProvider,
          output,
          item
        );
      }
    ),
    vscode.commands.registerCommand(
      "manimDock.openStageTimeline",
      async (item?: unknown) => {
        await openStageTimelineCommand(
          context,
          sidecar,
          outlineProvider,
          outlineTree,
          output,
          item
        );
      }
    ),
    vscode.commands.registerCommand("manimDock.insertTemplate", async () => {
      await insertTemplateCommand(context);
    }),
    vscode.commands.registerCommand("manimDock.scaffoldExample", async () => {
      await scaffoldExampleCommand(context, output);
    }),
    vscode.commands.registerCommand("manimDock.setPatchMode", async () => {
      const current =
        vscode.workspace.getConfiguration("manimDock").get<string>("patchMode") ||
        "confirm";
      const picked = await vscode.window.showQuickPick(
        [
          {
            label: "confirm",
            description: "Show confirm-diff, then Apply / Cancel (default)",
            picked: current === "confirm",
          },
          {
            label: "auto",
            description: "Apply immediately; Undo with Ctrl/Cmd+Z",
            picked: current === "auto",
          },
        ],
        {
          placeHolder: `Current: ${current}`,
          title: "Manim Dock: Set Patch Mode",
        }
      );
      if (!picked) {
        return;
      }
      await vscode.workspace
        .getConfiguration("manimDock")
        .update("patchMode", picked.label, vscode.ConfigurationTarget.Global);
      refreshPatchModeStatus();
      void vscode.window.showInformationMessage(
        `Manim Dock: patchMode = ${picked.label}`
      );
    }),
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (e.affectsConfiguration("manimDock.patchMode")) {
        refreshPatchModeStatus();
      }
    }),
    vscode.commands.registerCommand(
      "manimDock.extractMethod",
      async (item?: unknown) => {
        await extractMethodCommand(
          context,
          sidecar,
          outlineProvider,
          output,
          item
        );
      }
    ),
    vscode.commands.registerCommand("manimDock.browseLibrary", async () => {
      await browseLibraryCommand(context, sidecar, output);
    }),
    vscode.commands.registerCommand(
      "manimDock.renderMethod",
      async (item?: unknown) => {
        await renderMethodCommand(sidecar, outlineProvider, output, item);
      }
    ),
    vscode.commands.registerCommand("manimDock.openInSideview", async () => {
      await openInSideviewCommand();
    }),
    vscode.window.onDidChangeActiveTextEditor((editor) => {
      if (editor?.document.languageId === "python") {
        outlineProvider.refresh();
        syncSurfacesToEditor(editor);
      }
    }),
    vscode.window.onDidChangeTextEditorSelection((e) => {
      if (e.textEditor.document.languageId === "python") {
        syncSurfacesToEditor(e.textEditor);
      }
    }),
    vscode.workspace.onDidSaveTextDocument((doc) => {
      if (doc.languageId === "python") {
        outlineProvider.refresh();
        StageTimelinePanel.refreshIfOpen(doc.uri.fsPath);
      }
    })
  );
}

function syncSurfacesToEditor(editor: vscode.TextEditor): void {
  const filePath = editor.document.uri.fsPath;
  const line = editor.selection.active.line + 1; // 1-based for sidecar ranges
  StageTimelinePanel.highlightLine(filePath, line);
}

async function openInSideviewCommand(): Promise<void> {
  const ext = vscode.extensions.getExtension(SIDEVIEW_EXT_ID);
  if (!ext) {
    const pick = await vscode.window.showInformationMessage(
      "Manim Sideview is not installed. Install it for a richer Manim preview player (Dock keeps Stage + Timeline).",
      "Open Marketplace",
      "Dismiss"
    );
    if (pick === "Open Marketplace") {
      await vscode.env.openExternal(vscode.Uri.parse(SIDEVIEW_MARKETPLACE));
    }
    return;
  }

  if (!ext.isActive) {
    try {
      await ext.activate();
    } catch (err) {
      void vscode.window.showWarningMessage(
        `Manim Dock: could not activate Sideview: ${String(err)}`
      );
    }
  }

  const editor = vscode.window.activeTextEditor;
  if (editor?.document.languageId === "python") {
    // Ensure Sideview sees the current file as active.
    await vscode.window.showTextDocument(editor.document, {
      preserveFocus: false,
      preview: false,
    });
  } else {
    void vscode.window.showInformationMessage(
      "Manim Dock: open a Python scene file, then run Open in Sideview again."
    );
  }

  try {
    await vscode.commands.executeCommand(SIDEVIEW_RUN_CMD);
  } catch {
    void vscode.window.showInformationMessage(
      `Manim Sideview is installed. Run “Manim: Runs a Sideview” (${SIDEVIEW_RUN_CMD}) from the Command Palette to preview the current scene.`
    );
  }
}

async function resolveSceneTarget(
  outlineProvider: OutlineProvider,
  output: vscode.OutputChannel,
  item?: unknown,
  outlineTree?: vscode.TreeView<unknown>
): Promise<{ filePath: string; sceneName: string } | undefined> {
  const fromArg = asSceneTarget(item);
  if (fromArg) {
    return fromArg;
  }
  // Toolbar / palette: use Outline selection (scene or method under a scene).
  if (outlineTree) {
    for (const sel of outlineTree.selection) {
      const fromSel = asSceneTarget(sel);
      if (fromSel) {
        return fromSel;
      }
    }
  }
  const resolved = await outlineProvider.resolvePythonOutline();
  if ("error" in resolved) {
    output.appendLine(resolved.error);
    void vscode.window.showErrorMessage(`Manim Dock: ${resolved.error}`);
    return undefined;
  }
  if (resolved.outline.scenes.length === 1) {
    return {
      filePath: resolved.filePath,
      sceneName: resolved.outline.scenes[0].name,
    };
  }
  const picked = await vscode.window.showQuickPick(
    resolved.outline.scenes.map((s) => s.name),
    { placeHolder: "Select a Scene" }
  );
  if (!picked) {
    return undefined;
  }
  return { filePath: resolved.filePath, sceneName: picked };
}

async function openStageTimelineCommand(
  context: vscode.ExtensionContext,
  sidecar: SidecarClient,
  outlineProvider: OutlineProvider,
  outlineTree: vscode.TreeView<unknown>,
  output: vscode.OutputChannel,
  item?: unknown
): Promise<void> {
  const target = await resolveSceneTarget(
    outlineProvider,
    output,
    item,
    outlineTree
  );
  if (!target) {
    return;
  }
  output.appendLine(
    `\n=== Stage & Timeline ${target.sceneName} (${target.filePath}) ===`
  );
  try {
    await vscode.window.withProgress(
      {
        location: vscode.ProgressLocation.Notification,
        title: `Manim Dock: opening Stage & Timeline — ${target.sceneName}`,
      },
      async () => {
        await StageTimelinePanel.open(
          context,
          sidecar,
          output,
          target.filePath,
          target.sceneName
        );
      }
    );
  } catch (err) {
    output.appendLine(`[stage-timeline] open failed: ${String(err)}`);
    void vscode.window.showErrorMessage(
      `Manim Dock: could not open Stage & Timeline: ${String(err)}`
    );
  }
}

async function insertTemplateCommand(
  context: vscode.ExtensionContext
): Promise<void> {
  const templatesDir = path.join(context.extensionPath, "templates");
  const choices = [
    { label: "basic_scene", description: "Single Scene construct skeleton" },
    {
      label: "multi_section_scene",
      description: "Scene with next_section beats",
    },
    {
      label: "multi_scene_project",
      description: "Multiple Scene classes in one file",
    },
  ];
  const picked = await vscode.window.showQuickPick(choices, {
    placeHolder: "Insert Manim Dock template",
  });
  if (!picked) {
    return;
  }
  const filePath = path.join(templatesDir, `${picked.label}.py`);
  if (!fs.existsSync(filePath)) {
    void vscode.window.showErrorMessage(
      `Manim Dock: template not found: ${filePath}`
    );
    return;
  }
  const content = fs.readFileSync(filePath, "utf8");
  const doc = await vscode.workspace.openTextDocument({
    content,
    language: "python",
  });
  await vscode.window.showTextDocument(doc);
}

async function scaffoldExampleCommand(
  context: vscode.ExtensionContext,
  output: vscode.OutputChannel
): Promise<void> {
  const lessonSrc = path.join(
    context.extensionPath,
    "examples",
    "minimal_lesson"
  );
  if (!fs.existsSync(path.join(lessonSrc, "lesson.py"))) {
    void vscode.window.showErrorMessage(
      `Manim Dock: examples/minimal_lesson not found under ${context.extensionPath}`
    );
    return;
  }

  let destDir: string | undefined;
  const folders = await vscode.window.showOpenDialog({
    canSelectFiles: false,
    canSelectFolders: true,
    canSelectMany: false,
    openLabel: "Scaffold into folder",
    title: "Choose destination for minimal_lesson",
  });
  if (folders?.[0]) {
    destDir = folders[0].fsPath;
  } else if (vscode.workspace.workspaceFolders?.[0]) {
    destDir = path.join(
      vscode.workspace.workspaceFolders[0].uri.fsPath,
      "minimal_lesson"
    );
  }
  if (!destDir) {
    void vscode.window.showWarningMessage(
      "Manim Dock: no destination folder selected."
    );
    return;
  }

  fs.mkdirSync(destDir, { recursive: true });
  for (const name of ["lesson.py", "README.md"]) {
    const src = path.join(lessonSrc, name);
    if (!fs.existsSync(src)) {
      continue;
    }
    const dest = path.join(destDir, name);
    if (fs.existsSync(dest)) {
      const overwrite = await vscode.window.showWarningMessage(
        `${name} already exists in ${destDir}. Overwrite?`,
        "Overwrite",
        "Skip"
      );
      if (overwrite !== "Overwrite") {
        continue;
      }
    }
    fs.copyFileSync(src, dest);
  }
  output.appendLine(`[scaffold] copied minimal_lesson → ${destDir}`);
  void vscode.window.showInformationMessage(
    `Manim Dock: scaffolded example into ${destDir}`
  );
  const lessonPath = path.join(destDir, "lesson.py");
  if (fs.existsSync(lessonPath)) {
    const doc = await vscode.workspace.openTextDocument(lessonPath);
    await vscode.window.showTextDocument(doc);
  }
}

async function resolveLibraryPath(
  context: vscode.ExtensionContext
): Promise<string | undefined> {
  const candidates: string[] = [];
  for (const folder of vscode.workspace.workspaceFolders ?? []) {
    const root = folder.uri.fsPath;
    candidates.push(
      path.join(root, "lesson_lib", "patterns.py"),
      path.join(root, "examples", "lesson_lib", "patterns.py"),
      path.join(root, "lesson_lib.py")
    );
  }
  candidates.push(
    path.join(
      context.extensionPath,
      "examples",
      "lesson_lib",
      "patterns.py"
    )
  );
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }
  const picked = await vscode.window.showOpenDialog({
    canSelectFiles: true,
    canSelectFolders: false,
    canSelectMany: false,
    filters: { Python: ["py"] },
    openLabel: "Choose library module",
    title: "Manim Dock: library .py for browse",
  });
  return picked?.[0]?.fsPath;
}

async function browseLibraryCommand(
  context: vscode.ExtensionContext,
  sidecar: SidecarClient,
  output: vscode.OutputChannel
): Promise<void> {
  const libraryPath = await resolveLibraryPath(context);
  if (!libraryPath) {
    void vscode.window.showWarningMessage(
      "Manim Dock: no lesson_lib/patterns.py found."
    );
    return;
  }

  let helpers;
  try {
    helpers = await sidecar.libraryCatalog(libraryPath);
  } catch (err) {
    void vscode.window.showErrorMessage(
      `Manim Dock library catalog failed: ${String(err)}`
    );
    return;
  }
  if (!helpers.length) {
    void vscode.window.showWarningMessage(
      `Manim Dock: no helpers found in ${libraryPath}`
    );
    return;
  }

  const picked = await vscode.window.showQuickPick(
    helpers.map((h) => ({
      label: h.name,
      description: h.signature,
      detail: h.doc || undefined,
      insert: h.insert,
    })),
    { placeHolder: `Insert helper from ${path.basename(libraryPath)}` }
  );
  if (!picked) {
    return;
  }

  const editor = vscode.window.activeTextEditor;
  if (!editor || editor.document.languageId !== "python") {
    void vscode.window.showWarningMessage(
      "Manim Dock: open a Python editor to insert a library helper."
    );
    return;
  }

  // Snippet-style $0 → cursor; insert as plain text at the cursor.
  const text = picked.insert.replace(/\$0/g, "");
  const pos = editor.selection.active;
  await editor.edit((builder) => {
    builder.insert(pos, text);
  });
  output.appendLine(`[library] inserted ${picked.label} from ${libraryPath}`);
}

async function resolveMethodTarget(
  outlineProvider: OutlineProvider,
  output: vscode.OutputChannel,
  item?: unknown
): Promise<
  { filePath: string; sceneName: string; methodName: string } | undefined
> {
  const fromTree = asMethodTarget(item);
  if (fromTree) {
    return fromTree;
  }

  const resolved = await outlineProvider.resolvePythonOutline();
  if ("error" in resolved) {
    output.appendLine(resolved.error);
    void vscode.window.showErrorMessage(`Manim Dock: ${resolved.error}`);
    return undefined;
  }

  const editor = vscode.window.activeTextEditor;
  const cursorLine =
    editor?.document.uri.fsPath === resolved.filePath
      ? editor.selection.active.line + 1
      : undefined;

  type MethodChoice = {
    label: string;
    description: string;
    sceneName: string;
    methodName: string;
  };
  const choices: MethodChoice[] = [];
  for (const scene of resolved.outline.scenes) {
    for (const method of scene.methods) {
      if (method.name === "construct") {
        continue;
      }
      choices.push({
        label: method.name,
        description: scene.name,
        sceneName: scene.name,
        methodName: method.name,
      });
    }
  }
  if (!choices.length) {
    void vscode.window.showWarningMessage(
      "Manim Dock: no non-construct methods found on the active scene file."
    );
    return undefined;
  }

  if (cursorLine !== undefined) {
    for (const scene of resolved.outline.scenes) {
      for (const method of scene.methods) {
        if (method.name === "construct") {
          continue;
        }
        if (
          method.range.start_line <= cursorLine &&
          cursorLine <= method.range.end_line
        ) {
          return {
            filePath: resolved.filePath,
            sceneName: scene.name,
            methodName: method.name,
          };
        }
      }
    }
  }

  if (choices.length === 1) {
    return {
      filePath: resolved.filePath,
      sceneName: choices[0].sceneName,
      methodName: choices[0].methodName,
    };
  }

  const picked = await vscode.window.showQuickPick(choices, {
    placeHolder: "Select a method to render",
  });
  if (!picked) {
    return undefined;
  }
  return {
    filePath: resolved.filePath,
    sceneName: picked.sceneName,
    methodName: picked.methodName,
  };
}

async function renderMethodCommand(
  sidecar: SidecarClient,
  outlineProvider: OutlineProvider,
  output: vscode.OutputChannel,
  item?: unknown
): Promise<void> {
  const target = await resolveMethodTarget(outlineProvider, output, item);
  if (!target) {
    return;
  }
  await renderSceneCommand(
    sidecar,
    outlineProvider,
    output,
    {
      filePath: target.filePath,
      scene: { name: target.sceneName },
    },
    {
      method: target.methodName,
      titleSuffix: ` · ${target.methodName}()`,
    }
  );
}

async function extractMethodCommand(
  context: vscode.ExtensionContext,
  sidecar: SidecarClient,
  outlineProvider: OutlineProvider,
  output: vscode.OutputChannel,
  item?: unknown
): Promise<void> {
  let filePath: string | undefined;
  let sceneName: string | undefined;
  let methodName: string | undefined;

  const fromTree = asMethodTarget(item);
  if (fromTree) {
    filePath = fromTree.filePath;
    sceneName = fromTree.sceneName;
    methodName = fromTree.methodName;
  } else {
    const target = await resolveSceneTarget(outlineProvider, output, item);
    if (!target) {
      return;
    }
    filePath = target.filePath;
    sceneName = target.sceneName;
    const resolved = await outlineProvider.resolvePythonOutline();
    if ("error" in resolved) {
      return;
    }
    const scene = resolved.outline.scenes.find((s) => s.name === sceneName);
    const methods = (scene?.methods ?? [])
      .map((m) => m.name)
      .filter((n) => n !== "construct");
    if (!methods.length) {
      void vscode.window.showErrorMessage(
        "Manim Dock: no extractable methods on this scene."
      );
      return;
    }
    const picked = await vscode.window.showQuickPick(methods, {
      placeHolder: "Select a method to extract to a library module",
    });
    if (!picked) {
      return;
    }
    methodName = picked;
  }

  if (!filePath || !sceneName || !methodName) {
    return;
  }

  const defaultLib = path.join(
    path.dirname(filePath),
    "..",
    "lesson_lib",
    "extracted.py"
  );
  const libUri = await vscode.window.showSaveDialog({
    defaultUri: vscode.Uri.file(defaultLib),
    filters: { Python: ["py"] },
    saveLabel: "Extract to library",
    title: "Library module for extracted helper",
  });
  if (!libUri) {
    return;
  }

  const sceneDoc = await vscode.workspace.openTextDocument(filePath);
  let librarySource: string | null = null;
  try {
    const libDoc = await vscode.workspace.openTextDocument(libUri);
    librarySource = libDoc.getText();
  } catch {
    librarySource = null;
  }

  let proposal;
  try {
    proposal = await sidecar.extractMethod(
      filePath,
      sceneName,
      methodName,
      libUri.fsPath,
      sceneDoc.getText(),
      librarySource
    );
  } catch (err) {
    void vscode.window.showErrorMessage(
      `Manim Dock extract failed: ${String(err)}`
    );
    return;
  }

  if (!proposal.ok) {
    void vscode.window.showWarningMessage(
      `Manim Dock: ${proposal.error ?? "extract failed"}`
    );
    return;
  }

  output.appendLine(`\n=== Extract ${proposal.summary} ===`);
  output.appendLine(proposal.library_diff);
  output.appendLine(proposal.scene_diff);

  const choice = await vscode.window.showInformationMessage(
    `Extract ${methodName} to library?\n${proposal.summary}`,
    { modal: true, detail: truncate(proposal.library_diff + "\n" + proposal.scene_diff, 1400) },
    "Apply",
    "Cancel"
  );
  if (choice !== "Apply") {
    return;
  }

  // Write library module (create if needed), then apply scene patch.
  if (!(await fileExists(libUri))) {
    const create = new vscode.WorkspaceEdit();
    create.createFile(libUri, { ignoreIfExists: true });
    await vscode.workspace.applyEdit(create);
  }
  await vscode.workspace.fs.writeFile(
    libUri,
    Buffer.from(proposal.library_proposed, "utf8")
  );

  const sceneUri = vscode.Uri.file(filePath);
  const current = sceneDoc.getText();
  if (current !== proposal.scene_original) {
    void vscode.window.showErrorMessage(
      "Manim Dock: scene changed during extract. Library was written; re-run extract for the scene call."
    );
    return;
  }
  const sceneEdit = new vscode.WorkspaceEdit();
  const end = sceneDoc.lineAt(sceneDoc.lineCount - 1).range.end;
  sceneEdit.replace(
    sceneUri,
    new vscode.Range(new vscode.Position(0, 0), end),
    proposal.scene_proposed
  );
  const ok = await vscode.workspace.applyEdit(sceneEdit);
  if (!ok) {
    void vscode.window.showErrorMessage(
      "Manim Dock: library written, but scene edit failed."
    );
    return;
  }
  await sceneDoc.save();
  output.appendLine(`[extract] applied ${proposal.summary}`);
  outlineProvider.refresh();
  void vscode.window.showInformationMessage(
    `Manim Dock: extracted ${methodName} → ${libUri.fsPath}`
  );
}

function truncate(text: string, max: number): string {
  if (text.length <= max) {
    return text;
  }
  return text.slice(0, max) + "\n…";
}

async function fileExists(uri: vscode.Uri): Promise<boolean> {
  try {
    await vscode.workspace.fs.stat(uri);
    return true;
  } catch {
    return false;
  }
}

async function renderSkipToSectionCommand(
  sidecar: SidecarClient,
  outlineProvider: OutlineProvider,
  output: vscode.OutputChannel,
  item?: unknown
): Promise<void> {
  const target = await resolveSceneTarget(outlineProvider, output, item);
  if (!target) {
    return;
  }
  const resolved = await outlineProvider.resolvePythonOutline();
  if ("error" in resolved) {
    void vscode.window.showErrorMessage(`Manim Dock: ${resolved.error}`);
    return;
  }
  const scene = resolved.outline.scenes.find((s) => s.name === target.sceneName);
  /** Bare Manim section names (not Outline display labels). */
  const sections: string[] = [];
  const seen = new Set<string>();
  for (const method of scene?.methods ?? []) {
    for (const ev of method.events) {
      if (ev.kind !== "next_section") {
        continue;
      }
      const name = sectionNameFromOutlineEvent(ev.label);
      if (!name || seen.has(name)) {
        continue;
      }
      seen.add(name);
      sections.push(name);
    }
  }
  if (!sections.length) {
    void vscode.window.showWarningMessage(
      "Manim Dock: no self.next_section(\"…\") markers in this scene. " +
        "Skip-to-section needs next_section chapters (Skill multi-scene files: render the Scene class instead)."
    );
    return;
  }
  const picked = await vscode.window.showQuickPick(sections, {
    placeHolder: "Skip animations until this section, then render",
  });
  if (!picked) {
    return;
  }
  await renderSceneCommand(
    sidecar,
    outlineProvider,
    output,
    { filePath: target.filePath, scene: { name: target.sceneName } },
    {
      skipUntilSection: picked,
      titleSuffix: ` (skip → ${picked})`,
    }
  );
}

/**
 * Outline labels look like `self.next_section('Title')`; render expects bare `Title`.
 */
function sectionNameFromOutlineEvent(label: string | undefined): string | undefined {
  if (!label) {
    return undefined;
  }
  const m = label.match(
    /next_section\s*\(\s*(?:name\s*=\s*)?(['"])(.*?)\1/
  );
  if (m?.[2]) {
    return m[2];
  }
  // Already a bare name (e.g. from Timeline).
  if (!label.includes("(") && label.trim()) {
    return label.trim();
  }
  return undefined;
}

async function renderSceneCommand(
  sidecar: SidecarClient,
  outlineProvider: OutlineProvider,
  output: vscode.OutputChannel,
  item?: unknown,
  options?: RenderOptions & { titleSuffix?: string }
): Promise<void> {
  const target = await resolveSceneTarget(outlineProvider, output, item);
  if (!target) {
    return;
  }
  const { filePath, sceneName } = target;

  const quality =
    vscode.workspace.getConfiguration("manimDock").get<string>("renderQuality") ||
    "l";

  const suffix = options?.titleSuffix ?? "";
  const renderOpts: RenderOptions | undefined =
    options?.saveSections || options?.skipUntilSection || options?.method
      ? {
          saveSections: options.saveSections,
          skipUntilSection: options.skipUntilSection,
          method: options.method,
        }
      : undefined;

  output.show(true);
  output.appendLine(
    `\n=== Render ${sceneName}${suffix} (${filePath}) quality=${quality}` +
      (renderOpts?.saveSections ? " save_sections" : "") +
      (renderOpts?.skipUntilSection
        ? ` skip_until=${renderOpts.skipUntilSection}`
        : "") +
      (renderOpts?.method ? ` method=${renderOpts.method}` : "") +
      " ==="
  );

  await vscode.window.withProgress(
    {
      location: vscode.ProgressLocation.Notification,
      title: `Manim Dock: rendering ${sceneName}${suffix}…`,
      cancellable: false,
    },
    async () => {
      try {
        const result = await sidecar.render(
          filePath,
          sceneName,
          quality,
          (chunk) => {
            output.append(chunk);
          },
          renderOpts
        );
        if (result.log_tail) {
          output.appendLine("\n--- log tail ---");
          output.appendLine(result.log_tail);
        }
        if (!result.ok || !result.output_path) {
          void vscode.window.showErrorMessage(
            `Manim Dock render failed: ${result.error ?? "unknown error"}. See “Manim Dock” output.`
          );
          return;
        }
        PreviewPanel.show(result.output_path, sceneName);
        void vscode.window.showInformationMessage(
          `Manim Dock: rendered ${sceneName}${suffix}`
        );
      } catch (err) {
        output.appendLine(String(err));
        void vscode.window.showErrorMessage(
          `Manim Dock render failed: ${String(err)}. Check the Manim Dock output and your Python/Manim install.`
        );
      }
    }
  );
}

export function deactivate(): void {
  // no-op
}
