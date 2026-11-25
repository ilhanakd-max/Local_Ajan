#!/usr/bin/env node
import { main } from "../src/cli.js";

main().catch((err) => {
  console.error("Fatal error:", err?.message || err);
  process.exit(1);
});
