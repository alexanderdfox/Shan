const vscode = require("vscode");
const { execFile } = require("child_process");
const path = require("path");
const fs = require("fs");

/** @type {vscode.DiagnosticCollection} */
let diagnosticCollection;

function getConfig() {
  return vscode.workspace.getConfiguration("shan");
}

function findProjectRoot(docPath) {
  const configured = getConfig().get("projectRoot", "");
  if (configured && fs.existsSync(path.join(configured, "shan", "__main__.py"))) {
    return configured;
  }
  let dir = path.dirname(docPath);
  for (let i = 0; i < 12; i++) {
    if (fs.existsSync(path.join(dir, "shan", "__main__.py"))) {
      return dir;
    }
    const parent = path.dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return null;
}

function runShan(args, cwd) {
  const python = getConfig().get("pythonPath", "python3");
  return new Promise((resolve, reject) => {
    execFile(
      python,
      ["-m", "shan", ...args],
      { cwd, maxBuffer: 10 * 1024 * 1024 },
      (err, stdout, stderr) => {
        resolve({ err, stdout: stdout || "", stderr: stderr || "" });
      }
    );
  });
}

async function checkDocument(doc) {
  if (doc.languageId !== "shan") return;
  const root = findProjectRoot(doc.uri.fsPath);
  if (!root) {
    diagnosticCollection.set(
      doc.uri,
      [
        new vscode.Diagnostic(
          new vscode.Range(0, 0, 0, 1),
          "Cannot find Peacock project (shan/). Set shan.projectRoot.",
          vscode.DiagnosticSeverity.Warning
        ),
      ]
    );
    return;
  }
  const tmp = doc.isDirty;
  if (tmp) await doc.save();
  const { stdout } = await runShan(["check", doc.uri.fsPath, "--json"], root);
  let data;
  try {
    data = JSON.parse(stdout);
  } catch {
    diagnosticCollection.delete(doc.uri);
    return;
  }
  const diags = (data.diagnostics || []).map((d) => {
    const line = Math.max(0, (d.line || 1) - 1);
    const col = Math.max(0, (d.col || 1) - 1);
    const range = new vscode.Range(line, col, line, col + 1);
    const sev =
      d.severity === "warning"
        ? vscode.DiagnosticSeverity.Warning
        : d.severity === "info"
          ? vscode.DiagnosticSeverity.Information
          : vscode.DiagnosticSeverity.Error;
    return new vscode.Diagnostic(range, d.message, sev);
  });
  diagnosticCollection.set(doc.uri, diags);
}

async function formatDocument(doc) {
  const root = findProjectRoot(doc.uri.fsPath);
  if (!root) return [];
  await runShan(["fmt", "-w", doc.uri.fsPath], root);
  return [];
}

function activate(context) {
  diagnosticCollection = vscode.languages.createDiagnosticCollection("shan");
  context.subscriptions.push(diagnosticCollection);

  context.subscriptions.push(
    vscode.languages.registerDocumentFormattingEditProvider("shan", {
      provideDocumentFormattingEdits: async (doc) => {
        await formatDocument(doc);
        const text = fs.readFileSync(doc.uri.fsPath, "utf8");
        const full = new vscode.Range(doc.positionAt(0), doc.positionAt(doc.getText().length));
        return [vscode.TextEdit.replace(full, text)];
      },
    })
  );

  const checkHandler = (doc) => {
    if (doc && doc.languageId === "shan") checkDocument(doc);
  };

  context.subscriptions.push(
    vscode.workspace.onDidSaveTextDocument((doc) => {
      if (!getConfig().get("checkOnSave", true)) return;
      checkHandler(doc);
      if (getConfig().get("formatOnSave", false)) formatDocument(doc);
    }),
    vscode.workspace.onDidOpenTextDocument(checkHandler)
  );

  vscode.workspace.textDocuments.forEach(checkHandler);

  context.subscriptions.push(
    vscode.commands.registerCommand("shan.run", async () => {
      const ed = vscode.window.activeTextEditor;
      if (!ed) return;
      const root = findProjectRoot(ed.document.uri.fsPath);
      const { stderr } = await runShan(["run", ed.document.uri.fsPath], root || path.dirname(ed.document.uri.fsPath));
      const channel = vscode.window.createOutputChannel("Shàn");
      channel.appendLine(stderr || "Done.");
      channel.show();
    }),
    vscode.commands.registerCommand("shan.check", () => {
      const ed = vscode.window.activeTextEditor;
      if (ed) checkDocument(ed.document);
    }),
    vscode.commands.registerCommand("shan.compile", async () => {
      const ed = vscode.window.activeTextEditor;
      if (!ed) return;
      const root = findProjectRoot(ed.document.uri.fsPath);
      await runShan(["compile", ed.document.uri.fsPath, "--run"], root || path.dirname(ed.document.uri.fsPath));
    })
  );
}

function deactivate() {}

module.exports = { activate, deactivate };
