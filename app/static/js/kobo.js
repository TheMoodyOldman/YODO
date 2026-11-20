(() => {
  const file = document.getElementById('kobo-file');
  if (!file) return;
  const feedback = document.getElementById('kobo-feedback');
  const panel = document.querySelector('[data-kobo-import]');
  let sqlPromise;
  function prepare() {
    if (sqlPromise) return;
    sqlPromise = new Promise((resolve, reject) => {
      const script=document.createElement('script'); script.src=panel.dataset.sqlJs;
      script.onload=() => {
        try { resolve(initSqlJs({locateFile:name => new URL(name,script.src).href})); }
        catch (error) { reject(error); }
      };
      script.onerror=() => reject(new Error('parser unavailable'));
      document.head.append(script);
    });
    sqlPromise.then(() => { file.disabled=false; feedback.textContent='選取檔案後會自動整理書單，再讓你確認。'; }).catch(() => { feedback.textContent='本機解析器無法載入，請重新整理或使用下方貼上書單。'; });
  }
  // Other collection tabs do not download the WASM parser. Prepare it only on screen.
  if ('IntersectionObserver' in window) {
    const observer=new IntersectionObserver(entries => {
      if (entries.some(entry => entry.isIntersecting)) { prepare(); observer.disconnect(); }
    });
    observer.observe(panel);
  } else { prepare(); }
  file.addEventListener('change', async () => {
    const selected=file.files[0]; if (!selected) return;
    file.disabled=true;
    try {
      if (selected.size>128*1024*1024) throw new Error('檔案超過 128 MB，請改用貼上書單。');
      feedback.textContent='正在本機整理書櫃，原始檔不會上傳…';
      const SQL=await sqlPromise;
      const result=YodoKobo.extract(SQL,new Uint8Array(await selected.arrayBuffer()),document.getElementById('kobo-scope').value);
      if (!result.books.length) throw new Error('這個範圍沒有書籍，請換成「全部」或使用貼上書單。');
      const payload=JSON.stringify(result);
      if (new TextEncoder().encode(payload).length>900000) throw new Error('書單太大，請縮小匯入範圍。');
      document.getElementById('kobo-payload').value=payload;
      feedback.textContent=`找到 ${result.books.length} 本，正在開啟確認清單…`;
      document.getElementById('kobo-upload').requestSubmit();
    } catch (error) { feedback.textContent=error.message.startsWith('檔案') || /書|範圍/.test(error.message) ? error.message : '檔案無法讀取，請確認選的是 KoboReader.sqlite，或改用貼上書單。'; file.disabled=false; file.value=''; }
  });
})();
