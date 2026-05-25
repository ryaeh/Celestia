/**
 * Start Celestia shell API on 127.0.0.1 if not already running (Vite / Tauri dev).
 */
import { spawn } from "node:child_process";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "../..");
const PORT = Number(process.env.CELESTIA_SHELL_PORT || 8765);
const PYTHON =
  process.platform === "win32"
    ? path.join(ROOT, "venv", "Scripts", "python.exe")
    : path.join(ROOT, "venv", "bin", "python3");

function ping(port) {
  return new Promise((resolve) => {
    const req = http.get(`http://127.0.0.1:${port}/status`, (res) => {
      resolve(res.statusCode === 200);
      res.resume();
    });
    req.on("error", () => resolve(false));
    req.setTimeout(800, () => {
      req.destroy();
      resolve(false);
    });
  });
}

function waitForApi(port, attempts = 40) {
  return new Promise((resolve) => {
    let n = 0;
    const tick = async () => {
      if (await ping(port)) {
        resolve(true);
        return;
      }
      n += 1;
      if (n >= attempts) {
        resolve(false);
        return;
      }
      setTimeout(tick, 250);
    };
    tick();
  });
}

async function main() {
  if (await ping(PORT)) {
    console.log(`[ensure-api] API already up on :${PORT}`);
    return;
  }

  const script = path.join(ROOT, "run_celestia.py");
  console.log(`[ensure-api] Starting Python API on :${PORT}…`);
  const child = spawn(PYTHON, [script, "--shell-server"], {
    cwd: ROOT,
    detached: true,
    stdio: "ignore",
    windowsHide: true,
  });
  child.unref();

  const ok = await waitForApi(PORT);
  if (!ok) {
    console.warn(
      `[ensure-api] API did not respond on :${PORT}. Run manually:\n` +
        `  ${PYTHON} run_celestia.py --shell-server`,
    );
    process.exit(0);
  }
  console.log(`[ensure-api] API ready http://127.0.0.1:${PORT}`);
}

main().catch((e) => {
  console.warn("[ensure-api]", e);
  process.exit(0);
});
