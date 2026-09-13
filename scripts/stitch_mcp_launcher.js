#!/usr/bin/env node
"use strict";

const path = require("node:path");
const { spawn } = require("node:child_process");
const { constants } = require("node:os");

const PLUGIN_ROOT = path.resolve(__dirname, "..");
const PROXY_SCRIPT = path.join(__dirname, "stitch_mcp_proxy.py");

function pythonCandidates(platform = process.platform) {
  if (platform === "win32") {
    return [["py", ["-3.11"]], ["python", []]];
  }
  return [["python3", []], ["python", []]];
}

function forwardedExitCode(code, signal) {
  if (Number.isInteger(code)) {
    return code;
  }
  const signalNumber = signal ? constants.signals[signal] : undefined;
  return Number.isInteger(signalNumber) ? 128 + signalNumber : 1;
}

function launch(candidates = pythonCandidates(), index = 0) {
  if (index >= candidates.length) {
    process.stderr.write("Stitch MCP requires Python 3.11 or newer on PATH.\n");
    process.exitCode = 1;
    return;
  }

  const [command, prefixArguments] = candidates[index];
  const child = spawn(command, [...prefixArguments, PROXY_SCRIPT], {
    cwd: PLUGIN_ROOT,
    env: process.env,
    stdio: "inherit",
    windowsHide: true,
  });
  let spawnFailed = false;
  const signalHandlers = new Map();

  const removeSignalHandlers = () => {
    for (const [signal, handler] of signalHandlers) {
      process.removeListener(signal, handler);
    }
  };

  child.once("spawn", () => {
    for (const signal of ["SIGINT", "SIGTERM"]) {
      const handler = () => {
        if (!child.killed) {
          child.kill(signal);
        }
      };
      signalHandlers.set(signal, handler);
      process.on(signal, handler);
    }
  });

  child.once("error", (error) => {
    spawnFailed = true;
    removeSignalHandlers();
    if (error && error.code === "ENOENT") {
      launch(candidates, index + 1);
      return;
    }
    process.stderr.write("Stitch MCP Python launcher failed.\n");
    process.exitCode = 1;
  });

  child.once("exit", (code, signal) => {
    if (spawnFailed) {
      return;
    }
    removeSignalHandlers();
    process.exitCode = forwardedExitCode(code, signal);
  });
}

module.exports = { forwardedExitCode, launch, pythonCandidates };

if (require.main === module) {
  launch();
}
