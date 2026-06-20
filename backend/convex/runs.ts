import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

// Append a finished run to the global history. Called by the Python core after
// every command (via the Convex Python client: client.mutation("runs:record", ...)).
export const record = mutation({
  args: {
    channel: v.string(),
    transcript: v.string(),
    refinedPrompt: v.string(),
    intent: v.string(),
    cursorOutput: v.string(),
    summary: v.string(),
    workdir: v.string(),
    status: v.string(),
  },
  handler: async (ctx, args) => {
    return await ctx.db.insert("runs", { ...args, createdAt: Date.now() });
  },
});

// Most recent runs, newest first. Used as context so Claude can resolve references
// like "my last build" or "the other project", and to power the dashboard later.
export const recent = query({
  args: { limit: v.optional(v.number()) },
  handler: async (ctx, { limit }) => {
    return await ctx.db
      .query("runs")
      .withIndex("by_createdAt")
      .order("desc")
      .take(limit ?? 10);
  },
});

// The most recent run that actually changed something (edit/terminal) — i.e. the
// "last build" a user is most likely referring to.
export const lastBuild = query({
  args: {},
  handler: async (ctx) => {
    const items = await ctx.db
      .query("runs")
      .withIndex("by_createdAt")
      .order("desc")
      .take(50);
    return items.find((r) => r.intent === "edit" || r.intent === "terminal") ?? null;
  },
});
