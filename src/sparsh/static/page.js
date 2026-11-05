// Sparsh's page: reads /api/state every few seconds, and a phone's
// screen only when asked (a peek is a real read of the phone, a second
// or two; it is never done on a timer).
"use strict";

const EVERY = 5000;
const KEY = "sparsh-page-token";
let token = "";
const open = {};        // serial -> the steps list is open
const more = {};        // serial -> every step shown, not the newest few
const FEW = 6;
let only = "";          // a program's name: only the steps it asked for
const screens = {};     // serial -> the last peek, kept across redraws

function $(id) { return document.getElementById(id); }

function el(tag, attrs, ...kids) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else if (v !== false && v != null) node.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) {
    if (kid == null || kid === false) continue;
    node.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return node;
}

function remember(t) {
  token = t;
  try { sessionStorage.setItem(KEY, t); } catch (_) { /* a private window */ }
}

function startToken() {
  const hash = new URLSearchParams(location.hash.slice(1));
  if (hash.get("token")) {
    remember(hash.get("token"));
    history.replaceState(null, "", location.pathname);
    return;
  }
  try { token = sessionStorage.getItem(KEY) || ""; } catch (_) { token = ""; }
}

async function api(path) {
  const r = await fetch(path, { headers: { Authorization: "Bearer " + token } });
  let body = {};
  try { body = await r.json(); } catch (_) { /* not JSON */ }
  if (r.status === 401) { signIn(); throw new Error("signed out"); }
  if (!r.ok) throw new Error(body.detail || ("HTTP " + r.status));
  return body;
}

function signIn() {
  $("main").hidden = true;
  $("sign").hidden = false;
  $("state-line").textContent = "Signed out";
}

const STATES = {
  device: ["answering", "on"], offline: ["offline", "off"], unauthorized: ["not trusted yet", "off"],
  missing: ["not answering", "off"], unnamed: ["not named yet", ""],
};

function chip(phone) {
  const [words, kind] = STATES[phone.state] || [phone.state, ""];
  return el("span", { class: "chip " + kind }, words);
}

function when(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d)) return iso.slice(11, 19);
  const today = new Date().toDateString() === d.toDateString();
  return today ? d.toTimeString().slice(0, 5)
               : d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function asked(step) {
  const args = step.args || {};
  const words = Object.entries(args).map(([k, v]) => k + "=" + JSON.stringify(v)).join(" ");
  return (step.action || "?") + (words ? " " + words : "");
}

// Who asked, as the program said it ("Samay: Morning brief", "Telegram ·
// asha"); the program is its first word, for the filter.
function program(step) {
  if (step.by === "you") return "You";
  if (!step.via) return "An agent (not said)";
  return step.via.split(/[:·]/)[0].trim() || step.via;
}

function stepRow(step) {
  const said = step.said || (step.outcome === "done" ? step.app : "");
  const asker = step.by === "you" ? "you" : (step.via || "agent");
  return el("li", {},
    el("span", { class: "at", title: step.at || "" }, when(step.at)),
    el("span", { class: "by", title: step.by === "you" ? "your own step"
                 : step.via ? "asked by " + step.via : "an agent; the program didn't say" }, asker),
    el("span", { class: "did" },
      asked(step), " → ", el("span", { class: "out " + (step.outcome || "") }, step.outcome),
      said ? " (" + said + ")" : "",
      step.on ? el("div", { class: "on" }, "on " + step.on) : null));
}

function screenView(phone) {
  const seen = screens[phone.serial];
  if (!seen) return null;
  if (seen.error) return el("div", { class: "note bad" }, seen.error);
  const b = seen.battery || {};
  const power = b.level == null ? "Battery: not said"
    : "Battery: " + b.level + "%" + (b.charging == null ? "" : b.charging ? ", charging" : ", not charging");
  const picture = seen.shot
    ? el("img", { src: "data:image/png;base64," + seen.shot, alt: "The phone's screen" })
    : el("div", { class: "noshot" }, "No picture: " + (seen.screen && seen.screen.note
        ? "this screen isn't shown." : "list only."));
  return el("div", { class: "screen" }, picture,
    el("div", {},
      el("p", { class: "meta" }, "Looked at " + seen.at + " · " + power),
      el("pre", {}, seen.text || "")));
}

async function look(phone, shot, button) {
  button.disabled = true;
  try {
    const got = await api("/api/peek?serial=" + encodeURIComponent(phone.serial) + "&shot=" + (shot ? 1 : 0));
    screens[phone.serial] = { ...got, at: new Date().toTimeString().slice(0, 8) };
  } catch (e) {
    if (e.message !== "signed out") screens[phone.serial] = { error: "Couldn't look: " + e.message };
  }
  button.disabled = false;
  draw(last);
}

function phoneCard(phone) {
  const lookBtn = el("button", { class: "btn main", title: "Read the screen now, with a picture" }, "Look");
  const listBtn = el("button", { class: "btn", title: "Read the screen now, as the list only" }, "List");
  lookBtn.addEventListener("click", () => look(phone, true, lookBtn));
  listBtn.addEventListener("click", () => look(phone, false, listBtn));
  const ready = phone.state === "device";
  const steps = (phone.steps || []).filter((s) => !only || program(s) === only);
  const shown = more[phone.serial] ? steps : steps.slice(0, FEW);
  const moreBtn = steps.length > FEW
    ? el("button", { class: "btn more", onclick: () => { more[phone.serial] = !more[phone.serial]; draw(last); } },
         more[phone.serial] ? "Show the newest " + FEW : "Show " + (steps.length - FEW) + " more")
    : null;
  const list = el("details", { class: "steps", open: open[phone.serial] !== false,
    ontoggle: (e) => { open[phone.serial] = e.target.open; } },
    el("summary", {}, steps.length ? "What was done on it, newest first"
                                   : "Nothing done on it yet"),
    steps.length ? el("ul", { class: "step-list" }, shown.map(stepRow)) : null, moreBtn);
  return el("article", { class: "phone" },
    el("div", { class: "phone-head" },
      el("span", { class: "name" }, phone.name || phone.model || phone.serial),
      el("span", { class: "what" }, [phone.kind,
        phone.name && phone.model && phone.model !== phone.kind ? phone.model.replace(/_/g, " ") : "",
        phone.serial].filter(Boolean).join(" · ")),
      chip(phone),
      phone.spare ? el("span", { class: "chip spare", title: "A watch may open a page on it unasked" }, "spare") : null,
      ready ? el("span", { class: "actions" }, lookBtn, listBtn) : null),
    phone.note ? el("div", { class: "why" }, phone.note) : null,
    screenView(phone),
    list);
}

let last = null;

function drawFilter(phones) {
  const names = new Set();
  for (const p of phones) for (const s of p.steps || []) names.add(program(s));
  if (only && !names.has(only)) names.add(only);
  const pick = el("select", { "aria-label": "Show the steps asked for by",
    onchange: (e) => { only = e.target.value; draw(last); } },
    el("option", { value: "" }, "everyone"),
    [...names].sort().map((n) => el("option", { value: n, selected: n === only }, n)));
  $("filter").replaceChildren(names.size > 1 || only
    ? el("label", { class: "filter" }, "Show steps asked for by ", pick) : "");
}

function draw(data) {
  if (!data) return;
  last = data;
  const phones = data.phones || [];
  const answering = phones.filter((p) => p.state === "device").length;
  $("state-line").textContent = phones.length
    ? answering + " of " + phones.length + " phone" + (phones.length === 1 ? "" : "s") + " answering"
    : "No phones";
  const notes = [];
  if (data.adb && data.adb !== "ok") notes.push(el("div", { class: "note bad" }, "adb: " + data.adb));
  if (data.wda && data.wda.note) notes.push(el("div", { class: "note wait" }, data.wda.note));
  $("notes").replaceChildren(...notes);
  $("phones").replaceChildren(...(phones.length ? phones.map(phoneCard)
    : [el("p", { class: "empty" }, "No phone is named and none answers. Plug one in, or name them in ",
         el("code", {}, "SPARSH_PHONES"), " (Sarathi: Settings → Your phones).")]));
  drawFilter(phones);
  const r = data.rules || {};
  $("rules").replaceChildren(el("dl", {},
    el("dt", {}, "Never (the agent is kept out of these apps)"),
    el("dd", {}, (r.never || []).length ? r.never.join(", ") : "none"),
    el("dt", {}, "Ask first (a tap on these words waits for your yes)"),
    el("dd", {}, (r.ask || []).join(", ") || "none"),
    el("dt", {}, "Kept in"),
    el("dd", {}, el("code", {}, r.path || ""), r.exists ? "" : " (not written yet: the defaults)")));
  $("foot").textContent = "Sparsh " + (data.version || "");
}

async function tick() {
  if (!token) return signIn();
  try {
    const data = await api("/api/state");
    $("sign").hidden = true;
    $("main").hidden = false;
    draw(data);
  } catch (e) {
    if (e.message !== "signed out") $("state-line").textContent = "Couldn't read: " + e.message;
  }
}

$("token-go").addEventListener("click", () => {
  remember($("token").value.trim());
  tick();
});
startToken();
tick();
setInterval(() => { if (!document.hidden) tick(); }, EVERY);
