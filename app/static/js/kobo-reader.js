// Shared by the browser and Node fixture tests. Only allowlisted book columns leave the device.
(function (root) {
  function extract(SQL, bytes, scope = 'started') {
    if (bytes.byteLength > 128 * 1024 * 1024) throw new Error('檔案超過 128 MB，請改用貼上書單。');
    if (!['started', 'finished', 'all'].includes(scope)) throw new Error('閱讀範圍不正確。');
    const db = new SQL.Database(bytes);
    try {
      db.run('PRAGMA trusted_schema=OFF');
      const table = db.exec("SELECT type, sql FROM sqlite_master WHERE name='content'");
      if (!table.length || table[0].values[0][0] !== 'table' || /CREATE\s+VIRTUAL/i.test(table[0].values[0][1] || '')) throw new Error('這不是可讀取的 Kobo 書櫃檔案。');
      const columns = new Set(db.exec('PRAGMA table_info(content)')[0].values.map(r => r[1]));
      if (!['Title','ContentType','ReadStatus'].every(c => columns.has(c))) throw new Error('此 Kobo 書櫃版本缺少必要欄位，請改用貼上書單。');
      const select = ['Title', columns.has('Attribution') ? 'Attribution' : "''", columns.has('ISBN') ? 'ISBN' : "''", 'ReadStatus'];
      const where = ['ContentType = 6', 'ReadStatus IN (0,1,2)'];
      if (columns.has('BookID')) where.push('BookID IS NULL');
      if (scope === 'started') where.push('ReadStatus IN (1,2)');
      if (scope === 'finished') where.push('ReadStatus = 2');
      const result = db.exec(`SELECT ${select.join(',')} FROM content WHERE ${where.join(' AND ')} LIMIT 5001`);
      const rows = result.length ? result[0].values : [];
      if (rows.length > 5000) throw new Error('書籍超過 5000 本，請縮小匯入範圍。');
      const books = rows.filter(r => typeof r[0] === 'string' && r[0].trim()).map(r => ({title:r[0].trim(),author:String(r[1] || ''),isbn:String(r[2] || ''),status:Number(r[3]) === 2 ? 'read' : Number(r[3]) === 1 ? 'reading' : 'want'}));
      return {format:'yodo-kobo-v1',books};
    } finally { db.close(); }
  }
  root.YodoKobo = {extract};
  if (typeof module !== 'undefined') module.exports = {extract};
})(typeof globalThis !== 'undefined' ? globalThis : this);
