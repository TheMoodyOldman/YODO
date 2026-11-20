// 拍照找書, all in the browser first: a barcode (BarcodeDetector: Chrome/Edge on Android, Samsung Internet,
// Chrome on macOS), then the printed ISBN digits (Tesseract.js, every browser). Either becomes a typed ISBN.
// Only a photo with no readable ISBN goes to the server's AI reader, when configured.
// The live camera needs HTTPS or localhost.
(() => {
  const root = document.querySelector("[data-bookscan]");
  if (!root) return;
  const aiReady = root.dataset.ai === "1";
  const status = root.querySelector("[data-status]");
  const isbnForm = root.querySelector("[data-isbn-form]");
  const isbnInput = isbnForm.querySelector("input[name=isbn]");
  const photoForm = root.querySelector("[data-photo-form]");
  const photoInput = root.querySelector("[data-photo-input]");
  const live = root.querySelector("[data-live]");
  const camera = root.querySelector("[data-camera]");
  const video = root.querySelector("[data-video]");
  const startBtn = root.querySelector("[data-start]");
  const stopBtn = root.querySelector("[data-stop]");

  const say = (text) => { status.textContent = text; };
  const isbnFrom = (raw) => {
    const d = String(raw || "").replace(/\D/g, "");
    return /^97[89]\d{10}$/.test(d) ? d : null;
  };

  let detector = null;
  async function getDetector() {
    if (detector) return detector;
    if (!("BarcodeDetector" in window)) return null;
    try {
      const formats = await window.BarcodeDetector.getSupportedFormats();
      if (!formats.includes("ean_13")) return null;
      detector = new window.BarcodeDetector({ formats: ["ean_13"] });
    } catch {
      return null;
    }
    return detector;
  }

  let busy = false;
  function submitIsbn(isbn) {
    if (busy) return;
    busy = true;
    stopCamera();
    isbnInput.value = isbn;
    say(`讀到 ISBN ${isbn}，查詢中…`);
    isbnForm.submit();
  }
  isbnForm.addEventListener("submit", () => say("查詢中…"));

  // ---------- live camera ----------
  let stream = null;
  let timer = null;
  function stopCamera() {
    clearInterval(timer);
    timer = null;
    if (stream) stream.getTracks().forEach((t) => t.stop());
    stream = null;
    camera.hidden = true;
    stopBtn.hidden = true;
    startBtn.hidden = false;
  }
  async function startCamera() {
    const d = await getDetector();
    if (!d) return;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false });
    } catch (e) {
      say(e && e.name === "NotAllowedError"
        ? "沒有取得相機權限。可以在瀏覽器設定允許相機，或改用下方的拍照。"
        : "無法開啟相機，請改用下方的拍照或輸入 ISBN。");
      return;
    }
    video.srcObject = stream;
    await video.play().catch(() => {});
    camera.hidden = false;
    startBtn.hidden = true;
    stopBtn.hidden = false;
    say("對準封底條碼…");
    timer = setInterval(async () => {
      if (!stream || video.readyState < 2) return;
      try {
        const codes = await d.detect(video);
        for (const code of codes) {
          const isbn = isbnFrom(code.rawValue);
          if (isbn) return submitIsbn(isbn);
        }
      } catch { /* a frame that cannot be read yet */ }
    }, 300);
  }
  startBtn.addEventListener("click", startCamera);
  stopBtn.addEventListener("click", () => { stopCamera(); say(""); });
  window.addEventListener("pagehide", stopCamera);

  // ---------- printed ISBN digits: Tesseract.js, free and on-device ----------
  // Loaded from jsDelivr only when a photo has no readable barcode; it then fetches its engine and the
  // English language data (a few MB, cached by the browser afterwards).
  const TESSERACT_URL = "https://cdn.jsdelivr.net/npm/tesseract.js@5.1.1/dist/tesseract.min.js";
  // iPhone photos are HEIC, which Chrome and Edge on Windows/Android cannot open: converted here first.
  const HEIC_URL = "https://cdnjs.cloudflare.com/ajax/libs/heic2any/0.0.3/heic2any.min.js";

  // An Error tagged with what went wrong, so the message can say what to do.
  const failure = (code, cause) => Object.assign(new Error(code), { code, cause });

  const scripts = {};
  function loadScript(url, globalName) {
    if (window[globalName]) return Promise.resolve(window[globalName]);
    if (!scripts[url]) {
      scripts[url] = new Promise((resolve, reject) => {
        const s = document.createElement("script");
        s.src = url;
        s.async = true;
        s.onload = () => (window[globalName] ? resolve(window[globalName]) : reject(failure("load")));
        s.onerror = () => { delete scripts[url]; reject(failure("load")); };
        document.head.appendChild(s);
      });
    }
    return scripts[url];
  }
  const loadTesseract = () => loadScript(TESSERACT_URL, "Tesseract");

  const isHeic = (file) => /hei[cf]/i.test(file.type) || /\.hei[cf]$/i.test(file.name);

  // A photo this browser can draw: the original, or a JPEG made from an iPhone HEIC photo.
  async function usablePhoto(file) {
    try {
      const bitmap = await createImageBitmap(file);
      if (bitmap.close) bitmap.close();
      return file;
    } catch (e) {
      if (!isHeic(file)) throw failure("decode", e);
    }
    say("轉換 iPhone 照片格式（HEIC）中…");
    const heic2any = await loadScript(HEIC_URL, "heic2any");
    let out;
    try {
      out = await heic2any({ blob: file, toType: "image/jpeg", quality: 0.9 });
    } catch (e) {
      throw failure("heic", e);
    }
    if (Array.isArray(out)) out = out[0];  // a burst/live photo gives several images
    const jpeg = new File([out], file.name.replace(/\.hei[cf]$/i, "") + ".jpg", { type: "image/jpeg" });
    try {  // so the server also gets the JPEG if the photo goes on to the AI reader
      const dt = new DataTransfer();
      dt.items.add(jpeg);
      photoInput.files = dt.files;
    } catch { /* older browsers: the AI reader then gets the original */ }
    return jpeg;
  }

  const MESSAGES = {
    decode: "讀不了這個照片格式，請改用 JPG 或 PNG 照片，或在下面輸入 ISBN。",
    heic: "這張 iPhone 照片（HEIC 格式）無法在這個瀏覽器轉換。請改傳 JPG（iPhone「設定 → 相機 → 格式」選「最相容」），或直接用手機打開這個網頁拍照。",
    load: "辨識工具下載失敗，請確認網路連線後再試（廣告封鎖外掛也可能擋住），或在下面輸入 ISBN。",
    ocr: "文字辨識失敗，請換一張照片再試，或在下面輸入 ISBN。",
  };

  function isbn13Ok(d) {
    if (!/^97[89]\d{10}$/.test(d)) return false;
    let sum = 0;
    for (let i = 0; i < 13; i++) sum += Number(d[i]) * (i % 2 ? 3 : 1);
    return sum % 10 === 0;
  }
  function isbn10Ok(d) {
    if (!/^\d{9}[\dX]$/.test(d)) return false;
    let sum = 0;
    for (let i = 0; i < 10; i++) sum += (10 - i) * (d[i] === "X" ? 10 : Number(d[i]));
    return sum % 11 === 0;
  }
  // Same rule as find_all in app/isbn.py. Text is read as whole runs of digits joined by spaces or
  // dashes, never cut in the middle: the first ten digits of an ISBN-13 are often a valid ISBN-10 by
  // chance (978-986-7778-17-8 -> 9789867778), which would open the wrong book.
  function isbnInText(text) {
    const runs = String(text).toUpperCase().match(/[0-9X](?:[ \t\-‐-―]*[0-9X])*/g) || [];
    for (const run of runs) {
      const d = run.replace(/[^0-9X]/g, "");
      if (d.length === 10) {
        // An ISBN-10, unless it starts 978/979: then it is an ISBN-13 that lost digits.
        if (isbn10Ok(d) && !/^97[89]/.test(d)) return d;  // the server turns it into an ISBN-13
        continue;
      }
      for (let i = 0; i + 13 <= d.length; i++) {  // a barcode's price add-on can be glued on
        if (isbn13Ok(d.slice(i, i + 13))) return d.slice(i, i + 13);
      }
    }
    return null;
  }

  // Large phone photos are slow to read and no more accurate: scale to ≤ 2000 px on the long edge.
  async function photoCanvas(file) {
    const bitmap = await createImageBitmap(file);
    const scale = Math.min(1, 2000 / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    canvas.getContext("2d").drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    if (bitmap.close) bitmap.close();
    return canvas;
  }

  async function readPrintedIsbn(file) {
    say("讀取照片上的 ISBN…（第一次使用要先下載辨識資料）");
    const Tesseract = await loadTesseract();
    const canvas = await photoCanvas(file);
    const worker = await Tesseract.createWorker("eng", 1, {
      logger: (m) => {
        if (m.status === "recognizing text") say(`讀取照片上的 ISBN… ${Math.round((m.progress || 0) * 100)}%`);
      },
    });
    try {
      await worker.setParameters({ tessedit_char_whitelist: "0123456789-XISBN " });
      const { data } = await worker.recognize(canvas);
      return isbnInText(data.text);
    } finally {
      await worker.terminate();
    }
  }

  // ---------- photo: barcode -> printed digits -> server AI ----------
  photoInput.addEventListener("change", async () => {
    let file = photoInput.files && photoInput.files[0];
    if (!file) return;
    say("讀取照片中…");
    try {
      file = await usablePhoto(file);
    } catch (e) {
      console.error("拍照找書：無法讀取照片", e.cause || e);
      say(MESSAGES[e.code] || MESSAGES.decode);
      photoInput.value = "";
      return;
    }
    const d = await getDetector();
    if (d) {
      try {
        const codes = await d.detect(await createImageBitmap(file));
        for (const code of codes) {
          const isbn = isbnFrom(code.rawValue);
          if (isbn) return submitIsbn(isbn);
        }
      } catch { /* no barcode here: read the digits instead */ }
    }

    let problem = null;
    try {
      const isbn = await readPrintedIsbn(file);
      if (isbn) return submitIsbn(isbn);
    } catch (e) {
      console.error("拍照找書：文字辨識失敗", e.cause || e);
      problem = e.code === "load" ? "load" : "ocr";
    }

    if (aiReady) {
      say("照片裡讀不到 ISBN，改讀封面的書名與作者…（約 5～15 秒）");
      photoForm.submit();
      return;
    }
    say(problem
      ? MESSAGES[problem]
      : "這張照片裡讀不到 ISBN。請把 ISBN 那一行拍清楚、拍正再試，或在下面輸入 ISBN。");
    photoInput.value = "";
  });

  // The live camera needs a barcode reader and a secure page (HTTPS or localhost).
  getDetector().then((d) => {
    const secure = window.isSecureContext && navigator.mediaDevices && navigator.mediaDevices.getUserMedia;
    if (d && secure) live.hidden = false;
  });
})();
