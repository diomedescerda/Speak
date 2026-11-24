export function element(tag, text = "", className = "") {
  const result = document.createElement(tag);
  if (text !== "") result.textContent = text;
  if (className) result.className = className;
  return result;
}

export function button(text, className, action) {
  const result = element("button", text, className);
  result.type = "button";
  result.addEventListener("click", action);
  return result;
}

function japaneseText(tag, text, className = "") {
  const result = element(tag, "", className);
  result.lang = "ja";
  const value = text || "";
  const markup = /([\p{Script=Han}々〆]+)(?:\[([ぁ-ゖァ-ヺー]+)\]|[（(]([ぁ-ゖァ-ヺー]+)[）)])/gu;
  let position = 0;
  for (const item of value.matchAll(markup)) {
    result.append(value.slice(position, item.index));
    const ruby = element("ruby", item[1]);
    ruby.append(element("rt", item[2] || item[3]));
    result.append(ruby);
    position = item.index + item[0].length;
  }
  result.append(value.slice(position));
  return result;
}

function section(title, className = "") {
  const result = element("section", "", className);
  result.append(element("h3", title));
  return result;
}

function line(label, text, lang = "en") {
  const result = element("p");
  if (!text) return result;
  const value = lang === "ja" ? japaneseText("span", text) : element("span", text);
  result.append(element("span", label, "inline-label"), " ", value);
  return result;
}

function list(items, renderItem, className = "") {
  const result = element("ul", "", className);
  for (const item of items) {
    const row = element("li");
    row.append(renderItem(item));
    result.append(row);
  }
  return result;
}

export function displayDate(date) {
  if (!date || !/^\d{4}-\d{2}-\d{2}/.test(date)) return "";
  return new Intl.DateTimeFormat(undefined, {
    month: "short", day: "numeric", year: "numeric", timeZone: "UTC",
  }).format(new Date(date.slice(0, 10) + "T12:00:00Z"));
}

function externalLink(href, label) {
  try {
    const url = new URL(href);
    if (url.protocol !== "http:" && url.protocol !== "https:") return null;
    const result = element("a", label, "source");
    result.href = url.href;
    result.target = "_blank";
    result.rel = "noopener noreferrer";
    return result;
  } catch {
    return null;
  }
}

function audioPlayer(options, label, slow = false) {
  const group = element("div", "", "media");
  const actions = element("div", "", "media-buttons");
  const player = element("audio");
  const status = element("p", "", "media-status");
  player.hidden = true;
  player.controls = true;
  player.preload = "none";
  player.setAttribute("aria-label", label);
  status.hidden = true;
  status.role = "status";
  group.append(actions, player, status);

  const showError = () => {
    status.textContent = "Audio is unavailable. Try playing it again.";
    status.hidden = false;
  };
  player.addEventListener("error", showError);

  function play(slower) {
    const params = new URLSearchParams(options);
    if (slower) params.set("slow", "1");
    const source = "/api/audio?" + params;
    status.hidden = true;
    player.hidden = false;
    if (player.getAttribute("src") !== source || player.error) player.src = source;
    else if (player.ended) player.currentTime = 0;
    player.play().catch((error) => {
      if (error.name !== "AbortError") showError();
    });
  }

  actions.append(button(label, "secondary", () => play(false)));
  if (slow) actions.append(button("Play slowly", "secondary", () => play(true)));
  return group;
}

function renderEnglish(mission, card, materials, prompt) {
  card.append(element("h3", mission.source_title, "mission-title"));
  if (mission.speaking_mode) card.append(element("p", mission.speaking_mode, "intro muted"));
  prompt.append(element("p", mission.speaking_prompt, "prompt-text preserve-lines"));
  if (mission.speaking_mode_desc) prompt.append(element("p", mission.speaking_mode_desc, "muted"));
  card.append(prompt);

  if (mission.reading_excerpt) {
    const reading = element("details");
    reading.append(
      element("summary", "Read the excerpt"),
      element("p", mission.reading_excerpt, "reading preserve-lines"),
    );
    const link = externalLink(mission.source_url, mission.source_name || "Read the original");
    if (link) reading.append(link);
    card.append(reading);
  }

  const phrases = mission.target_phrases || [];
  if (phrases.length) {
    const expressions = section("Target expressions");
    expressions.append(list(phrases, (item) => {
      const entry = element("div");
      entry.append(element("strong", item.phrase), element("p", item.meaning));
      if (item.example) entry.append(element("p", item.example, "muted"));
      return entry;
    }));
    materials.append(expressions);
  }

  const connector = mission.connector_challenge || {};
  if (connector.phrase) {
    const challenge = section("Connector challenge");
    challenge.append(element("strong", connector.phrase));
    if (connector.usage_tip) challenge.append(element("p", connector.usage_tip));
    if (connector.example) challenge.append(element("p", connector.example, "muted"));
    materials.append(challenge);
  }

  const forbidden = mission.forbidden_words || [];
  if (forbidden.length) {
    const avoid = section("Words to avoid");
    avoid.append(list(forbidden, (item) => {
      const entry = element("div");
      entry.append(element("strong", item.word));
      if (item.instead_use) entry.append(line("Try", Array.isArray(item.instead_use) ? item.instead_use.join(", ") : item.instead_use));
      return entry;
    }));
    materials.append(avoid);
  }
}

function renderJapanese(mission, card, materials, prompt) {
  card.append(element("h3", mission.topic_title, "mission-title"));
  if (mission.scenario) card.append(element("p", mission.scenario, "intro muted"));
  prompt.append(
    japaneseText("p", mission.speaking_prompt_ja, "prompt-text preserve-lines"),
    element("p", mission.speaking_prompt_en, "translation preserve-lines"),
  );
  card.append(prompt);

  if (mission.model_japanese) {
    const model = section("Model passage");
    model.append(japaneseText("p", mission.model_japanese, "japanese-reading preserve-lines"));
    if (mission.model_english) model.append(element("p", mission.model_english, "translation preserve-lines"));
    model.append(audioPlayer({lang: "ja", kind: "model", mission_id: mission.id}, "Play model", true));
    materials.append(model);
  }
  if (mission.starter_template) {
    const starter = section("Sentence starter");
    starter.append(japaneseText("p", mission.starter_template, "japanese-reading"));
    materials.append(starter);
  }
  const frame = mission.grammar_frame || {};
  if (frame.pattern) {
    const grammar = section("Grammar frame");
    grammar.append(
      japaneseText("strong", frame.pattern),
      element("p", frame.meaning),
      japaneseText("p", frame.structure),
      japaneseText("p", frame.example_ja, "japanese-reading"),
      element("p", frame.example_en, "translation"),
    );
    materials.append(grammar);
  }
  if (mission.vocab_blocks?.length) {
    const vocabulary = section("Vocabulary");
    vocabulary.append(list(mission.vocab_blocks, (item) => {
      const entry = element("div");
      entry.append(japaneseText("strong", item.word), " ", japaneseText("span", item.reading, "muted"));
      entry.append(element("p", item.meaning), japaneseText("p", item.example_ja, "japanese-reading"));
      return entry;
    }));
    materials.append(vocabulary);
  }
  if (mission.particle_traps?.length) {
    const traps = section("Particle and conjugation watchouts");
    traps.append(list(mission.particle_traps, (item) => {
      const entry = element("div");
      entry.append(
        element("strong", item.trap_title),
        line("Avoid", item.wrong, "ja"),
        line("Try", item.right, "ja"),
        element("p", item.explanation, "muted"),
      );
      return entry;
    }));
    materials.append(traps);
  }
}

export function renderMission(mission, lang, card, materials) {
  const category = lang === "ja" ? "Stage " + mission.stage + " · " + mission.stage_name : mission.category;
  const meta = [displayDate(mission.date), category].filter(Boolean).join(" · ");
  const prompt = section("Your speaking prompt", "prompt");
  prompt.firstChild.className = "prompt-title";
  card.replaceChildren(element("p", meta, "mission-meta"));
  materials.replaceChildren();
  if (lang === "ja") renderJapanese(mission, card, materials, prompt);
  else renderEnglish(mission, card, materials, prompt);
  materials.hidden = !materials.childElementCount;
}

function coachMetrics(attempt, lang) {
  const metrics = attempt.metrics || {};
  const details = element("div", "", "metrics");
  const add = (value, unit) => {
    if (typeof value === "number" && Number.isFinite(value)) {
      details.append(element("span", value + " " + unit));
    }
  };
  if (attempt.has_audio) {
    add(metrics.duration_sec, "sec");
    add(lang === "ja" ? metrics.cpm : metrics.wpm, lang === "ja" ? "CPM" : "WPM");
  }
  if (lang === "ja") {
    add(metrics.char_count, "characters");
  } else {
    add(metrics.word_count, "words");
    if (typeof metrics.unique_word_ratio === "number") add(Math.round(metrics.unique_word_ratio * 100), "% unique");
  }
  return details;
}

function coachNotes(review, metrics, lang) {
  const notes = section(lang === "ja" ? "Grammar and vocabulary" : "Expression check");
  if (lang === "ja") {
    if (review.scaffolding_check) notes.append(element("p", review.scaffolding_check));
    if (metrics.grammar_pattern && typeof metrics.grammar_used === "boolean") {
      notes.append(line(metrics.grammar_used ? "Grammar used" : "Grammar to try", metrics.grammar_pattern, "ja"));
    }
    if (metrics.vocab_used?.length) notes.append(line("Vocabulary used", metrics.vocab_used.join("、"), "ja"));
    if (review.traps_spotted?.length) notes.append(list(review.traps_spotted, (note) => element("span", note), "note-list"));
  } else {
    if (review.constraint_check) notes.append(element("p", review.constraint_check));
    if (metrics.targets_used?.length) notes.append(line("Targets used", metrics.targets_used.join(", ")));
    const forbidden = Object.entries(metrics.forbidden_used || {}).map(([word, count]) => word + " (" + count + "×)");
    if (forbidden.length) notes.append(line("Words to avoid", forbidden.join(", ")));
    const repeated = (metrics.repeated_words || []).map(({word, count}) => word + " (" + count + "×)");
    if (repeated.length) notes.append(line("Repeated words", repeated.join(", ")));
    if (review.repetitive_habits_spotted?.length) {
      notes.append(list(review.repetitive_habits_spotted, (note) => element("span", note), "note-list"));
    }
  }
  return notes;
}

export function retryChallenge(review) {
  return (review.round2_challenge || "")
    .replace(/\[l\]/gi, "Play polished version")
    .replace(/\[r\]/gi, "Retry round");
}

export function renderAttempt(container, attempt, lang, retry = null) {
  const review = attempt.review || {};
  const header = element("header", "", "feedback-heading");
  const heading = element("h2", "Round " + attempt.round_num + " feedback");
  heading.tabIndex = -1;
  header.append(heading);
  if (review.score != null) {
    const score = element("span", review.score, "score");
    score.append(element("small", "/100"));
    header.append(score);
  }
  container.replaceChildren(header);
  if (review.summary_feedback) container.append(element("p", review.summary_feedback, "preserve-lines"));
  const metrics = coachMetrics(attempt, lang);
  if (metrics.childElementCount) container.append(metrics);

  const polished = review.native_model_version;
  if (polished) {
    const model = section("Polished version", "polished");
    if (lang === "ja") {
      model.append(japaneseText("p", polished, "japanese-reading preserve-lines"));
      if (review.native_model_english) model.append(element("p", review.native_model_english, "translation"));
      model.append(audioPlayer({lang, kind: "polished", attempt_id: attempt.id}, "Play polished version"));
    } else {
      model.append(element("p", polished, "preserve-lines"));
    }
    container.append(model);
  }

  const notes = coachNotes(review, attempt.metrics || {}, lang);
  if (notes.childElementCount > 1) container.append(notes);

  if (review.sentence_upgrades?.length) {
    const upgrades = section("Sentence upgrades");
    upgrades.append(list(review.sentence_upgrades, (item) => {
      const entry = element("div");
      if (item.original) {
        entry.append(lang === "ja" ? japaneseText("p", item.original) : element("p", item.original));
      }
      if (item.why_upgrade) entry.append(element("p", item.why_upgrade, "muted"));
      if (item.natural_casual) entry.append(line("Casual", item.natural_casual, lang));
      if (item.natural_articulate) entry.append(line("Articulate", item.natural_articulate));
      if (item.natural_polite) entry.append(line("Polite", item.natural_polite, "ja"));
      return entry;
    }, "upgrades"));
    container.append(upgrades);
  }

  const transcript = section("Your transcript");
  transcript.append(lang === "ja"
    ? japaneseText("p", attempt.transcript, "preserve-lines")
    : element("p", attempt.transcript, "preserve-lines"));
  if (attempt.has_audio) transcript.append(audioPlayer({lang, kind: "recording", attempt_id: attempt.id}, "Play your recording"));
  container.append(transcript);

  const challenge = retryChallenge(review);
  if (challenge) {
    const next = section(attempt.round_num === 1 ? "Round 2 focus" : "Next step");
    next.append(element("p", challenge));
    container.append(next);
  }
  if (retry) container.append(button("Retry round", "primary full", retry));
  return heading;
}
