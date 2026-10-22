'use strict';

// Keep the cockpit visible while Python imports. A slow but live backend is
// not offline; only an exited/absent child or an unreachable existing service
// should produce the offline warning.
const DEFAULT_WAIT_MS = 20000;

function backendStillStarting(elapsedMs) {
  const seconds = Math.max(1, Math.round(elapsedMs / 1000));
  return `SPARK core backend is still starting after ${seconds}s; the cockpit remains available and will reconnect.`;
}

function backendOfflineMessage() {
  return 'SPARK core backend offline. Launching UI anyway; check Python dependencies.';
}

function classifyBackendWait({ childAlive, elapsedMs, maxWaitMs = DEFAULT_WAIT_MS }) {
  if (!(elapsedMs >= maxWaitMs)) return { state: 'waiting' };
  if (childAlive) {
    return { state: 'starting', level: 'log', message: backendStillStarting(elapsedMs) };
  }
  return { state: 'offline', level: 'warn', message: backendOfflineMessage() };
}

module.exports = { DEFAULT_WAIT_MS, classifyBackendWait, backendStillStarting, backendOfflineMessage };
