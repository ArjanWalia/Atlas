import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

// Enqueue a command from a remote channel (called by the Spectrum iMessage gateway).
export const enqueue = mutation({
  args: {
    channel: v.string(),
    text: v.optional(v.string()),
    audioStorageId: v.optional(v.id("_storage")),
  },
  handler: async (ctx, args) => {
    const now = Date.now();
    return await ctx.db.insert("commands", {
      channel: args.channel,
      text: args.text,
      audioStorageId: args.audioStorageId,
      status: "pending",
      createdAt: now,
      updatedAt: now,
    });
  },
});

// Pending commands, oldest first. The Python worker subscribes to this.
export const pending = query({
  args: {},
  handler: async (ctx) => {
    return await ctx.db
      .query("commands")
      .withIndex("by_status", (q) => q.eq("status", "pending"))
      .order("asc")
      .take(20);
  },
});

// One command by id — the gateway subscribes to this to learn when it's done.
export const byId = query({
  args: { id: v.id("commands") },
  handler: async (ctx, { id }) => {
    return await ctx.db.get(id);
  },
});

// Atomically claim a pending command (pending -> claimed). Returns true if THIS caller
// won the claim, giving the single-writer worker exactly-once execution.
export const claim = mutation({
  args: { id: v.id("commands") },
  handler: async (ctx, { id }) => {
    const cmd = await ctx.db.get(id);
    if (!cmd || cmd.status !== "pending") return false;
    await ctx.db.patch(id, { status: "claimed", updatedAt: Date.now() });
    return true;
  },
});

// Mark a command finished with the spoken/replied summary.
export const complete = mutation({
  args: { id: v.id("commands"), summary: v.string(), status: v.string() },
  handler: async (ctx, { id, summary, status }) => {
    await ctx.db.patch(id, {
      summary,
      status: status === "error" ? "error" : "done",
      updatedAt: Date.now(),
    });
  },
});

// Mark a command failed with a user-facing message.
export const fail = mutation({
  args: { id: v.id("commands"), summary: v.string() },
  handler: async (ctx, { id, summary }) => {
    await ctx.db.patch(id, { status: "error", summary, updatedAt: Date.now() });
  },
});
