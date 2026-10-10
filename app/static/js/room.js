// Live room polling: <body ... data-room-poll="/games/room/<kind>/<code>/v" data-room-version="...">
// Reloads when anyone changes the room. If the player is typing, shows a banner instead of
// throwing their text away.
(() => {
  const el = document.querySelector("[data-room-poll]");
  if (!el) return;
  const url = el.dataset.roomPoll;
  let current = el.dataset.roomVersion;
  const typing = () => {
    const a = document.activeElement;
    return a && (a.tagName === "TEXTAREA" || (a.tagName === "INPUT" && a.type === "text")) && a.value.trim();
  };
  async function poll() {
    try {
      const r = await fetch(url, { cache: "no-store" });
      if (r.ok) {
        const { v } = await r.json();
        if (v !== current) {
          if (window.roomBusy) {  // e.g. a song clip is playing: check again shortly
            setTimeout(poll, 700);
            return;
          }
          if (typing()) {
            document.querySelector("[data-room-stale]")?.removeAttribute("hidden");
            current = v;
          } else {
            location.reload();
            return;
          }
        }
      }
    } catch {}
    setTimeout(poll, 2000);
  }
  setTimeout(poll, 2000);
})();
