import * as dotenv from "dotenv";
dotenv.config({ path: '.env' });

if (!process.env.OPENAI_API_KEY) {
  console.error("FATAL: OPENAI_API_KEY is not set. Exiting.");
  process.exit(1);
}

console.log("Starting AI Orchestrator...");
console.log("PORT:", process.env.PORT);
console.log("OPENAI_API_KEY: set");

import express from "express";
import cors from "cors";
import { processMessage, UserMessage } from "./ai/orchestrator/smartAssistant";
import { pruneOldSessions } from "./ai/memory/memoryService";

console.log("Modules loaded successfully");

const app = express();
const PORT = process.env.PORT || 3001;

// Middleware
app.use(cors());
app.use(express.json({ limit: "1mb" }));

// Health check
app.get("/health", (req, res) => {
  res.json({ status: "ok", service: "ai-orchestrator", uptime: process.uptime() });
});

// Main AI endpoint
app.post("/api/v1/ai/smart-assistant", async (req, res) => {
  try {
    const { userId, sessionId, text, channel, metadata } = req.body;

    if (!text) {
      return res.status(400).json({ error: "Missing required field: text" });
    }

    const message: UserMessage = {
      userId: userId || "anonymous",
      sessionId: sessionId || `session-${Date.now()}`,
      text,
      channel: channel || "web",
      metadata: {
        ...metadata,
        authToken: req.headers.authorization?.replace("Bearer ", "") || metadata?.authToken
      }
    };

    const result = await Promise.race([
      processMessage(message),
      new Promise<never>((_, reject) =>
        setTimeout(() => reject(new Error("Request timeout (60s)")), 60_000)
      )
    ]);

    res.json({
      success: true,
      answer: result.answer,
      confidence: result.confidence,
      escalationRequired: result.escalationRequired,
      escalationReason: result.escalationReason,
      actionsExecuted: result.actionsExecuted,
      meta: result.meta
    });
  } catch (error) {
    console.error("[ERROR] Smart assistant failed:", error);
    res.status(500).json({
      success: false,
      error: error instanceof Error ? error.message : "Internal server error"
    });
  }
});

// Prune stale sessions every 5 minutes
setInterval(pruneOldSessions, 5 * 60 * 1000);

// Crash handlers — log and exit cleanly so Railway restarts the process
process.on("unhandledRejection", (reason) => {
  console.error("[FATAL] Unhandled rejection:", reason);
  process.exit(1);
});
process.on("uncaughtException", (err) => {
  console.error("[FATAL] Uncaught exception:", err);
  process.exit(1);
});

// Start server
app.listen(Number(PORT), "0.0.0.0", () => {
  console.log(`AI Orchestrator running on port ${PORT}`);
  console.log(`  Health: http://0.0.0.0:${PORT}/health`);
  console.log(`  API: POST http://0.0.0.0:${PORT}/api/v1/ai/smart-assistant`);
});
