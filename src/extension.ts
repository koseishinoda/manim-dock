import * as vscode from "vscode";
import {
  asSceneTarget,
  OutlineProvider,
  revealRange,
} from "./outlineTree";
import { PreviewPanel } from "./previewPanel";
import { SidecarClient, SourceRange } from "./sidecar";
import { StagePanel } from "./stagePanel";

export function activate(context: vscode.ExtensionContext): void {
  const sidecar = new SidecarClient(context.extensionPath);
  const output = vscode.window.createOutputChannel("Manim Dock");
  const outlineProvider = new OutlineProvider(sidecar, output);
  StagePanel.ensureProposedProvider(context);

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
    vscode.window.onDidChangeActiveTextEditor((editor) => {
      if (editor?.document.languageId === "python") {
        outlineProvider.refresh();
      }
    }),
    vscode.workspace.onDidSaveTextDocument((doc) => {
      if (doc.languageId === "python") {
        outlineProvider.refresh();
      }
    })
  );
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
