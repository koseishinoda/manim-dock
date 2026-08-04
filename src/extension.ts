import * as vscode from "vscode";
import { OutlineProvider, revealRange } from "./outlineTree";
import { SidecarClient, SourceRange } from "./sidecar";

export function activate(context: vscode.ExtensionContext): void {
  const sidecar = new SidecarClient(context.extensionPath);
  const outlineProvider = new OutlineProvider(sidecar);

  context.subscriptions.push(
    vscode.window.registerTreeDataProvider("manimDock.outline", outlineProvider),
    vscode.commands.registerCommand("manimDock.refreshOutline", () => {
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

export function deactivate(): void {
  // no-op
}
