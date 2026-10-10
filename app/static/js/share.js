// Share / download for game share cards. Markup (see _share.html):
//   <div data-share-box data-image="/x.jpg" data-filename="x.jpg" data-period="bingo" data-key="2026-10">
//     <button data-share hidden> <a data-download href download> <p data-share-tip hidden> <p data-download-tip>
// On phones the Web Share API opens the system sheet (Instagram Stories, Threads, ...);
// elsewhere only download is offered. Each share/download is logged as a CardEvent.
(() => {
  const probe = new File([""], "card.jpg", { type: "image/jpeg" });
  const canShare = !!(navigator.canShare && navigator.canShare({ files: [probe] }));

  document.querySelectorAll("[data-share-box]").forEach((box) => {
    const { image, filename, period, key } = box.dataset;
    const log = (action) =>
      fetch("/me/card/events", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ period, key, action }),
        keepalive: true,
      }).catch(() => {});

    box.querySelector("[data-download]")?.addEventListener("click", () => log("download"));
    const btn = box.querySelector("[data-share]");
    if (!btn || !canShare) return;
    btn.hidden = false;
    box.querySelector("[data-share-tip]")?.removeAttribute("hidden");
    box.querySelector("[data-download-tip]")?.setAttribute("hidden", "");
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      try {
        const blob = await (await fetch(image)).blob();
        await navigator.share({ files: [new File([blob], filename, { type: "image/jpeg" })] });
        log("share");
      } catch (e) {
        if (e.name !== "AbortError") alert("無法開啟分享，請改用「下載圖片」。");
      } finally {
        btn.disabled = false;
      }
    });
  });
})();
