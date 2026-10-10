// Game invites: check /games/invites on load and every 15 s, and show a pop-up
// 「Mika 邀請你玩猜歌對戰」 with 加入 / 略過. Runs on every page for logged-in users.
(() => {
  const shown = new Set();
  let toast = null;

  function render(inv) {
    toast?.remove();
    toast = document.createElement("div");
    toast.className = "invite-toast";
    toast.setAttribute("role", "alertdialog");
    toast.setAttribute("aria-label", "遊戲邀請");
    const text = document.createElement("p");
    const who = document.createElement("strong");
    who.textContent = inv.from;
    text.append("🎮 ", who, ` 邀請你玩${inv.game}`);
    const join = document.createElement("a");
    join.className = "btn small";
    join.href = inv.url;
    join.textContent = "加入";
    const no = document.createElement("button");
    no.type = "button";
    no.className = "btn small secondary";
    no.textContent = "略過";
    no.addEventListener("click", async () => {
      toast.remove();
      toast = null;
      try { await fetch(`/games/invites/${inv.id}/decline`, { method: "POST" }); } catch {}
      check();
    });
    const actions = document.createElement("div");
    actions.className = "invite-actions";
    actions.append(no, join);
    toast.append(text, actions);
    document.body.append(toast);
    requestAnimationFrame(() => toast.classList.add("in"));
  }

  async function check() {
    if (document.hidden) return;
    try {
      const r = await fetch("/games/invites", { cache: "no-store" });
      if (!r.ok) return;
      const { invites } = await r.json();
      const next = invites.find((i) => i.url !== location.pathname && !shown.has(`${i.id}:${i.from}`));
      if (next && !toast) {
        shown.add(`${next.id}:${next.from}`);
        render(next);
      }
    } catch {}
  }

  check();
  setInterval(check, 15000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) check(); });
})();
