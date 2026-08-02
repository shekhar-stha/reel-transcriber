const {
  Document, Packer, Paragraph, TextRun, ExternalHyperlink, HeadingLevel,
  BorderStyle, PageBreak,
} = require('docx');
const fs = require('fs');

const BASE = '/Users/shekhar/Claude Code/reel-analysis/hooks-batch';
const data = JSON.parse(fs.readFileSync(BASE + '/progress.json', 'utf8')).sort((a, b) => a.num - b.num);

function fmtCount(n) {
  if (n == null) return null;
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K';
  return String(n);
}

const okRecs = data.filter(r => r.status === 'ok');
const okCount = okRecs.length;
const errCount = data.length - okCount;
const children = [];

children.push(new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun('1,000 Viral Hooks — Hook + Transcript Library')] }));
children.push(new Paragraph({
  spacing: { after: 120 },
  children: [new TextRun({
    text: `${okCount} of ${data.length} reels captured with on-screen text hook + full transcript. ${errCount} were blocked by Instagram rate-limiting (recoverable on retry). Generated ${new Date().toISOString().slice(0,10)}.`,
    italics: true, color: '666666',
  })],
}));
children.push(new Paragraph({ spacing: { after: 200 }, children: [new TextRun({ text: 'Note: on-screen text hooks are OCR-read from video frames and may include minor stray fragments (watermarks, captions). The core hook text is reliable.', italics: true, size: 18, color: '999999' })] }));

for (const r of data) {
  if (r.status !== 'ok') continue; // only include captured reels in the main doc

  children.push(new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(`#${r.num}  ·  ${r.section || ''}`)] }));

  children.push(new Paragraph({
    spacing: { after: 80 },
    children: [new TextRun({ text: 'Hook template: ', bold: true }), new TextRun({ text: r.hook || '—', italics: true })],
  }));

  // ON-SCREEN TEXT HOOK
  const th = (r.text_hook || '').trim();
  children.push(new Paragraph({
    spacing: { after: 80 },
    children: [
      new TextRun({ text: 'On-screen text hook: ', bold: true, color: 'B45309' }),
      new TextRun({ text: th ? th.replace(/\n/g, ' / ') : '(no on-screen text detected)' }),
    ],
  }));

  children.push(new Paragraph({
    spacing: { after: 80 },
    children: [
      new TextRun({ text: 'Link: ', bold: true }),
      new ExternalHyperlink({ children: [new TextRun({ text: r.resolved_link || r.link, style: 'Hyperlink' })], link: r.resolved_link || r.link }),
    ],
  }));

  const meta = [];
  if (r.uploader) meta.push('@' + r.uploader);
  if (fmtCount(r.like_count)) meta.push(fmtCount(r.like_count) + ' likes');
  if (fmtCount(r.comment_count)) meta.push(fmtCount(r.comment_count) + ' comments');
  if (r.duration) meta.push(Math.round(r.duration) + 's');
  if (meta.length) children.push(new Paragraph({ spacing: { after: 80 }, children: [new TextRun({ text: meta.join('  ·  '), size: 18, color: '888888' })] }));

  children.push(new Paragraph({ spacing: { before: 40, after: 40 }, children: [new TextRun({ text: 'Transcript', bold: true, size: 20 })] }));
  children.push(new Paragraph({
    spacing: { after: 120 }, indent: { left: 360 },
    border: { left: { style: BorderStyle.SINGLE, size: 18, color: 'D97706', space: 12 } },
    children: [new TextRun({ text: r.transcript || '(silent / no speech)', color: '222222' })],
  }));

  children.push(new Paragraph({ border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: 'DDDDDD', space: 8 } }, spacing: { after: 160 }, children: [new TextRun('')] }));
}

// Appendix: list of blocked reels for manual capture
const blocked = data.filter(r => r.status !== 'ok');
if (blocked.length) {
  children.push(new Paragraph({ children: [new PageBreak()] }));
  children.push(new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun('Appendix — Not yet captured')] }));
  children.push(new Paragraph({ spacing: { after: 120 }, children: [new TextRun({ text: `${blocked.length} reels blocked by Instagram rate-limiting. These are recoverable — the retry job will fill them in over time.`, italics: true, color: '666666' })] }));
  for (const r of blocked) {
    children.push(new Paragraph({
      spacing: { after: 60 },
      children: [
        new TextRun({ text: `#${r.num}  `, bold: true }),
        new TextRun({ text: (r.hook || '—') + '  ', size: 18 }),
        new ExternalHyperlink({ children: [new TextRun({ text: r.link, style: 'Hyperlink', size: 16 })], link: r.link }),
      ],
    }));
  }
}

const doc = new Document({
  creator: 'Reel Transcriber', title: '1,000 Viral Hooks Library',
  styles: {
    default: { document: { run: { font: 'Arial', size: 22 } } },
    paragraphStyles: [
      { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true, run: { size: 36, bold: true, font: 'Arial', color: '111111' }, paragraph: { spacing: { before: 200, after: 200 }, outlineLevel: 0 } },
      { id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true, run: { size: 25, bold: true, font: 'Arial', color: 'B45309' }, paragraph: { spacing: { before: 200, after: 80 }, outlineLevel: 1 } },
    ],
  },
  sections: [{ properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } } }, children }],
});

Packer.toBuffer(doc).then(buf => {
  const out = '/Users/shekhar/Claude Code/reel-analysis/Viral_Hooks_Library.docx';
  fs.writeFileSync(out, buf);
  console.log('✓ docx:', out, '(', (buf.length/1024).toFixed(0), 'KB,', okCount, 'reels )');
});

// Markdown version
let md = `# 1,000 Viral Hooks — Hook + Transcript Library\n\n${okCount}/${data.length} captured (text hook + transcript). ${errCount} blocked by rate-limiting (recoverable).\n\n---\n\n`;
for (const r of data) {
  if (r.status !== 'ok') continue;
  md += `## #${r.num} · ${r.section || ''}\n\n`;
  md += `**Hook template:** ${r.hook || '—'}\n\n`;
  md += `**On-screen text hook:** ${(r.text_hook || '(none detected)').replace(/\n/g, ' / ')}\n\n`;
  md += `**Link:** ${r.resolved_link || r.link}\n\n`;
  const meta = [];
  if (r.uploader) meta.push('@' + r.uploader);
  if (fmtCount(r.like_count)) meta.push(fmtCount(r.like_count) + ' likes');
  if (fmtCount(r.comment_count)) meta.push(fmtCount(r.comment_count) + ' comments');
  if (meta.length) md += `_${meta.join(' · ')}_\n\n`;
  md += `**Transcript:**\n\n> ${(r.transcript || '(silent)').replace(/\n/g, '\n> ')}\n\n---\n\n`;
}
fs.writeFileSync('/Users/shekhar/Claude Code/reel-analysis/Viral_Hooks_Library.md', md);
console.log('✓ markdown too');
