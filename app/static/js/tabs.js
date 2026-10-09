// Tabs and "顯示更多" paging, shared by the profile and collection pages.
//
// Markup: a [role="tablist"] of [role="tab"][data-tab="name"] buttons (optional data-default),
// [role="tabpanel"][data-panel="name"] panels, [data-goto="name"] shortcut buttons, and
// [data-paged="24"] lists whose overflow items carry class "extra", revealed by a [data-more]
// button in the same <section>. Without JS every panel and item simply renders.
//
// The URL hash selects a tab (#music) or an element inside one (#entry-12), so redirects
// after a form post land back where the user was.
(() => {
  const tabs = [...document.querySelectorAll('[role="tab"]')];
  const panels = [...document.querySelectorAll('[role="tabpanel"]')];

  document.querySelectorAll("[data-more]").forEach((btn) => {
    const list = btn.closest("section").querySelector("[data-paged]");
    const page = Number(list.dataset.paged);
    btn.addEventListener("click", () => {
      const hidden = [...list.querySelectorAll(".extra")];
      hidden.slice(0, page).forEach((el) => el.classList.remove("extra"));
      if (hidden.length <= page) btn.remove();
    });
  });

  if (!tabs.length) return;
  document.documentElement.classList.add("js");
  const bar = tabs[0].closest('[role="tablist"]');
  const names = tabs.map((t) => t.dataset.tab);
  const fallback = bar.dataset.default || names[0];

  function show(name, scroll) {
    tabs.forEach((t) => t.setAttribute("aria-selected", String(t.dataset.tab === name)));
    panels.forEach((p) => (p.hidden = p.dataset.panel !== name));
    if (scroll && bar.getBoundingClientRect().top < 0) bar.scrollIntoView();
    history.replaceState(null, "", location.pathname + location.search + (name === fallback ? "" : "#" + name));
  }

  function resolve(hash, scroll) {
    if (names.includes(hash)) return show(hash, scroll);
    const target = hash && document.getElementById(hash);
    const panel = target && target.closest('[role="tabpanel"]');
    if (!panel) return show(fallback, scroll);
    show(panel.dataset.panel, false);
    target.classList.remove("extra");
    history.replaceState(null, "", location.pathname + location.search + "#" + hash);
    target.scrollIntoView({ block: "center" });
  }

  tabs.forEach((t) => t.addEventListener("click", () => show(t.dataset.tab, true)));
  document.querySelectorAll("[data-goto]").forEach((b) => b.addEventListener("click", () => show(b.dataset.goto, true)));
  window.addEventListener("hashchange", () => resolve(location.hash.slice(1), true));
  resolve(location.hash.slice(1), false);
})();
