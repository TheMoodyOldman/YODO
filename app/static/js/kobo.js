(() => {
  const file = document.getElementById('kobo-file');
  const feedback = document.getElementById('kobo-feedback');
  const script = [...document.scripts].find(s => s.src.includes('/vendor/sql.js/sql-wasm.js'));
  let sqlPromise;
  try {
    sqlPromise = initSqlJs({locateFile:name => new URL(name, script.src).href});
    sqlPromise.then(() => { file.disabled=false; feedback.textContent='選取檔案後會自動整理書單，再讓你確認。'; }).catch(() => { feedback.textContent='本機解析器無法載入，請重新整理或使用下方貼上書單。'; });
  } catch { feedback.textContent='本機解析器無法載入，請使用下方貼上書單。'; }
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
