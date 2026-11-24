import {button, displayDate, element, renderAttempt, renderMission, retryChallenge} from "./content.js";

const byId = (id) => document.getElementById(id);
const ui = {
  practiceNav: byId("show-practice"),
  historyNav: byId("show-history"),
  language: {en: byId("english"), ja: byId("japanese")},
  viewHeading: byId("view-heading"),
  practiceView: byId("practice-view"),
  missionState: byId("mission-state"),
  missionStatus: byId("mission-status"),
  reloadMission: byId("reload-mission"),
  layout: byId("session-layout"),
  mission: byId("mission"),
  materials: byId("materials"),
  roundHeading: byId("round-heading"),
  roundFocus: byId("round-focus"),
  targetTime: byId("target-time"),
  completed: byId("completed"),
  startOver: byId("start-over"),
  form: byId("response-form"),
  recordPanel: byId("record-panel"),
  record: byId("record"),
  stop: byId("stop"),
  cancel: byId("cancel"),
  take: byId("take"),
  textPanel: byId("text-panel"),
  response: byId("response"),
  submit: byId("submit"),
  typeResponse: byId("type-response"),
  microphone: byId("use-microphone"),
  practiceStatus: byId("practice-status"),
  feedback: byId("feedback"),
  historyView: byId("history-view"),
  historyState: byId("history-state"),
  historyStatus: byId("history-status"),
  reloadHistory: byId("reload-history"),
  historyList: byId("history-list"),
  historyFeedback: byId("history-feedback"),
};

function savedLanguage() {
  try {
    if (localStorage.getItem("speak-language") === "ja") return "ja";
  } catch {
    // The language preference is optional when browser storage is unavailable.
  }
  return "en";
}

function createSession(lang) {
  return {
    lang, mission: null, loading: false, missionError: "", busy: false,
    mode: "record", draft: "", take: null, takeUrl: "", requestId: "",
    review: null, retryOf: null, status: "", statusTone: "",
  };
}

const sessions = {en: createSession("en"), ja: createSession("ja")};
let language = savedLanguage();
let view = "practice";
let renderedMission = null;
let activeCapture = null;
let historyRequest = 0;
let activePlayer = null;
const current = () => sessions[language];
const practicing = (session) => view === "practice" && session === current();

async function api(path, lang, options = {}) {
  const response = await fetch("/api/" + path + "?" + new URLSearchParams({lang}), {
    cache: "no-store",
    ...options,
  });
  const result = await response.json().catch(() => null);
  if (!response.ok || result === null) {
    const fallback = response.status === 403
      ? "Open Speak with your authorized Tailscale account."
      : "Speak could not complete the request. Try again.";
    throw new Error(result?.error || fallback);
  }
  return result;
}

function updateStatus(session, message = "", tone = "") {
  session.status = message;
  session.statusTone = tone;
  if (practicing(session)) renderPractice();
}

function setNavigation() {
  for (const [key, control] of Object.entries(ui.language)) {
    control.setAttribute("aria-pressed", String(key === language));
    control.disabled = Boolean(activeCapture);
  }
  for (const [key, control] of [["practice", ui.practiceNav], ["history", ui.historyNav]]) {
    if (key === view) control.setAttribute("aria-current", "page");
    else control.removeAttribute("aria-current");
    control.disabled = Boolean(activeCapture);
  }
}

async function loadMission(session) {
  if (session.loading) return;
  session.loading = true;
  session.missionError = "";
  if (practicing(session)) renderPractice();
  try {
    const result = await api("mission", session.lang);
    session.mission = result.mission;
  } catch (error) {
    session.missionError = error.message;
  } finally {
    session.loading = false;
    if (practicing(session)) renderPractice();
  }
}

function captureLimit(session) {
  if (session.lang === "ja") return session.mission.target_seconds || 30;
  return session.retryOf ? 60 : 90;
}

function formatTime(seconds) {
  const minutes = Math.floor(seconds / 60);
  return minutes + ":" + String(seconds % 60).padStart(2, "0");
}

function updateTimer(capture) {
  const elapsed = Math.floor((performance.now() - capture.startedAt) / 1000);
  ui.targetTime.textContent = formatTime(Math.min(elapsed, capture.limit)) + " / " + formatTime(capture.limit);
  if (elapsed >= capture.limit) stopCapture(capture);
}

function renderPractice() {
  const session = current();
  const mission = session.mission;
  ui.layout.hidden = !mission;
  ui.missionState.hidden = Boolean(mission);
  ui.reloadMission.hidden = !session.missionError;
  ui.missionStatus.textContent = session.missionError || "Loading your mission…";
  if (!mission) return;

  if (renderedMission !== mission) {
    renderMission(mission, session.lang, ui.mission, ui.materials);
    renderedMission = mission;
  }

  const completed = Boolean(session.review && !session.retryOf);
  const round = session.retryOf ? 2 : session.review?.round_num || 1;
  const capture = activeCapture;
  const typing = session.mode === "text";
  const target = captureLimit(session);
  ui.roundHeading.textContent = "Round " + round;
  ui.roundFocus.textContent = session.retryOf ? retryChallenge(session.retryOf.review) : "";
  ui.roundFocus.hidden = !ui.roundFocus.textContent;
  ui.targetTime.hidden = completed || typing;
  if (capture?.startedAt != null) updateTimer(capture);
  else ui.targetTime.textContent = "Up to " + formatTime(target);
  ui.form.hidden = completed;
  ui.completed.hidden = !completed;
  ui.recordPanel.hidden = typing;
  ui.record.hidden = Boolean(capture);
  ui.record.disabled = session.busy;
  ui.stop.hidden = !capture?.recorder;
  ui.stop.disabled = Boolean(capture?.stopping);
  ui.cancel.hidden = !capture || Boolean(capture.recorder);
  ui.take.hidden = !session.take || Boolean(capture);
  if (session.takeUrl !== (ui.take.getAttribute("src") || "")) {
    ui.take.pause();
    if (session.takeUrl) ui.take.src = session.takeUrl;
    else {
      ui.take.removeAttribute("src");
      ui.take.load();
    }
  }
  ui.textPanel.hidden = !typing;
  ui.response.lang = session.lang;
  ui.response.disabled = session.busy;
  if (ui.response.value !== session.draft) ui.response.value = session.draft;
  ui.submit.hidden = Boolean(capture) || (!typing && !session.take);
  ui.submit.disabled = session.busy || (typing && !session.draft.trim());
  ui.submit.textContent = session.busy ? "Getting feedback…" : "Get feedback";
  ui.typeResponse.hidden = typing || Boolean(capture);
  ui.typeResponse.disabled = session.busy;
  ui.microphone.hidden = !typing;
  ui.microphone.disabled = session.busy;
  ui.practiceStatus.className = ["practice-status", session.statusTone].filter(Boolean).join(" ");
  ui.practiceStatus.textContent = session.status;
}

function focusHeading(heading) {
  heading.focus({preventScroll: true});
  heading.scrollIntoView({block: "start"});
}

function renderFeedback(session, reveal = false) {
  ui.feedback.hidden = !session.review;
  if (!session.review) return;
  const retry = session.review.round_num === 1 && !session.retryOf ? () => startRetry(session) : null;
  const heading = renderAttempt(ui.feedback, session.review, session.lang, retry);
  if (reveal) focusHeading(heading);
}

function clearTake(session) {
  if (session.takeUrl) URL.revokeObjectURL(session.takeUrl);
  session.take = null;
  session.takeUrl = "";
}

function resetResponse(session) {
  clearTake(session);
  session.draft = "";
  session.requestId = "";
  updateStatus(session);
}

function startRetry(session) {
  session.retryOf = session.review;
  resetResponse(session);
  renderFeedback(session);
  focusHeading(ui.roundHeading);
}

function switchMode(mode) {
  const session = current();
  session.mode = mode;
  session.requestId = "";
  updateStatus(session);
  if (mode === "text") ui.response.focus();
  else ui.record.focus();
}

function releaseCapture(capture) {
  if (activeCapture === capture) activeCapture = null;
  clearInterval(capture.timer);
  for (const track of capture.stream?.getTracks() || []) track.stop();
  setNavigation();
}

function stopCapture(capture) {
  if (capture.stopping) return;
  capture.stopping = true;
  if (capture.recorder?.state === "recording") {
    capture.recorder.stop();
    updateStatus(capture.session, "Preparing your recording…");
    return;
  }
  releaseCapture(capture);
  updateStatus(capture.session);
}

function recordFormat() {
  const choices = ["audio/mp4", "audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus"];
  return choices.find((type) => MediaRecorder.isTypeSupported?.(type));
}

async function startCapture() {
  const session = current();
  if (session.busy || activeCapture) return;
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
    updateStatus(session, "Microphone recording needs a supported browser over HTTPS. You can still type or dictate your response.", "error");
    return;
  }
  if (activePlayer) activePlayer.pause();
  const capture = {session, limit: captureLimit(session), chunks: []};
  activeCapture = capture;
  setNavigation();
  updateStatus(session, "Waiting for microphone access…");
  try {
    capture.stream = await navigator.mediaDevices.getUserMedia({audio: true});
    if (activeCapture !== capture) {
      for (const track of capture.stream.getTracks()) track.stop();
      return;
    }
    const format = recordFormat();
    const recorder = new MediaRecorder(capture.stream, format ? {mimeType: format} : undefined);
    capture.recorder = recorder;
    recorder.addEventListener("dataavailable", (event) => {
      if (event.data?.size) capture.chunks.push(event.data);
    });
    recorder.addEventListener("stop", () => {
      if (activeCapture !== capture) return;
      releaseCapture(capture);
      const type = recorder.mimeType || capture.chunks[0]?.type;
      const take = new Blob(capture.chunks, {type});
      if (!take.size) {
        updateStatus(session, "Could not capture audio. Try recording again.", "error");
        return;
      }
      clearTake(session);
      session.take = take;
      session.takeUrl = URL.createObjectURL(take);
      session.requestId = "";
      updateStatus(session, "Recording ready.");
      ui.submit.focus({preventScroll: true});
    });
    recorder.addEventListener("error", () => {
      if (activeCapture !== capture) return;
      releaseCapture(capture);
      updateStatus(session, "The recording was interrupted. Try recording again.", "error");
    });
    for (const track of capture.stream.getAudioTracks()) {
      track.addEventListener("ended", () => {
        if (activeCapture === capture) stopCapture(capture);
      });
    }
    recorder.start();
    capture.startedAt = performance.now();
    capture.timer = setInterval(() => updateTimer(capture), 250);
    updateStatus(session, "Recording…", "recording");
    ui.stop.focus({preventScroll: true});
  } catch (error) {
    if (activeCapture !== capture) return;
    releaseCapture(capture);
    const message = error.name === "NotAllowedError"
      ? "Microphone access was declined. Allow it in Safari or use Type response."
      : "Could not start the microphone. Try again or use Type response.";
    updateStatus(session, message, "error");
  }
}

function extension(type) {
  if (type.startsWith("audio/mp4")) return "m4a";
  if (type.startsWith("audio/ogg")) return "ogg";
  return "webm";
}

function newRequestId() {
  return window.crypto.randomUUID?.()
    || Array.from(window.crypto.getRandomValues(new Uint8Array(16)), (value) => value.toString(16).padStart(2, "0")).join("");
}

async function submitResponse(event) {
  event.preventDefault();
  const session = current();
  if (session.busy || activeCapture || !session.mission) return;
  const typed = session.mode === "text";
  if (typed ? !session.draft.trim() : !session.take) return;
  if (!session.requestId) session.requestId = newRequestId();

  const form = new FormData();
  form.set("mission_id", session.mission.id);
  form.set("request_id", session.requestId);
  if (session.retryOf) form.set("previous_attempt_id", session.retryOf.id);
  if (typed) form.set("text", session.draft.trim());
  else form.set("audio", session.take, "take." + extension(session.take.type));

  if (activePlayer) activePlayer.pause();
  session.busy = true;
  updateStatus(session, typed ? "Preparing feedback…" : "Transcribing your recording and preparing feedback…");
  try {
    const result = await api("review", session.lang, {
      method: "POST",
      headers: {"X-Speak-Request": "1"},
      body: form,
    });
    session.review = result.attempt;
    session.retryOf = null;
    resetResponse(session);
    if (practicing(session)) renderFeedback(session, true);
    if (view === "history" && language === session.lang) loadHistory();
  } catch (error) {
    updateStatus(session, error.message, "error");
  } finally {
    session.busy = false;
    if (practicing(session)) renderPractice();
  }
}

function cleanHistoryDetails() {
  ui.historyFeedback.hidden = true;
  ui.historyFeedback.replaceChildren();
  for (const item of ui.historyList.querySelectorAll("[aria-expanded='true']")) {
    item.setAttribute("aria-expanded", "false");
  }
}

async function loadHistory() {
  const requestedLanguage = language;
  const request = ++historyRequest;
  cleanHistoryDetails();
  ui.historyList.replaceChildren();
  ui.historyState.hidden = false;
  ui.historyStatus.textContent = "Loading your history…";
  ui.reloadHistory.hidden = true;
  try {
    const {attempts} = await api("history", requestedLanguage);
    if (request !== historyRequest || view !== "history") return;
    if (!attempts.length) {
      ui.historyStatus.textContent = "No completed rounds yet.";
      return;
    }
    ui.historyState.hidden = true;
    for (const attempt of attempts) {
      const row = element("li");
      const label = "Round " + attempt.round_num + " • " + attempt.title;
      const item = button("", "", () => {
        cleanHistoryDetails();
        item.setAttribute("aria-expanded", "true");
        ui.historyFeedback.hidden = false;
        const heading = renderAttempt(ui.historyFeedback, attempt, requestedLanguage);
        const back = button("Back to history", "secondary history-back", () => {
          cleanHistoryDetails();
          item.focus();
        });
        ui.historyFeedback.prepend(back);
        focusHeading(heading);
      });
      item.setAttribute("aria-expanded", "false");
      item.setAttribute("aria-controls", "history-feedback");
      const date = displayDate(attempt.date);
      const score = attempt.review?.score;
      const detail = [date, score != null ? score + "/100" : ""].filter(Boolean).join(" · ");
      item.append(element("span", label, "history-title"));
      if (detail) item.append(element("span", detail, "history-meta"));
      row.append(item);
      ui.historyList.append(row);
    }
  } catch (error) {
    if (request !== historyRequest || view !== "history") return;
    ui.historyStatus.textContent = error.message;
    ui.reloadHistory.hidden = false;
  }
}

function navigate(nextView, nextLanguage = language) {
  if (activeCapture) return;
  if (activePlayer) activePlayer.pause();
  view = nextView;
  language = nextLanguage;
  try {
    localStorage.setItem("speak-language", language);
  } catch {
    // Practice works when the browser blocks storage.
  }
  setNavigation();
  const practice = view === "practice";
  ui.viewHeading.textContent = practice ? "Today’s mission" : "Session history";
  ui.practiceView.hidden = !practice;
  ui.historyView.hidden = practice;
  if (practice) {
    const session = current();
    renderPractice();
    renderFeedback(session);
    if (!session.mission && !session.loading && !session.missionError) loadMission(session);
  } else {
    loadHistory();
  }
}

ui.practiceNav.addEventListener("click", () => navigate("practice"));
ui.historyNav.addEventListener("click", () => navigate("history"));
ui.language.en.addEventListener("click", () => navigate(view, "en"));
ui.language.ja.addEventListener("click", () => navigate(view, "ja"));
ui.reloadMission.addEventListener("click", () => loadMission(current()));
ui.reloadHistory.addEventListener("click", loadHistory);
ui.record.addEventListener("click", startCapture);
ui.stop.addEventListener("click", () => stopCapture(activeCapture));
ui.cancel.addEventListener("click", () => stopCapture(activeCapture));
ui.typeResponse.addEventListener("click", () => switchMode("text"));
ui.microphone.addEventListener("click", () => switchMode("record"));
ui.response.addEventListener("input", () => {
  const session = current();
  session.draft = ui.response.value;
  session.requestId = "";
  updateStatus(session);
});
ui.form.addEventListener("submit", submitResponse);
ui.startOver.addEventListener("click", () => {
  const session = current();
  session.review = null;
  session.retryOf = null;
  resetResponse(session);
  renderFeedback(session);
  focusHeading(ui.roundHeading);
});

document.addEventListener("play", (event) => {
  if (!(event.target instanceof HTMLAudioElement)) return;
  if (activePlayer && activePlayer !== event.target) activePlayer.pause();
  activePlayer = event.target;
}, true);

window.addEventListener("pagehide", () => {
  if (activePlayer) activePlayer.pause();
  if (!activeCapture) return;
  const capture = activeCapture;
  releaseCapture(capture);
  if (capture.recorder?.state === "recording") capture.recorder.stop();
  updateStatus(capture.session, "Recording stopped when you left the page.");
});

navigate("practice");
