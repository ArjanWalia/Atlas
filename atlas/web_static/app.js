"use strict";

const $ = (id) => document.getElementById(id);

const els = {
  input: $("input"),
  send: $("send"),
  mic: $("mic"),
  suggestions: $("suggestions"),
  results: $("results"),
  loading: $("loading"),
  loadingText: $("loading-text"),
  intent: $("intent"),
  summaryCard: $("summary-card"),
  summary: $("summary"),
  refinedCard: $("refined-card"),
  refined: $("refined"),
  outputCard: $("output-card"),
  output: $("output"),
  error: $("error"),
  play: $("play"),
  player: $("player"),
  statusDot: $("status-dot"),
  statusText: $("status-text"),
  footModel: $("foot-model"),
};

let ttsEnabled = false;
let busy = false;

// --- Health -----------------------------------------------------------------

async function loadHealth() {
  try {
    const res = await fetch("/api/health");
    const h = await res.json();
    ttsEnabled = !!h.elevenlabs;
    if (h.model) els.footModel.textContent = h.model;

    if (h.anthropic && h.cursor) {
      setStatus("ok", "Ready");
    } else if (!h.anthropic) {
      setStatus("bad", "No API key");
    } else {
      setStatus("bad", "Cursor CLI missing");
    }
  } catch {
    setStatus("bad", "Offline");
  }
}

function setStatus(state, text) {
  els.statusDot.className = "dot " + state;
  els.statusText.textContent = text;
}

// --- Autosize textarea ------------------------------------------------------

function autosize() {
  els.input.style.height = "auto";
  els.input.style.height = Math.min(els.input.scrollHeight, 220) + "px";
}
els.input.addEventListener("input", autosize);

// --- Submit -----------------------------------------------------------------

async function submit() {
  if (busy) return;
  const text = els.input.value.trim();
  if (!text) return;

  busy = true;
  els.send.disabled = true;
  els.results.hidden = true;
  els.error.hidden = true;
  els.suggestions.style.opacity = "0.4";
  showLoading(true);

  try {
    const res = await fetch("/api/command", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    const data = await res.json();
    render(data);
  } catch (err) {
    renderError("Could not reach Atlas: " + err.message);
  } finally {
    showLoading(false);
    busy = false;
    els.send.disabled = false;
    els.suggestions.style.opacity = "1";
  }
}

function showLoading(on) {
  els.loading.hidden = !on;
  if (on) {
    const steps = [
      "Refining your request…",
      "Handing it to Cursor…",
      "Summarizing the result…",
    ];
    let i = 0;
    els.loadingText.textContent = steps[0];
    clearInterval(showLoading._t);
    showLoading._t = setInterval(() => {
      i = Math.min(i + 1, steps.length - 1);
      els.loadingText.textContent = steps[i];
    }, 2600);
  } else {
    clearInterval(showLoading._t);
  }
}

function render(data) {
  els.results.hidden = false;

  if (data.intent) {
    els.intent.textContent = data.intent;
    els.intent.dataset.intent = data.intent;
    els.intent.hidden = false;
  } else {
    els.intent.hidden = true;
  }

  toggleCard(els.refinedCard, els.refined, data.refined);
  toggleCard(els.outputCard, els.output, data.output);

  if (data.summary) {
    els.summaryCard.hidden = false;
    els.summary.textContent = data.summary;
    els.play.hidden = !ttsEnabled;
    if (ttsEnabled) playVoice(data.summary, true);
  } else {
    els.summaryCard.hidden = true;
    els.play.hidden = true;
  }

  if (data.error) {
    els.error.hidden = false;
    els.error.textContent = data.error;
  } else {
    els.error.hidden = true;
  }
}

function toggleCard(card, node, value) {
  if (value) {
    card.hidden = false;
    node.textContent = value;
  } else {
    card.hidden = true;
  }
}

function renderError(msg) {
  els.results.hidden = false;
  els.intent.hidden = true;
  els.summaryCard.hidden = true;
  els.refinedCard.hidden = true;
  els.outputCard.hidden = true;
  els.play.hidden = true;
  els.error.hidden = false;
  els.error.textContent = msg;
}

// --- Voice playback (ElevenLabs via backend) --------------------------------

async function playVoice(text, auto = false) {
  if (!ttsEnabled) return;
  try {
    els.play.classList.add("playing");
    const res = await fetch("/api/tts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!res.ok) throw new Error("TTS failed");
    const blob = await res.blob();
    els.player.src = URL.createObjectURL(blob);
    await els.player.play();
  } catch (err) {
    if (!auto) renderError("Voice playback failed: " + err.message);
  } finally {
    els.play.classList.remove("playing");
  }
}

els.play.addEventListener("click", () => playVoice(els.summary.textContent));

// --- Browser speech-to-text (Web Speech API) --------------------------------

function setupMic() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) {
    els.mic.title = "Voice input needs Chrome or Edge";
    els.mic.classList.add("disabled");
    return;
  }
  const rec = new SR();
  rec.lang = "en-US";
  rec.interimResults = true;
  rec.continuous = false;

  let listening = false;
  let base = "";

  els.mic.addEventListener("click", () => {
    if (listening) {
      rec.stop();
      return;
    }
    base = els.input.value ? els.input.value.trim() + " " : "";
    rec.start();
  });

  rec.onstart = () => {
    listening = true;
    els.mic.classList.add("recording");
  };
  rec.onend = () => {
    listening = false;
    els.mic.classList.remove("recording");
    autosize();
  };
  rec.onerror = () => {
    listening = false;
    els.mic.classList.remove("recording");
  };
  rec.onresult = (e) => {
    let txt = "";
    for (let i = 0; i < e.results.length; i++) txt += e.results[i][0].transcript;
    els.input.value = base + txt;
    autosize();
  };
}

// --- Wiring -----------------------------------------------------------------

els.send.addEventListener("click", submit);
els.input.addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
    e.preventDefault();
    submit();
  }
});
els.suggestions.querySelectorAll(".chip").forEach((chip) => {
  chip.addEventListener("click", () => {
    els.input.value = chip.dataset.text;
    autosize();
    els.input.focus();
  });
});

loadHealth();
setupMic();
els.input.focus();
