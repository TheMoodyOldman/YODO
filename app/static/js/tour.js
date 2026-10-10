// 互動新手教學. Data comes from app.onboarding.tour_payload in #tour-data:
//   state: null (never offered: show the start-or-skip dialog) | "active"
//   steps: [{key, title, href, done, targets[], hint, progress}]
// Steps tick themselves off from real data on every page load; the current step index is kept in
// localStorage so 上一步/下一步 work across pages. Moving between pages slides like a slideshow.
(() => {
  const data = document.getElementById("tour-data");
  if (!data) return;
  const cfg = JSON.parse(data.textContent);
  const steps = cfg.steps;
  const total = steps.length;
  const KEY = "yodo-tour-step";
  const SLIDE = "yodo-tour-slide";
  const root = document.documentElement;

  const store = {
    get(k) { try { return localStorage.getItem(k); } catch { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch {} },
    del(k) { try { localStorage.removeItem(k); } catch {} },
  };
  const post = (action) => fetch(`/me/tour/${action}`, { method: "POST", headers: { "X-Requested-With": "fetch" } });
  const pageOf = (href) => href.split("#")[0];
  const hashOf = (href) => (href.includes("#") ? href.split("#")[1] : "");
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text) e.textContent = text; return e; };

  // Slide in when we arrived here from the tour, slide out before leaving.
  try {
    if (sessionStorage.getItem(SLIDE)) {
      sessionStorage.removeItem(SLIDE);
      root.classList.add("tour-enter");
      setTimeout(() => root.classList.remove("tour-enter"), 700);
    }
  } catch {}
  function go(href) {
    try { sessionStorage.setItem(SLIDE, "1"); } catch {}
    root.classList.add("tour-leave");
    setTimeout(() => { location.href = href; }, 280);
  }

  const firstOpen = () => { const i = steps.findIndex((s) => !s.done); return i === -1 ? total : i; };

  // ---------- start-or-skip dialog (first visit) ----------
  function welcome() {
    const veil = el("div", "tour-veil");
    const box = el("div", "tour-welcome");
    box.setAttribute("role", "dialog");
    box.setAttribute("aria-modal", "true");
    box.setAttribute("aria-labelledby", "tour-welcome-title");
    box.append(el("div", "tour-welcome-mark", "👋"));
    const h = el("h2", "", `歡迎加入，${cfg.name}！`);
    h.id = "tour-welcome-title";
    box.append(h, el("p", "muted", `跟著 ${total} 個小步驟完成設定，大約 2 分鐘，就能開始認識品味相近的人。`));
    const list = el("ol", "tour-welcome-steps");
    steps.forEach((s) => list.append(el("li", s.done ? "done" : "", s.title)));
    box.append(list);
    const actions = el("div", "tour-welcome-actions");
    const start = el("button", "btn", "開始教學");
    const skip = el("button", "btn secondary", "先跳過");
    start.type = skip.type = "button";
    actions.append(start, skip);
    box.append(actions, el("p", "muted small", "之後可以在「設定」重新開始教學。"));
    veil.append(box);
    document.body.append(veil);
    document.body.classList.add("tour-locked");
    start.focus();
    // Keep focus inside: this dialog needs an answer.
    veil.addEventListener("keydown", (e) => {
      if (e.key === "Tab") { e.preventDefault(); (document.activeElement === start ? skip : start).focus(); }
      if (e.key === "Escape") e.preventDefault();
    });
    start.addEventListener("click", async () => {
      start.disabled = skip.disabled = true;
      await post("start");
      const i = firstOpen();
      store.set(KEY, String(i));
      veil.remove();
      document.body.classList.remove("tour-locked");
      cfg.state = "active";
      if (i < total && pageOf(steps[i].href) !== location.pathname) go(steps[i].href);
      else show(i);
    });
    skip.addEventListener("click", async () => {
      start.disabled = skip.disabled = true;
      await post("skip");
      store.del(KEY);
      veil.classList.add("closing");
      document.body.classList.remove("tour-locked");
      setTimeout(() => veil.remove(), 250);
    });
  }

  // ---------- spotlight ring that follows the target ----------
  let ring = null, target = null, raf = 0;
  // Follow the target every frame: pages slide in, images load and panels open, so its box moves.
  function place() {
    if (!ring || !target) return;
    raf = requestAnimationFrame(place);
    const r = target.getBoundingClientRect();
    const pad = 8;
    Object.assign(ring.style, {
      top: `${r.top - pad}px`, left: `${r.left - pad}px`, width: `${r.width + pad * 2}px`, height: `${r.height + pad * 2}px`,
    });
    // Never cover what we're pointing at: move the card to the top while the target sits in the lower half.
    if (card) card.classList.toggle("top", r.top + r.height / 2 > innerHeight * 0.55);
  }
  function spotlight(node) {
    target = node;
    if (!ring) {
      ring = el("div", "tour-ring");
      document.body.append(ring);
    }
    node.scrollIntoView({ block: "center", behavior: "smooth" });
    cancelAnimationFrame(raf);
    place();
  }
  function clearSpotlight() {
    cancelAnimationFrame(raf);
    ring?.remove();
    ring = target = null;
  }
  function findTarget(step) {
    for (const sel of step.targets) {
      const node = document.querySelector(sel);
      if (node && node.getClientRects().length) return node;
    }
    return null;
  }

  // ---------- floating step card ----------
  let card = null;
  function show(i) {
    clearSpotlight();
    card?.remove();
    if (i >= total) return finish();
    const step = steps[i];
    store.set(KEY, String(i));
    const here = pageOf(step.href) === location.pathname;

    card = el("section", "tour-card");
    card.setAttribute("aria-live", "polite");
    const head = el("div", "tour-card-head");
    head.append(el("span", "tour-count", `第 ${i + 1} 步，共 ${total} 步`));
    const dots = el("span", "tour-dots");
    steps.forEach((s, j) => dots.append(el("span", (s.done ? "done" : "") + (j === i ? " on" : ""))));
    head.append(dots);
    const close = el("button", "tour-skip", "跳過教學");
    close.type = "button";
    head.append(close);
    card.append(head, el("h3", "", step.done ? `✓ ${step.title}` : step.title));
    card.append(el("p", "tour-hint", step.done ? "這一步完成了！" : here ? step.hint : `下一步在另一個頁面，按「前往」帶你過去。`));
    if (step.progress && !step.done) card.append(el("p", "tour-progress", step.progress));

    const actions = el("div", "tour-actions");
    if (i > 0) {
      const prev = el("button", "btn secondary small", "上一步");
      prev.type = "button";
      prev.addEventListener("click", () => move(i - 1));
      actions.append(prev);
    }
    const spacer = el("span", "tour-spacer");
    actions.append(spacer);
    if (!step.done) {
      const later = el("button", "link small muted", "略過這步");
      later.type = "button";
      later.addEventListener("click", () => move(i + 1));
      actions.append(later);
    }
    const main = el("button", "btn small", step.done ? (i + 1 === total ? "完成" : "下一步") : here ? "" : "前往");
    main.type = "button";
    if (main.textContent) {
      if (step.done) main.classList.add("pulse");
      main.addEventListener("click", () => (step.done ? move(i + 1) : go(step.href)));
      actions.append(main);
    }
    card.append(actions);
    document.body.append(card);
    requestAnimationFrame(() => card.classList.add("in"));
    close.addEventListener("click", skipTour);

    if (here && !step.done) {
      const want = hashOf(step.href);
      if (want && location.hash.slice(1) !== want) location.hash = want;  // e.g. the 動畫 tab of 收藏
      setTimeout(() => { const node = findTarget(step); if (node) spotlight(node); }, want ? 120 : 0);
    }
  }

  function move(i) {
    if (i >= total) return finish();
    const step = steps[Math.max(0, i)];
    store.set(KEY, String(Math.max(0, i)));
    if (pageOf(step.href) !== location.pathname) go(step.href);
    else show(Math.max(0, i));
  }

  async function skipTour() {
    if (!confirm("要跳過新手教學嗎？之後可以在「設定」重新開始。")) return;
    await post("skip");
    store.del(KEY);
    clearSpotlight();
    card?.remove();
  }

  async function finish() {
    clearSpotlight();
    card?.remove();
    await post("finish");
    store.del(KEY);
    const veil = el("div", "tour-veil");
    const box = el("div", "tour-welcome");
    box.append(el("div", "tour-welcome-mark", "🎉"), el("h2", "", "新手教學完成！"),
      el("p", "muted", "接下來可以到探索看看更多同好、玩小遊戲，或做一張 Recap 分享卡。"));
    const ok = el("button", "btn", "開始逛逛");
    ok.type = "button";
    ok.addEventListener("click", () => veil.remove());
    box.append(ok);
    veil.append(box);
    document.body.append(veil);
    ok.focus();
  }

  if (cfg.state === null) {
    welcome();
  } else {
    const saved = Number(store.get(KEY));
    const i = Number.isInteger(saved) && store.get(KEY) !== null && saved >= 0 && saved <= total ? saved : firstOpen();
    show(i);
  }
})();
