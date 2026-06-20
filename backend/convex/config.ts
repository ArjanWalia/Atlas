import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

// Single-user config singleton.
const KEY = "global";

// Read the active directory + known directories (or null before anything is set).
export const get = query({
  args: {},
  handler: async (ctx) => {
    return await ctx.db
      .query("config")
      .withIndex("by_key", (q) => q.eq("key", KEY))
      .unique();
  },
});

// Set the active project directory and remember it in knownDirs. This is what makes
// "switch to ~/projects/foo" stick across sessions and channels.
export const setWorkdir = mutation({
  args: { workdir: v.string() },
  handler: async (ctx, { workdir }) => {
    const now = Date.now();
    const existing = await ctx.db
      .query("config")
      .withIndex("by_key", (q) => q.eq("key", KEY))
      .unique();

    if (existing) {
      const knownDirs = existing.knownDirs.includes(workdir)
        ? existing.knownDirs
        : [...existing.knownDirs, workdir];
      await ctx.db.patch(existing._id, {
        activeWorkdir: workdir,
        knownDirs,
        updatedAt: now,
      });
      return existing._id;
    }

    return await ctx.db.insert("config", {
      key: KEY,
      activeWorkdir: workdir,
      knownDirs: [workdir],
      updatedAt: now,
    });
  },
});
