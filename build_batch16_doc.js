const { Document, Packer, Paragraph, TextRun, ExternalHyperlink, HeadingLevel, BorderStyle } = require('docx');
const fs = require('fs');

const data = JSON.parse(fs.readFileSync('/Users/shekhar/Claude Code/reel-analysis/batch16.json', 'utf8'));
function fmt(n){ if(n==null)return '—'; if(n>=1e6)return (n/1e6).toFixed(1)+'M'; if(n>=1e3)return (n/1e3).toFixed(1)+'K'; return ''+n; }

// clean OCR hook: collapse lines, trim obvious noise-only fragments
function cleanHook(h){
  return h.split('\n').map(s=>s.trim()).filter(Boolean).join(' / ');
}

// group by creator preserving first-seen order
const order = []; const groups = {};
for (const r of data){ const c=r.creator.split('|')[0].trim(); if(!groups[c]){groups[c]=[];order.push(c);} groups[c].push(r); }

const children = [];
children.push(new Paragraph({ heading: HeadingLevel.HEADING_1, children:[new TextRun('Reel Swipe File — Hooks + Transcripts')] }));
children.push(new Paragraph({ spacing:{after:200}, children:[new TextRun({text:`${data.length} reels across ${order.length} creators. Each entry: link · on-screen text hook · full transcript. Generated ${new Date().toISOString().slice(0,10)}.`, italics:true, color:'666666'})] }));

for (const c of order){
  children.push(new Paragraph({ heading: HeadingLevel.HEADING_1, spacing:{before:240}, children:[new TextRun(c)] }));
  for (const r of groups[c]){
    children.push(new Paragraph({ heading: HeadingLevel.HEADING_2, spacing:{before:160,after:40}, children:[new TextRun(`${fmt(r.likes)} likes`)] }));
    children.push(new Paragraph({ spacing:{after:50}, children:[
      new TextRun({text:'Link: ', bold:true}),
      new ExternalHyperlink({ children:[new TextRun({text:r.url, style:'Hyperlink'})], link:r.url }),
    ]}));
    children.push(new Paragraph({ spacing:{after:60}, children:[
      new TextRun({text:'Text hook: ', bold:true, color:'B45309'}),
      new TextRun({text: cleanHook(r.text_hook) || '(none detected)'}),
    ]}));
    children.push(new Paragraph({ spacing:{after:40}, children:[new TextRun({text:'Transcript', bold:true, size:20})] }));
    children.push(new Paragraph({
      spacing:{after:140}, indent:{left:360},
      border:{ left:{ style:BorderStyle.SINGLE, size:18, color:'D97706', space:12 } },
      children:[new TextRun({text:r.transcript, color:'222222'})],
    }));
    children.push(new Paragraph({ border:{bottom:{style:BorderStyle.SINGLE,size:4,color:'DDDDDD',space:8}}, spacing:{after:120}, children:[new TextRun('')] }));
  }
}

const doc = new Document({
  creator:'Reel Transcriber', title:'Reel Swipe File',
  styles:{ default:{document:{run:{font:'Arial',size:22}}}, paragraphStyles:[
    { id:'Heading1', name:'Heading 1', basedOn:'Normal', next:'Normal', quickFormat:true, run:{size:32,bold:true,font:'Arial',color:'111111'}, paragraph:{spacing:{before:200,after:120},outlineLevel:0} },
    { id:'Heading2', name:'Heading 2', basedOn:'Normal', next:'Normal', quickFormat:true, run:{size:22,bold:true,font:'Arial',color:'555555'}, paragraph:{spacing:{before:140,after:40},outlineLevel:1} },
  ]},
  sections:[{ properties:{page:{size:{width:12240,height:15840},margin:{top:1440,right:1440,bottom:1440,left:1440}}}, children }],
});
Packer.toBuffer(doc).then(buf=>{ const out='/Users/shekhar/Claude Code/reel-analysis/Reel_SwipeFile_16.docx'; fs.writeFileSync(out,buf); console.log('✓ docx:',out,'(',(buf.length/1024).toFixed(0),'KB )'); });

// markdown
let md = `# Reel Swipe File — Hooks + Transcripts\n\n${data.length} reels · ${order.length} creators.\n\n`;
for (const c of order){ md+=`\n## ${c}\n\n`; for(const r of groups[c]){ md+=`### ${fmt(r.likes)} likes\n**Link:** ${r.url}\n\n**Text hook:** ${cleanHook(r.text_hook)||'(none)'}\n\n**Transcript:**\n\n> ${r.transcript.replace(/\n/g,'\n> ')}\n\n---\n\n`; } }
fs.writeFileSync('/Users/shekhar/Claude Code/reel-analysis/Reel_SwipeFile_16.md', md);
console.log('✓ markdown too');
