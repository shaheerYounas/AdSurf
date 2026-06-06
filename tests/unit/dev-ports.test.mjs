import assert from "node:assert/strict";
import net from "node:net";
import test from "node:test";

import {
  chooseRunConfig,
  chooseDevPorts,
  COMMON_DEV_PORTS,
  DEFAULT_DEV_HOST,
  findAvailablePort,
  isPortAvailable,
} from "../../scripts/dev-ports.mjs";

function listenOnRandomPort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once("error", reject);
    server.listen({ host: DEFAULT_DEV_HOST, port: 0 }, () => resolve(server));
  });
}

function closeServer(server) {
  return new Promise((resolve, reject) => {
    server.close((error) => {
      if (error) reject(error);
      else resolve();
    });
  });
}

test("isPortAvailable returns false for an occupied port", async () => {
  const server = await listenOnRandomPort();
  const { port } = server.address();

  try {
    assert.equal(await isPortAvailable(port, DEFAULT_DEV_HOST), false);
  } finally {
    await closeServer(server);
  }

  assert.equal(await isPortAvailable(port, DEFAULT_DEV_HOST), true);
});

test("findAvailablePort skips occupied ports", async () => {
  const server = await listenOnRandomPort();
  const { port } = server.address();

  try {
    const selectedPort = await findAvailablePort({
      preferredPort: port,
      host: DEFAULT_DEV_HOST,
      maxAttempts: 20,
    });

    assert.notEqual(selectedPort, port);
  } finally {
    await closeServer(server);
  }
});

test("chooseDevPorts defaults away from common development ports", async () => {
  const { apiPort, webPort, host } = await chooseDevPorts({});

  assert.equal(host, DEFAULT_DEV_HOST);
  assert.equal(COMMON_DEV_PORTS.has(apiPort), false);
  assert.equal(COMMON_DEV_PORTS.has(webPort), false);
  assert.notEqual(apiPort, webPort);
});

test("web-only config keeps the configured API URL even if that API port is occupied", async () => {
  const server = await listenOnRandomPort();
  const { port } = server.address();

  try {
    const config = await chooseRunConfig("web", {
      API_DEV_PORT: String(port),
      DEV_HOST: DEFAULT_DEV_HOST,
    });

    assert.equal(config.apiBaseUrl, `http://${DEFAULT_DEV_HOST}:${port}`);
  } finally {
    await closeServer(server);
  }
});

test("api-only config keeps the configured web URL even if that web port is occupied", async () => {
  const server = await listenOnRandomPort();
  const { port } = server.address();

  try {
    const config = await chooseRunConfig("api", {
      WEB_DEV_PORT: String(port),
      DEV_HOST: DEFAULT_DEV_HOST,
    });

    assert.equal(config.webAppUrl, `http://${DEFAULT_DEV_HOST}:${port}`);
  } finally {
    await closeServer(server);
  }
});
