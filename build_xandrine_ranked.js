const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  ExternalHyperlink, HeadingLevel, BorderStyle, WidthType, ShadingType, PageBreak,
} = require('docx');
const fs = require('fs');

const data = JSON.parse(fs.readFileSync('/Users/shekhar/Claude Code/reel-analysis/xandrine_progress.json', 'utf8'))
  .filter(r => r.status === 'ok');

function fmtCount(n) {
  if (n == null) return '—';
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K';
  return String(n);
}

// Rank by pdf_views (desc). Reels without views go last.
const ranked = data.slice().sort((a, b) => (b.pdf_views || 0) - (a.pdf_views || 0));
const cellMargins = { top: 80, bottom: 80, left: 120, right: 120 };
const children = [];

children.push(new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun('Xandrine Reels — Ranked by Views')] }));
children.push(new Paragraph({ spacing: { after: 160 }, children: [new TextRun({ text: `All ${ranked.length} reels ranked most-viewed first. View counts from the original playbook PDF. TH = talking-head. Generated ${new Date().toISOString().slice(0,10)}.`, italics: true, color: '666666' })] }));

// Ranking table
const colW = [500, 1300, 2200, 1100, 700, 3560];
const rows = [new TableRow({ tableHeader: true, children: ['#','Views','Creator','Likes','Type','Link'].map((h,i) =>
  new TableCell({ width:{size:colW[i],type:WidthType.DXA}, margins:cellMargins, shading:{fill:'F4E4CC',type:ShadingType.CLEAR}, children:[new Paragraph({children:[new TextRun({text:h,bold:true,size:18})]})] })) })];
ranked.forEach((r, idx) => {
  rows.push(new TableRow({ children: [
    new TableCell({ width:{size:colW[0],type:WidthType.DXA}, margins:cellMargins, children:[new Paragraph({children:[new TextRun({text:String(idx+1),size:16})]})] }),
    new TableCell({ width:{size:colW[1],type:WidthType.DXA}, margins:cellMargins, children:[new Paragraph({children:[new TextRun({text:fmtCount(r.pdf_views),bold:true,size:16})]})] }),
    new TableCell({ width:{size:colW[2],type:WidthType.DXA}, margins:cellMargins, children:[new Paragraph({children:[new TextRun({text:'@'+r.handle,size:16})]})] }),
    new TableCell({ width:{size:colW[3],type:WidthType.DXA}, margins:cellMargins, children:[new Paragraph({children:[new TextRun({text:fmtCount(r.like_count),size:16})]})] }),
    new TableCell({ width:{size:colW[4],type:WidthType.DXA}, margins:cellMargins, children:[new Paragraph({children:[new TextRun({text:r.talking_head?'TH':'—',size:16,color:r.talking_head?'B45309':'AAAAAA'})]})] }),
    new TableCell({ width:{size:colW[5],type:WidthType.DXA}, margins:cellMargins, children:[new Paragraph({children:[new ExternalHyperlink({children:[new TextRun({text:r.code,style:'Hyperlink',size:14})],link:r.url})]})] }),
  ]}));
});
children.push(new Table({ width:{size:9360,type:WidthType.DXA}, columnWidths:colW, rows }));
children.push(new Paragraph({ children: [new PageBreak()] }));

// Full transcripts in ranked order (talking-head only get full transcript block)
children.push(new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun('Transcripts (ranked by views)')] }));
ranked.forEach((r, idx) => {
  children.push(new Paragraph({ heading: HeadingLevel.HEADING_2, spacing:{before:160,after:40},
    children: [new TextRun(`#${idx+1} · ${fmtCount(r.pdf_views)} views · @${r.handle}${r.talking_head?'':'  (non-talking-head)'}`)] }));
  children.push(new Paragraph({ spacing:{after:60}, children: [
    new ExternalHyperlink({ children:[new TextRun({text:r.url, style:'Hyperlink', size:18})], link:r.url }),
    new TextRun({ text: `   ·   ${fmtCount(r.like_count)} likes`, size:18, color:'888888' }),
  ]}));
  children.push(new Paragraph({
    spacing:{after:140}, indent:{left:360},
    border:{ left:{ style:BorderStyle.SINGLE, size:18, color:'D97706', space:12 } },
    children:[new TextRun({text: r.transcript || '(no speech — b-roll / text-only reel)', color: r.transcript?'222222':'999999', italics: !r.transcript})],
  }));
});

const doc = new Document({
  creator:'Reel Transcriber', title:'Xandrine Reels Ranked by Views',
  styles: { default:{document:{run:{font:'Arial',size:22}}}, paragraphStyles:[
    { id:'Heading1', name:'Heading 1', basedOn:'Normal', next:'Normal', quickFormat:true, run:{size:32,bold:true,font:'Arial',color:'111111'}, paragraph:{spacing:{before:200,after:160},outlineLevel:0} },
    { id:'Heading2', name:'Heading 2', basedOn:'Normal', next:'Normal', quickFormat:true, run:{size:21,bold:true,font:'Arial',color:'B45309'}, paragraph:{spacing:{before:160,after:60},outlineLevel:1} },
  ]},
  sections:[{ properties:{page:{size:{width:12240,height:15840},margin:{top:1440,right:1440,bottom:1440,left:1440}}}, children }],
});

Packer.toBuffer(doc).then(buf => {
  const out = '/Users/shekhar/Claude Code/reel-analysis/Xandrine_Ranked_By_Views.docx';
  fs.writeFileSync(out, buf);
  console.log('✓ docx:', out, '(', (buf.length/1024).toFixed(0), 'KB )');
});

// markdown
let md = `# Xandrine Reels — Ranked by Views\n\nAll ${ranked.length} reels, most-viewed first. Views from the playbook PDF.\n\n| # | Views | Creator | Likes | Type | Link |\n|---|---|---|---|---|---|\n`;
ranked.forEach((r,i)=>{ md += `| ${i+1} | ${fmtCount(r.pdf_views)} | @${r.handle} | ${fmtCount(r.like_count)} | ${r.talking_head?'TH':'—'} | ${r.url} |\n`; });
md += `\n---\n\n## Transcripts (ranked)\n\n`;
ranked.forEach((r,i)=>{ md += `### #${i+1} · ${fmtCount(r.pdf_views)} views · @${r.handle}${r.talking_head?'':' (non-TH)'}\n${r.url} · ${fmtCount(r.like_count)} likes\n\n> ${(r.transcript||'(no speech)').replace(/\n/g,'\n> ')}\n\n`; });
fs.writeFileSync('/Users/shekhar/Claude Code/reel-analysis/Xandrine_Ranked_By_Views.md', md);
console.log('✓ markdown too');
