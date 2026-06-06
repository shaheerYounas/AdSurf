import net from "node:net";
import path from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { readFileSync, writeFileSync } from "node:fs";

export const DEFAULT_WEB_DEV_PORT = 4310;
export const DEFAULT_API_DEV_PORT = 8720;
export const DEFAULT_DEV_HOST = "127.0.0.1";
export const COMMON_DEV_PORTS = new Set([3000, 3001, 3002, 5000, 5173, 8000, 8080]);

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, "..");

function parsePort(value, name) {
  if (value === undefined || value === null || value === "") return undefined;
  const parsed = Number.parseInt(value, 10);
  if (!Number.isInteger(parsed) || parsed < 1 || parsed > 65535) {
    throw new Error(`${name} must be a TCP port between 1 and 65535.`);
  }
  return parsed;
}

function envPort(names, fallback, env = process.env) {
  for (const name of names) {
    const port = parsePort(env[name], name);
    if (port !== undefined) {
      return { port, source: name };
    }
  }
  return { port: fallback, source: "default" };
}

function getPortPreferences(env = process.env) {
  return {
    host: env.DEV_HOST || env.HOST || DEFAULT_DEV_HOST,
    webPreference: envPort(["WEB_DEV_PORT", "PORT"], DEFAULT_WEB_DEV_PORT, env),
    apiPreference: envPort(["API_DEV_PORT", "FASTAPI_PORT"], DEFAULT_API_DEV_PORT, env),
  };
}

function localUrl(host, port) {
  return `http://${host}:${port}`;
}

function matchingLocalOrigins(origin) {
  const origins = new Set([origin]);
  try {
    const url = new URL(origin);
    if (url.hostname === "127.0.0.1") {
      url.hostname = "localhost";
      origins.add(url.origin);
    } else if (url.hostname === "localhost") {
      url.hostname = "127.0.0.1";
      origins.add(url.origin);
    }
  } catch {
    return [...origins];
  }
  return [...origins];
}

export async function isPortAvailable(port, host = DEFAULT_DEV_HOST) {
  return await new Promise((resolve) => {
    const server = net.createServer();
    server.unref();
    server.once("error", () => resolve(false));
    server.once("listening", () => {
      server.close(() => resolve(true));
    });
    server.listen({ host, port, exclusive: true });
  });
}

export async function findAvailablePort({
  preferredPort,
  host = DEFAULT_DEV_HOST,
  maxAttempts = 100,
  skipPorts = new Set(),
}) {
  for (let offset = 0; offset < maxAttempts; offset += 1) {
    const candidate = preferredPort + offset;
    if (candidate > 65535) break;
    if (skipPorts.has(candidate)) continue;
    if (await isPortAvailable(candidate, host)) {
      return candidate;
    }
  }

  throw new Error(`No available port found from ${preferredPort} after ${maxAttempts} attempts.`);
}

export async function chooseDevPorts(env = process.env) {
  const { host, webPreference, apiPreference } = getPortPreferences(env);
  const skipWebPorts = webPreference.source === "default" ? COMMON_DEV_PORTS : new Set();
  const skipApiPorts = apiPreference.source === "default" ? COMMON_DEV_PORTS : new Set();

  const apiPort = await findAvailablePort({
    preferredPort: apiPreference.port,
    host,
    skipPorts: skipApiPorts,
  });
  const webPort = await findAvailablePort({
    preferredPort: webPreference.port,
    host,
    skipPorts: new Set([...skipWebPorts, apiPort]),
  });

  return { host, apiPort, webPort };
}

export async function chooseRunConfig(mode, env = process.env) {
  const { host, webPreference, apiPreference } = getPortPreferences(env);

  if (mode === "all") {
    const ports = await chooseDevPorts(env);
    return {
      ...ports,
      apiBaseUrl: localUrl(ports.host, ports.apiPort),
      webAppUrl: localUrl(ports.host, ports.webPort),
    };
  }

  if (mode === "api") {
    const skipApiPorts = apiPreference.source === "default" ? COMMON_DEV_PORTS : new Set();
    const apiPort = await findAvailablePort({
      preferredPort: apiPreference.port,
      host,
      skipPorts: skipApiPorts,
    });
    return {
      host,
      apiPort,
      webPort: webPreference.port,
      apiBaseUrl: localUrl(host, apiPort),
      webAppUrl: env.WEB_APP_URL || localUrl(host, webPreference.port),
    };
  }

  const skipWebPorts = webPreference.source === "default" ? COMMON_DEV_PORTS : new Set();
  const webPort = await findAvailablePort({
    preferredPort: webPreference.port,
    host,
    skipPorts: skipWebPorts,
  });
  return {
    host,
    apiPort: apiPreference.port,
    webPort,
    apiBaseUrl: env.NEXT_PUBLIC_API_BASE_URL || env.API_BASE_URL || localUrl(host, apiPreference.port),
    webAppUrl: localUrl(host, webPort),
  };
}

function serviceEnv({ env = process.env, host, apiPort, webPort, apiBaseUrl, webAppUrl }) {
  return {
    api: {
      ...env,
      FASTAPI_HOST: host,
      FASTAPI_PORT: String(apiPort),
      API_BASE_URL: apiBaseUrl,
      WEB_APP_URL: webAppUrl,
      CORS_ALLOWED_ORIGINS: matchingLocalOrigins(webAppUrl).join(","),
    },
    web: {
      ...env,
      PORT: String(webPort),
      WEB_APP_URL: webAppUrl,
      API_BASE_URL: apiBaseUrl,
      NEXT_PUBLIC_API_BASE_URL: apiBaseUrl,
    },
  };
}

function writeEnvLocal(filePath, updates) {
  let lines = [];
  try {
    lines = readFileSync(filePath, "utf8").split("\n");
  } catch {
    // file doesn't exist yet — start fresh
  }
  for (const [key, value] of Object.entries(updates)) {
    const idx = lines.findIndex((l) => l.startsWith(`${key}=`) || l.startsWith(`# ${key}=`));
    const line = `${key}=${value}`;
    if (idx >= 0) {
      lines[idx] = line;
    } else {
      lines.push(line);
    }
  }
  writeFileSync(filePath, lines.join("\n"), "utf8");
}

function spawnService(name, command, args, options) {
  const child = spawn(command, args, {
    cwd: options.cwd,
    env: options.env,
    stdio: "inherit",
  });

  child.once("exit", (code, signal) => {
    if (options.onExit) {
      options.onExit(name, code, signal);
    }
  });

  return child;
}

function stopChildren(children) {
  for (const child of children) {
    if (!child.killed) {
      child.kill();
    }
  }
}

function printBanner({ mode, apiBaseUrl, webAppUrl }) {
  console.log(`\nAdSurf dev launcher (${mode})`);
  if (mode !== "api") console.log(`Web: ${webAppUrl}`);
  if (mode !== "web") console.log(`API: ${apiBaseUrl}`);
  console.log("Ports are selected before startup, so busy ports are skipped automatically.\n");
}

export async function run(mode, env = process.env) {
  if (!["all", "api", "web"].includes(mode)) {
    throw new Error(`Unknown dev service "${mode}". Use all, api, or web.`);
  }

  const { host, apiPort, webPort, apiBaseUrl, webAppUrl } = await chooseRunConfig(mode, env);
  const envByService = serviceEnv({ env, host, apiPort, webPort, apiBaseUrl, webAppUrl });
  const children = [];
  let shuttingDown = false;

  printBanner({ mode, apiBaseUrl, webAppUrl });

  // Persist resolved ports to .env.local so individual service restarts use the same URLs.
  const webEnvPath = path.join(repoRoot, "apps", "web", ".env.local");
  writeEnvLocal(webEnvPath, { NEXT_PUBLIC_API_BASE_URL: apiBaseUrl });

  const handleExit = (name, code, signal) => {
    if (shuttingDown) return;
    shuttingDown = true;
    if (code && code !== 0) {
      console.error(`${name} exited with code ${code}.`);
    } else if (signal) {
      console.error(`${name} exited after signal ${signal}.`);
    }
    stopChildren(children);
    process.exitCode = code ?? 0;
  };

  if (mode === "all" || mode === "api") {
    children.push(
      spawnService(
        "api",
        "python",
        ["-m", "uvicorn", "apps.api.app.main:app", "--reload", "--host", host, "--port", String(apiPort)],
        { cwd: repoRoot, env: envByService.api, onExit: handleExit },
      ),
    );
  }

  if (mode === "all" || mode === "web") {
    const nextCliPath = path.join(repoRoot, "node_modules", "next", "dist", "bin", "next");
    children.push(
      spawnService(
        "web",
        "node",
        [nextCliPath, "dev", "--hostname", host, "--port", String(webPort)],
        { cwd: path.join(repoRoot, "apps", "web"), env: envByService.web, onExit: handleExit },
      ),
    );
  }

  const shutdown = () => {
    shuttingDown = true;
    stopChildren(children);
  };
  process.once("SIGINT", shutdown);
  process.once("SIGTERM", shutdown);
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  run(process.argv[2] || "all").catch((error) => {
    console.error(error.message);
    process.exitCode = 1;
  });
}
