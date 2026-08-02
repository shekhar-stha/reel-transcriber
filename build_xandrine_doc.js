const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  ExternalHyperlink, HeadingLevel, BorderStyle, WidthType, ShadingType, PageBreak,
} = require('docx');
const fs = require('fs');

const data = JSON.parse(fs.readFileSync('/Users/shekhar/Claude Code/reel-analysis/xandrine_progress.json', 'utf8'));

function fmtCount(n) {
  if (n == null) return '—';
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K';
  return String(n);
}

// group by creator
const byCreator = {};
for (const r of data) {
  if (r.status !== 'ok') continue;
  (byCreator[r.handle] ||= []).push(r);
}
const creators = Object.keys(byCreator).sort();
const cellMargins = { top: 80, bottom: 80, left: 120, right: 120 };
const children = [];

// Title + summary
const totalTH = data.filter(r => r.status === 'ok' && r.talking_head).length;
children.push(new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun('Xandrine Content Playbook — Talking-Head Transcripts')] }));
children.push(new Paragraph({ spacing: { after: 120 }, children: [new TextRun({ text: `${data.length} reels from ${creators.length} creators · ${totalTH} talking-head reels transcribed · grouped by creator. Generated ${new Date().toISOString().slice(0,10)}.`, italics: true, color: '666666' })] }));

// Summary table by creator
const colW = [3200, 1400, 1400, 3360];
const rows = [new TableRow({ tableHeader: true, children: ['Creator', 'Talking-head', 'Other', 'Total reels'].map((h,i) => new TableCell({ width:{size:colW[i],type:WidthType.DXA}, margins:cellMargins, shading:{fill:'F4E4CC',type:ShadingType.CLEAR}, children:[new Paragraph({children:[new TextRun({text:h,bold:true,size:18})]})] })) })];
for (const c of creators) {
  const list = byCreator[c];
  const th = list.filter(r => r.talking_head).length;
  rows.push(new TableRow({ children: [
    new TableCell({ width:{size:colW[0],type:WidthType.DXA}, margins:cellMargins, children:[new Paragraph({children:[new TextRun({text:'@'+c,size:18})]})] }),
    new TableCell({ width:{size:colW[1],type:WidthType.DXA}, margins:cellMargins, children:[new Paragraph({children:[new TextRun({text:String(th),size:18})]})] }),
    new TableCell({ width:{size:colW[2],type:WidthType.DXA}, margins:cellMargins, children:[new Paragraph({children:[new TextRun({text:String(list.length-th),size:18})]})] }),
    new TableCell({ width:{size:colW[3],type:WidthType.DXA}, margins:cellMargins, children:[new Paragraph({children:[new TextRun({text:String(list.length),size:18})]})] }),
  ]}));
}
children.push(new Table({ width:{size:9360,type:WidthType.DXA}, columnWidths:colW, rows }));
children.push(new Paragraph({ children: [new PageBreak()] }));

// Per creator sections
for (const c of creators) {
  const list = byCreator[c].sort((a,b) => (b.like_count||0)-(a.like_count||0));
  children.push(new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun('@' + c)] }));

  // Talking-head reels first
  const th = list.filter(r => r.talking_head);
  const other = list.filter(r => !r.talking_head);

  for (const r of th) {
    children.push(new Paragraph({ heading: HeadingLevel.HEADING_2, spacing:{before:160,after:40}, children: [new TextRun(r.uploader || ('@'+c))] }));
    const meta = [];
    if (r.pdf_views != null) meta.push(fmtCount(r.pdf_views)+' views');
    if (fmtCount(r.like_count) !== '—') meta.push(fmtCount(r.like_count)+' likes');
    if (fmtCount(r.comment_count) !== '—') meta.push(fmtCount(r.comment_count)+' comments');
    if (r.duration) meta.push(Math.round(r.duration)+'s');
    children.push(new Paragraph({ spacing:{after:60}, children: [
      new ExternalHyperlink({ children:[new TextRun({text:r.url, style:'Hyperlink', size:18})], link:r.url }),
    ]}));
    if (meta.length) children.push(new Paragraph({ spacing:{after:60}, children:[new TextRun({text:meta.join('  ·  '), size:18, color:'888888'})] }));
    children.push(new Paragraph({
      spacing:{after:140}, indent:{left:360},
      border:{ left:{ style:BorderStyle.SINGLE, size:18, color:'D97706', space:12 } },
      children:[new TextRun({text:r.transcript || '(no speech)', color:'222222'})],
    }));
  }

  // Non-talking-head: compact list
  if (other.length) {
    children.push(new Paragraph({ spacing:{before:120,after:40}, children:[new TextRun({text:'Non-talking-head (b-roll / text-only):', bold:true, size:18, color:'999999'})] }));
    for (const r of other) {
      children.push(new Paragraph({ spacing:{after:30}, children:[
        new ExternalHyperlink({ children:[new TextRun({text:r.url, style:'Hyperlink', size:16})], link:r.url }),
        new TextRun({ text: `   ${fmtCount(r.like_count)} likes`, size:16, color:'999999' }),
        ...(r.transcript ? [new TextRun({ text: ` — "${r.transcript.slice(0,80)}${r.transcript.length>80?'…':''}"`, size:16, italics:true, color:'AAAAAA' })] : []),
      ]}));
    }
  }
  children.push(new Paragraph({ children: [new PageBreak()] }));
}

const doc = new Document({
  creator:'Reel Transcriber', title:'Xandrine Talking-Head Transcripts',
  styles: { default:{document:{run:{font:'Arial',size:22}}}, paragraphStyles:[
    { id:'Heading1', name:'Heading 1', basedOn:'Normal', next:'Normal', quickFormat:true, run:{size:32,bold:true,font:'Arial',color:'111111'}, paragraph:{spacing:{before:200,after:160},outlineLevel:0} },
    { id:'Heading2', name:'Heading 2', basedOn:'Normal', next:'Normal', quickFormat:true, run:{size:22,bold:true,font:'Arial',color:'B45309'}, paragraph:{spacing:{before:160,after:60},outlineLevel:1} },
  ]},
  sections:[{ properties:{page:{size:{width:12240,height:15840},margin:{top:1440,right:1440,bottom:1440,left:1440}}}, children }],
});

Packer.toBuffer(doc).then(buf => {
  const out = '/Users/shekhar/Claude Code/reel-analysis/Xandrine_TalkingHead_Transcripts.docx';
  fs.writeFileSync(out, buf);
  console.log('✓ docx:', out, '(', (buf.length/1024).toFixed(0), 'KB )');
});

// markdown
let md = `# Xandrine Content Playbook — Talking-Head Transcripts\n\n${data.length} reels · ${creators.length} creators · ${totalTH} talking-head. Grouped by creator.\n\n`;
for (const c of creators) {
  const list = byCreator[c].sort((a,b)=>(b.like_count||0)-(a.like_count||0));
  md += `\n## @${c}\n\n`;
  for (const r of list.filter(r=>r.talking_head)) {
    md += `### ${r.uploader||('@'+c)}\n`;
    md += `${r.url}\n`;
    const meta=[]; if(r.pdf_views!=null)meta.push(fmtCount(r.pdf_views)+' views'); if(fmtCount(r.like_count)!=='—')meta.push(fmtCount(r.like_count)+' likes'); if(fmtCount(r.comment_count)!=='—')meta.push(fmtCount(r.comment_count)+' comments');
    if(meta.length) md += `_${meta.join(' · ')}_\n`;
    md += `\n> ${(r.transcript||'(no speech)').replace(/\n/g,'\n> ')}\n\n`;
  }
  const other = list.filter(r=>!r.talking_head);
  if(other.length){ md += `**Non-talking-head:**\n`; for(const r of other){ md += `- ${r.url} (${fmtCount(r.like_count)} likes)\n`; } md += `\n`; }
}
fs.writeFileSync('/Users/shekhar/Claude Code/reel-analysis/Xandrine_TalkingHead_Transcripts.md', md);
console.log('✓ markdown too');
