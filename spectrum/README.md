# Atlas iMessage gateway (Photon Spectrum)

Connects a **Photon-hosted iMessage number** to Atlas. When you text a **voice memo**
(or plain text) to the number, this gateway uploads the audio to Convex and enqueues a
command; the Atlas worker on your Mac transcribes it, runs Cursor, **speaks the result
aloud**, and writes back a summary — which this gateway **texts back** to you.

```
iPhone voice memo ─iMessage─► Photon number ─► this gateway ─► Convex queue
                                                                   │
                                                  Atlas worker (Mac, `--worker`)
                                                  transcribe → run → say aloud
                                                                   │
                              this gateway ◄── summary ◄───────────┘  ── replies in iMessage
```

## Setup

1. Create a project at https://app.photon.codes and note the **Project ID** and
   **Project Secret**; provision/point your hosted **iMessage** number to it.
2. Configure env:
   ```bash
   cd spectrum
   cp .env.example .env
   # fill PROJECT_ID, PROJECT_SECRET, CONVEX_URL, SPECTRUM_ALLOWED_SENDERS
   npm install
   ```
3. Make sure the Convex backend is deployed (`cd ../backend && npx convex dev`) and the
   worker is running on your Mac (`python -m atlas --worker`).
4. Start the gateway:
   ```bash
   npm run dev
   ```

## Security

`SPECTRUM_ALLOWED_SENDERS` is an allowlist of iMessage handles (phone/email). The number
is public, so the gateway **fails closed**: anyone not on the list is ignored. Set it to
your own handle(s).

## Note on the Spectrum SDK

`src/index.ts` is a thin adapter. The exact `spectrum-ts` API (`Spectrum()`,
`app.messages`, `message.attachments` / `attachment.content.read()`, `message.reply()`,
`space.responding()`) follows Spectrum's docs but may differ slightly by version —
adjust those few call sites if the installed SDK differs. The Convex side and the rest of
the flow are unaffected.
