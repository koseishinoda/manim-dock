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
import { SidecarClient, SourceRange } from "./sidecar";
import { StagePanel } from "./stagePanel";
import { TimelinePanel } from "./timelinePanel";

export function activate(context: vscode.ExtensionContext): void {
  const sidecar = new SidecarClient(context.extensionPath);
  const output = vscode.window.createOutputChannel("Manim Dock");
  const outlineProvider = new OutlineProvider(sidecar, output);
  ProposedPatchProvider.ensure(context);

  context.subscriptions.push(
    output,
    vscode.window.registerTreeDataProvider("manimDock.outline", outlineProvider),
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
    vscode.commands.registerCommand("manimDock.doctor", async () => {
      try {
        const { probes } = await sidecar.doctor();
        const lines = probes.map(
          (p) => `${p.ok ? "OK" : "MISSING"}  ${p.name}: ${p.detail}`
        );
        const doc = await vscode.workspace.openTextDocument({
          content: ["Manim Dock Doctor", "", ...lines, ""].join("\n"),
          language: "plaintext",
        });
        await vscode.window.showTextDocument(doc, { preview: true });
      } catch (err) {
        void vscode.window.showErrorMessage(`Manim Dock doctor failed: ${String(err)}`);
      }
    }),
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
      "manimDock.openStage",
      async (item?: unknown) => {
        await openStageCommand(context, sidecar, outlineProvider, output, item);
      }
    ),
    vscode.commands.registerCommand(
      "manimDock.openTimeline",
      async (item?: unknown) => {
        await openTimelineCommand(context, sidecar, outlineProvider, output, item);
      }
    ),
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
        StagePanel.refreshIfOpen(doc.uri.fsPath);
        TimelinePanel.refreshIfOpen(doc.uri.fsPath);
      }
    })
  );
}

function syncSurfacesToEditor(editor: vscode.TextEditor): void {
  const filePath = editor.document.uri.fsPath;
  const line = editor.selection.active.line + 1; // 1-based for sidecar ranges
  StagePanel.highlightLine(filePath, line);
  TimelinePanel.highlightLine(filePath, line);
}

async function resolveSceneTarget(
  outlineProvider: OutlineProvider,
  output: vscode.OutputChannel,
  item?: unknown
): Promise<{ filePath: string; sceneName: string } | undefined> {
  const fromTree = asSceneTarget(item);
  if (fromTree) {
    return fromTree;
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

async function openStageCommand(
  context: vscode.ExtensionContext,
  sidecar: SidecarClient,
  outlineProvider: OutlineProvider,
  output: vscode.OutputChannel,
  item?: unknown
): Promise<void> {
  const target = await resolveSceneTarget(outlineProvider, output, item);
  if (!target) {
    return;
  }
  output.appendLine(`\n=== Stage ${target.sceneName} (${target.filePath}) ===`);
  await StagePanel.open(
    context,
    sidecar,
    output,
    target.filePath,
    target.sceneName
  );
}

async function openTimelineCommand(
  context: vscode.ExtensionContext,
  sidecar: SidecarClient,
  outlineProvider: OutlineProvider,
  output: vscode.OutputChannel,
  item?: unknown
): Promise<void> {
  const target = await resolveSceneTarget(outlineProvider, output, item);
  if (!target) {
    return;
  }
  output.appendLine(
    `\n=== Timeline ${target.sceneName} (${target.filePath}) ===`
  );
  await TimelinePanel.open(
    context,
    sidecar,
    output,
    target.filePath,
    target.sceneName
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

async function renderSceneCommand(
  sidecar: SidecarClient,
  outlineProvider: OutlineProvider,
  output: vscode.OutputChannel,
  item?: unknown
): Promise<void> {
  const target = await resolveSceneTarget(outlineProvider, output, item);
  if (!target) {
    return;
  }
  const { filePath, sceneName } = target;

  const quality =
    vscode.workspace.getConfiguration("manimDock").get<string>("renderQuality") ||
    "l";

  output.show(true);
  output.appendLine(`\n=== Render ${sceneName} (${filePath}) quality=${quality} ===`);

  await vscode.window.withProgress(
    {
      location: vscode.ProgressLocation.Notification,
      title: `Manim Dock: rendering ${sceneName}…`,
      cancellable: false,
    },
    async () => {
      try {
        const result = await sidecar.render(filePath, sceneName, quality, (chunk) => {
          output.append(chunk);
        });
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
          `Manim Dock: rendered ${sceneName}`
        );
      } catch (err) {
        output.appendLine(String(err));
        void vscode.window.showErrorMessage(
          `Manim Dock render failed: ${String(err)}. Run Doctor if manim is missing.`
        );
      }
    }
  );
}

export function deactivate(): void {
  // no-op
}
