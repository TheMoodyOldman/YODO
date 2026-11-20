// Shared cover multi-select (templates/_cover_picker.html): live 「已選 N」 count, a busy 完成 button,
// and search boxes that add result tiles to their tab. Works on every form with [data-picker].
(() => {
  document.querySelectorAll("form[data-picker]").forEach((form) => {
    const out = form.querySelector("[data-count]");
    const update = () => {
      if (out) out.textContent = form.querySelectorAll('input[name="pick"]:checked:not(:disabled)').length;
    };
    form.addEventListener("change", update);
    form.addEventListener("submit", () => {
      const btn = form.querySelector('.season-bar button[type="submit"]');
      if (btn) { btn.disabled = true; btn.textContent = "儲存中…"; }
    });
    update();
  });

  // Search: GET <data-search-url>?cat=..&q=.. -> {items: [{key, title, sub, cover}], error}
  document.querySelectorAll("[data-picker-search]").forEach((box) => {
    const input = box.querySelector("input");
    const button = box.querySelector("button");
    const grid = document.querySelector(box.dataset.target);
    const note = box.querySelector("[data-search-note]");
    const form = grid.closest("form");
    const tile = (item) => {
      const label = document.createElement("label");
      label.className = "season-pick" + (box.dataset.square ? " square" : "");
      const cb = document.createElement("input");
      cb.type = "checkbox"; cb.name = "pick"; cb.value = item.key; cb.checked = true;
      const cover = document.createElement("span");
      cover.className = "season-cover";
      if (item.cover) {
        const img = document.createElement("img");
        img.src = item.cover; img.alt = ""; img.loading = "lazy";
        cover.append(img);
      } else {
        const ini = document.createElement("span");
        ini.className = "season-initial"; ini.textContent = (item.title || "?").slice(0, 1);
        cover.append(ini);
      }
      const check = document.createElement("span");
      check.className = "season-check"; check.innerHTML = "&#10003;";
      cover.append(check);
      const title = document.createElement("span");
      title.className = "season-title"; title.textContent = item.title;
      label.append(cb, cover, title);
      if (item.sub) { const sub = document.createElement("span"); sub.className = "season-sub"; sub.textContent = item.sub; label.append(sub); }
      return label;
    };
    const run = async () => {
      const q = input.value.trim();
      if (!q) return;
      button.disabled = true;
      note.textContent = "搜尋中…";
      try {
        const r = await fetch(`${box.dataset.searchUrl}?cat=${encodeURIComponent(box.dataset.cat)}&q=${encodeURIComponent(q)}`);
        const data = await r.json();
        if (data.error) { note.textContent = data.error; return; }
        const existing = new Set([...grid.querySelectorAll('input[name="pick"]')].map((i) => i.value));
        const fresh = data.items.filter((i) => !existing.has(i.key));
        note.textContent = data.items.length ? `找到 ${data.items.length} 筆，點封面勾選或取消` : "找不到，換個關鍵字試試";
        // Results go on top, unticked: the user picks what they meant.
        fresh.reverse().forEach((item) => { const t = tile(item); t.querySelector("input").checked = false; grid.prepend(t); });
        form.dispatchEvent(new Event("change"));
      } catch {
        note.textContent = "搜尋暫時無法使用，請稍後再試";
      } finally {
        button.disabled = false;
      }
    };
    button.addEventListener("click", run);
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); run(); } });
  });
})();
