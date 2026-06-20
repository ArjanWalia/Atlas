import "dotenv/config";
import { ConvexClient } from "convex/browser";
import { makeFunctionReference } from "convex/server";
// Photon Spectrum SDK. NOTE: the exact surface (Spectrum(), app.messages, message
// attachments/reply, space.responding) is based on Spectrum's docs and may need small
// tweaks against the installed version — this gateway is deliberately a thin adapter.
import { Spectrum, imessage } from "spectrum-ts";

function requireEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    console.error(`Missing required env var ${name} (see .env.example).`);
    process.exit(1);
  }
  return value;
}

const CONVEX_URL = requireEnv("CONVEX_URL");
const PROJECT_ID = requireEnv("PROJECT_ID");
const PROJECT_SECRET = requireEnv("PROJECT_SECRET");
const ALLOWED = (process.env.SPECTRUM_ALLOWED_SENDERS ?? "")
  .split(",")
  .map((s) => s.trim().toLowerCase())
  .filter(Boolean);

const convex = new ConvexClient(CONVEX_URL);

// Convex function references (string form — no codegen needed in this project).
const generateUploadUrl = makeFunctionReference<"mutation">("files:generateUploadUrl");
const enqueueCommand = makeFunctionReference<"mutation">("commands:enqueue");
const commandById = makeFunctionReference<"query">("commands:byId");

// Upload raw audio bytes to Convex storage; return the storageId.
async function uploadAudio(bytes: Uint8Array, mimeType: string): Promise<string> {
  const uploadUrl = await convex.mutation(generateUploadUrl, {});
  const res = await fetch(uploadUrl, {
    method: "POST",
    headers: { "Content-Type": mimeType || "application/octet-stream" },
    body: bytes,
  });
  if (!res.ok) throw new Error(`Convex upload failed: ${res.status}`);
  const { storageId } = (await res.json()) as { storageId: string };
  return storageId;
}

// Resolve once the worker marks the command done/error; return its summary.
function waitForCommand(id: string): Promise<string> {
  return new Promise((resolve) => {
    const unsubscribe = convex.onUpdate(commandById, { id }, (cmd: any) => {
      if (cmd && (cmd.status === "done" || cmd.status === "error")) {
        unsubscribe();
        resolve(cmd.summary ?? "Done.");
      }
    });
  });
}

function isAllowed(sender: string | undefined): boolean {
  if (ALLOWED.length === 0) return false; // fail closed: a public number ignores all
  return !!sender && ALLOWED.includes(sender.toLowerCase());
}

async function main() {
  const app = await Spectrum({
    projectId: PROJECT_ID,
    projectSecret: PROJECT_SECRET,
    providers: [imessage.config()],
  });

  console.log("📨 Atlas iMessage gateway online — relaying voice memos to Atlas.");

  for await (const [space, message] of app.messages) {
    const sender: string | undefined = message.sender?.handle ?? message.from;
    if (!isAllowed(sender)) {
      console.log(`Ignoring message from non-allowlisted sender: ${sender}`);
      continue;
    }

    // Prefer a voice memo; otherwise treat the text as the command.
    const audio = (message.attachments ?? []).find((a: any) =>
      (a.mimeType ?? "").startsWith("audio/"),
    );
    if (!audio && !message.text) continue;

    try {
      let audioStorageId: string | undefined;
      if (audio) {
        const bytes: Uint8Array = await audio.content.read();
        audioStorageId = await uploadAudio(bytes, audio.mimeType ?? "audio/m4a");
      }

      const id = (await convex.mutation(enqueueCommand, {
        channel: "imessage",
        text: message.text ?? "",
        audioStorageId,
      })) as string;

      // Typing indicator while the Mac transcribes + runs Cursor + speaks, then reply.
      await space.responding(async () => {
        const summary = await waitForCommand(id);
        await message.reply(summary);
      });
    } catch (err) {
      console.error("Failed to handle message:", err);
      try {
        await message.reply("Sorry — Atlas couldn't process that.");
      } catch {
        /* ignore reply failures */
      }
    }
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
