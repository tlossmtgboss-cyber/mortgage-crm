import * as dotenv from "dotenv";
dotenv.config({ path: '.env' });

console.log("Starting AI Orchestrator...");
console.log("PORT:", process.env.PORT);
console.log("OPENAI_API_KEY:", process.env.OPENAI_API_KEY ? "set" : "NOT SET");
console.log("CRM_API_URL:", process.env.CRM_API_URL || "https://api.perenniaai.com (default)");

import express from "express";
import cors from "cors";
import { processMessage, UserMessage } from "./ai/orchestrator/smartAssistant";
import { pruneOldSessions } from "./ai/memory/memoryService";

console.log("Modules loaded successfully");

// Prevent process crash on unhandled rejections
process.on("unhandledRejection", (reason, promise) => {
  console.error("[FATAL] Unhandled rejection:", reason);
});

process.on("uncaughtException", (error) => {
  console.error("[FATAL] Uncaught exception:", error);
  // Give time to flush logs, then exit (Railway will restart)
  setTimeout(() => process.exit(1), 1000);
});

const app = express();
const PORT = process.env.PORT || 3001;

// Middleware
app.use(cors());
app.use(express.json({ limit: "1mb" }));

// Health check
app.get("/health", (req, res) => {
  res.json({
    status: "ok",
    service: "ai-orchestrator",
    uptime: process.uptime(),
    memory: Math.round(process.memoryUsage().heapUsed / 1024 / 1024) + "MB"
  });
});

// Main AI endpoint
app.post("/api/v1/ai/smart-assistant", async (req, res) => {
  const requestStart = Date.now();
  try {
    const { userId, sessionId, text, channel, metadata } = req.body;

    if (!text) {
      return res.status(400).json({ error: "Missing required field: text" });
    }

    if (text.length > 5000) {
      return res.status(400).json({ error: "Message too long (max 5000 chars)" });
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

    // 60s timeout for the entire processing pipeline
    const timeoutPromise = new Promise<never>((_, reject) =>
      setTimeout(() => reject(new Error("Processing timeout after 60s")), 60000)
    );

    const result = await Promise.race([processMessage(message), timeoutPromise]);

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
    const elapsed = Date.now() - requestStart;
    console.error(`[ERROR] Smart assistant failed after ${elapsed}ms:`, error);
    res.status(500).json({
      success: false,
      error: error instanceof Error ? error.message : "Internal server error"
    });
  }
});

// Prune stale sessions every 5 minutes to prevent memory leak
setInterval(() => {
  const pruned = pruneOldSessions(30 * 60 * 1000);
  if (pruned > 0) {
    console.log(`[MEMORY] Pruned ${pruned} stale sessions`);
  }
}, 5 * 60 * 1000);

// Start server
app.listen(Number(PORT), "0.0.0.0", () => {
  console.log(`AI Orchestrator running on port ${PORT}`);
  console.log(`   Health: http://0.0.0.0:${PORT}/health`);
  console.log(`   API: POST http://0.0.0.0:${PORT}/api/v1/ai/smart-assistant`);
});
