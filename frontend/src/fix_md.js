const fs = require('fs');
const c = fs.readFileSync('App.js', 'utf8');
const fn = 
function renderMarkdown(t) {
  if (!t || typeof t !== 'string') return t;
  var h = t.replace(/&amp;/g,'&').replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&quot;/g,'"');
  if (h.indexOf('|') === -1) { return h; }
  var lines = h.split('\n'), out = [], tbl = [];
  for (var i = 0; i < lines.length; i++) {
    var lt = lines[i].trim();
    if (lt.charAt(0) === '|' && lt.charAt(lt.length-1) === '|') { tbl.push(lt); }
    else {
      if (tbl.length) { out.push(tbl.join('<br>')); tbl = []; }
      if (lt) out.push(lt);
    }
  }
  if (tbl.length) out.push(tbl.join('<br>'));
  return out.join('<br>');
}
function renderT(t) {
  var rows = t.split('\n').filter(function(l){ return !l.match(/^[|\s:-]+\$/); });
  if (rows.length < 2) return t;
  var hs = rows[0].split('|').filter(function(x,i,a){ return i>0 && i<a.length-1; }).map(function(x){ return x.trim(); });
  var html = '<table style=border-collapse:collapse;width:100%;font-size:13px><thead><tr>';
  hs.forEach(function(hd){ html += '<th style=border:1px solid #e5e7eb;padding:6px 10px;background:#f3f4f6;font-weight:600>' + hd + '</th>'; });
  html += '</tr></thead><tbody>';
  for (var i=1; i<rows.length; i++) {
    var cells = rows[i].split('|').filter(function(x,j,a){ return j>0 && j<a.length-1; }).map(function(x){ return x.trim(); });
    var bg = i%2===1 ? '#f9fafb' : '';
    html += '<tr>';
    cells.forEach(function(cell){ html += '<td style=border:1px solid #e5e7eb;padding:6px 10px' + (bg?' background:'+bg:'') + '>' + cell + '</td>'; });
    html += '</tr>';
  }
  return html + '</tbody></table>';
}
module.exports = {renderMarkdown};
; 
const patched = fn + '\n' + c.replace(/cleanContent\s*\}/g, 'renderMarkdown(content)}');
fs.writeFileSync('App.js', patched);
console.log('Patched OK', patched.length);