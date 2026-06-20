import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

// Standard Convex upload pattern: the gateway requests a short-lived upload URL, POSTs
// the voice-memo bytes to it, and gets back a storageId it stores on the command.
export const generateUploadUrl = mutation({
  args: {},
  handler: async (ctx) => {
    return await ctx.storage.generateUploadUrl();
  },
});

// The Python worker calls this to get a temporary download URL for the audio.
export const getUrl = query({
  args: { storageId: v.id("_storage") },
  handler: async (ctx, { storageId }) => {
    return await ctx.storage.getUrl(storageId);
  },
});

// Delete a stored blob once a command is done, so voice memos don't accumulate.
export const remove = mutation({
  args: { storageId: v.id("_storage") },
  handler: async (ctx, { storageId }) => {
    await ctx.storage.delete(storageId);
  },
});
