import { defineSchema, defineTable } from "convex/server";
import { v } from "convex/values";

// Atlas cloud backend: a global, single-user history of every run plus a tiny
// "config" singleton that remembers the active project directory and the set of
// directories Atlas has worked in. This is what lets you say "build on my last
// project" or "switch to ~/projects/foo" from any session or channel.
export default defineSchema({
  // One row per command Atlas executes (mic, CLI, or iMessage).
  runs: defineTable({
    createdAt: v.number(),
    channel: v.string(), // "mic" | "cli" | "imessage"
    transcript: v.string(), // what the user said
    refinedPrompt: v.string(), // Claude's cleaned-up Cursor prompt
    intent: v.string(), // plan | explain | edit | terminal | navigate | other
    cursorOutput: v.string(), // Cursor's raw text output
    summary: v.string(), // spoken-style summary
    workdir: v.string(), // directory the run executed in
    status: v.string(), // "done" | "error"
  }).index("by_createdAt", ["createdAt"]),

  // Singleton row (key = "global") holding cross-session directory memory.
  config: defineTable({
    key: v.string(),
    activeWorkdir: v.optional(v.string()),
    knownDirs: v.array(v.string()),
    updatedAt: v.number(),
  }).index("by_key", ["key"]),

  // Inbound commands from remote channels (iMessage). The Spectrum gateway enqueues
  // them; the Python worker subscribes to the pending ones, runs them locally, and
  // writes back a summary that the gateway texts to the user.
  commands: defineTable({
    createdAt: v.number(),
    channel: v.string(), // "imessage"
    status: v.string(), // "pending" | "claimed" | "done" | "error"
    text: v.optional(v.string()), // caption or text-only command
    audioStorageId: v.optional(v.id("_storage")), // voice memo, if any
    summary: v.optional(v.string()), // spoken/replied result
    updatedAt: v.number(),
  }).index("by_status", ["status", "createdAt"]),
});
