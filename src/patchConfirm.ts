import * as vscode from "vscode";

export interface PendingPatch {
  path: string;
  original: string;
  proposed: string;
  summary: string;
  diff: string;
}

/**
 * Shared confirm-diff + WorkspaceEdit apply for Stage / Timeline patches.
 */
export class ProposedPatchProvider implements vscode.TextDocumentContentProvider {
  static readonly scheme = "manim-dock-proposed";
  private static instance: ProposedPatchProvider | undefined;
  private content = new Map<string, string>();
  private _onDidChange = new vscode.EventEmitter<vscode.Uri>();
  readonly onDidChange = this._onDidChange.event;

  static ensure(context: vscode.ExtensionContext): ProposedPatchProvider {
    if (!ProposedPatchProvider.instance) {
      ProposedPatchProvider.instance = new ProposedPatchProvider();
      context.subscriptions.push(
        vscode.workspace.registerTextDocumentContentProvider(
          ProposedPatchProvider.scheme,
          ProposedPatchProvider.instance
        )
      );
    }
    return ProposedPatchProvider.instance;
  }

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

export async function confirmAndApplyPatch(
  context: vscode.ExtensionContext,
  pending: PendingPatch,
  output: vscode.OutputChannel,
  channel: string
): Promise<boolean> {
  const provider = ProposedPatchProvider.ensure(context);
  const proposedUri = provider.set(pending.path, pending.proposed);
  await vscode.commands.executeCommand(
    "vscode.diff",
    vscode.Uri.file(pending.path),
    proposedUri,
    `Manim Dock: ${pending.summary}`
  );

  const choice = await vscode.window.showInformationMessage(
    `Apply patch?\n${pending.summary}`,
    { modal: true, detail: truncate(pending.diff, 1200) },
    "Apply",
    "Cancel"
  );
  if (choice !== "Apply") {
    return false;
  }

  const uri = vscode.Uri.file(pending.path);
  const doc = await vscode.workspace.openTextDocument(uri);
  if (doc.getText() !== pending.original) {
    void vscode.window.showErrorMessage(
      "Manim Dock: file changed since the patch was proposed. Refresh and try again."
    );
    return false;
  }

  const edit = new vscode.WorkspaceEdit();
  const start = new vscode.Position(0, 0);
  const end = doc.lineAt(doc.lineCount - 1).range.end;
  edit.replace(uri, new vscode.Range(start, end), pending.proposed);
  const ok = await vscode.workspace.applyEdit(edit);
  if (!ok) {
    void vscode.window.showErrorMessage("Manim Dock: failed to apply patch edit.");
    return false;
  }
  await doc.save();
  output.appendLine(`[${channel}] applied ${pending.summary}`);
  void vscode.window.showInformationMessage(
    `Manim Dock: applied ${pending.summary}`
  );
  return true;
}

function truncate(text: string, max: number): string {
  if (text.length <= max) {
    return text;
  }
  return text.slice(0, max) + "\n…";
}
