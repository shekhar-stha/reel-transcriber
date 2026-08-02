const { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, ExternalHyperlink, HeadingLevel, BorderStyle, WidthType, ShadingType, PageBreak } = require('docx');
const fs = require('fs');

const all = JSON.parse(fs.readFileSync('/Users/shekhar/Claude Code/reel-analysis/beckie_progress.json', 'utf8'));
function fmt(n){ if(n==null)return '—'; if(n>=1e6)return (n/1e6).toFixed(1)+'M'; if(n>=1e3)return (n/1e3).toFixed(1)+'K'; return ''+n; }
function cleanHook(h){ return (h||'').split('\n').map(s=>s.trim()).filter(Boolean).join(' / '); }

const th = all.filter(r=>r.status==='ok'&&r.talking_head).sort((a,b)=>(b.like_count||0)-(a.like_count||0));

// interview/dialogue reels (manually flagged by code)
const DIALOGUE = new Set(['DbKZ-jBs28v']); // @ari "sell me this pen"
// Split a dialogue transcript into alternating turns on question/answer cues (best-effort)
function dialogueParagraphs(text){
  // ari's pen pitch: alternate Salesperson / Prospect. Split on sentence boundaries, heuristic speaker toggle.
  // Simpler: present as a note + raw transcript in quote (kept readable). We mark it as interview.
  return null;
}

const children = [];
children.push(new Paragraph({ heading:HeadingLevel.HEADING_1, children:[new TextRun('Beckie Sales — Talking-Head Swipe File')] }));
children.push(new Paragraph({ spacing:{after:160}, children:[new TextRun({text:`${th.length} talking-head reels from your saved collection, ranked by likes. Each: text hook · creator · likes · full transcript. Interview/dialogue reels are flagged. Generated ${new Date().toISOString().slice(0,10)}.`, italics:true, color:'666666'})] }));

th.forEach((r, i) => {
  const isDlg = DIALOGUE.has(r.code);
  children.push(new Paragraph({ heading:HeadingLevel.HEADING_2, spacing:{before:180,after:40},
    children:[new TextRun(`#${i+1} · @${r.uploader||'?'} · ${fmt(r.like_count)} likes · ${Math.round(r.duration)}s${isDlg?'  [INTERVIEW / DIALOGUE]':''}`)] }));
  children.push(new Paragraph({ spacing:{after:50}, children:[
    new TextRun({text:'Link: ',bold:true}), new ExternalHyperlink({children:[new TextRun({text:r.url,style:'Hyperlink'})],link:r.url}) ]}));
  children.push(new Paragraph({ spacing:{after:60}, children:[
    new TextRun({text:'Text hook: ',bold:true,color:'B45309'}), new TextRun({text:cleanHook(r.text_hook)||'(none detected)'}) ]}));
  if (isDlg){
    children.push(new Paragraph({ spacing:{after:50}, children:[new TextRun({text:'Format: two-person role-play (salesperson ↔ prospect). Transcript below is the full exchange; speaker turns alternate through the question-answer flow.', italics:true, size:18, color:'888888'})] }));
  }
  children.push(new Paragraph({ spacing:{after:40}, children:[new TextRun({text:'Transcript',bold:true,size:20})] }));
  children.push(new Paragraph({ spacing:{after:140}, indent:{left:360},
    border:{left:{style:BorderStyle.SINGLE,size:18,color:'D97706',space:12}}, children:[new TextRun({text:r.transcript,color:'222222'})] }));
  children.push(new Paragraph({ border:{bottom:{style:BorderStyle.SINGLE,size:4,color:'DDDDDD',space:8}}, spacing:{after:120}, children:[new TextRun('')] }));
});

// Creator directory
children.push(new Paragraph({ children:[new PageBreak()] }));
children.push(new Paragraph({ heading:HeadingLevel.HEADING_1, children:[new TextRun('Creator Directory (for research / repurposing)')] }));
children.push(new Paragraph({ spacing:{after:120}, children:[new TextRun({text:'Every creator in the collection, with reel count and combined likes. All sales / marketing / persuasion focused.', italics:true, color:'666666'})] }));
const byC = {};
all.filter(r=>r.status==='ok').forEach(r=>{ const c=r.uploader||'(unknown)'; if(!byC[c]) byC[c]={n:0,likes:0,th:0,urls:[]}; byC[c].n++; byC[c].likes+=(r.like_count||0); if(r.talking_head)byC[c].th++; byC[c].urls.push(r.url); });
const creators = Object.entries(byC).sort((a,b)=>b[1].likes-a[1].likes);
const cw=[3400,900,900,4160];
const rows=[new TableRow({tableHeader:true,children:['Creator','Reels','Talking-head','Combined likes'].map((h,i)=>new TableCell({width:{size:cw[i],type:WidthType.DXA},margins:{top:80,bottom:80,left:120,right:120},shading:{fill:'F4E4CC',type:ShadingType.CLEAR},children:[new Paragraph({children:[new TextRun({text:h,bold:true,size:18})]})]}))})];
creators.forEach(([c,v])=>{ rows.push(new TableRow({children:[
  new TableCell({width:{size:cw[0],type:WidthType.DXA},margins:{top:80,bottom:80,left:120,right:120},children:[new Paragraph({children:[new TextRun({text:'@'+c,size:18})]})]}),
  new TableCell({width:{size:cw[1],type:WidthType.DXA},margins:{top:80,bottom:80,left:120,right:120},children:[new Paragraph({children:[new TextRun({text:''+v.n,size:18})]})]}),
  new TableCell({width:{size:cw[2],type:WidthType.DXA},margins:{top:80,bottom:80,left:120,right:120},children:[new Paragraph({children:[new TextRun({text:''+v.th,size:18})]})]}),
  new TableCell({width:{size:cw[3],type:WidthType.DXA},margins:{top:80,bottom:80,left:120,right:120},children:[new Paragraph({children:[new TextRun({text:fmt(v.likes),size:18})]})]}),
]}))});
children.push(new Table({width:{size:9360,type:WidthType.DXA},columnWidths:cw,rows}));

const doc = new Document({ creator:'Reel Transcriber', title:'Beckie Sales Swipe File',
  styles:{ default:{document:{run:{font:'Arial',size:22}}}, paragraphStyles:[
    {id:'Heading1',name:'Heading 1',basedOn:'Normal',next:'Normal',quickFormat:true,run:{size:30,bold:true,font:'Arial',color:'111111'},paragraph:{spacing:{before:200,after:120},outlineLevel:0}},
    {id:'Heading2',name:'Heading 2',basedOn:'Normal',next:'Normal',quickFormat:true,run:{size:21,bold:true,font:'Arial',color:'555555'},paragraph:{spacing:{before:160,after:40},outlineLevel:1}} ]},
  sections:[{properties:{page:{size:{width:12240,height:15840},margin:{top:1440,right:1440,bottom:1440,left:1440}}},children}] });
Packer.toBuffer(doc).then(buf=>{ const out='/Users/shekhar/Claude Code/reel-analysis/Beckie_Sales_SwipeFile.docx'; fs.writeFileSync(out,buf); console.log('✓ docx:',out,'(',(buf.length/1024).toFixed(0),'KB )'); });

// markdown
let md=`# Beckie Sales — Talking-Head Swipe File\n\n${th.length} talking-head reels, ranked by likes.\n\n`;
th.forEach((r,i)=>{ md+=`## #${i+1} · @${r.uploader} · ${fmt(r.like_count)} likes · ${Math.round(r.duration)}s${DIALOGUE.has(r.code)?' [INTERVIEW]':''}\n**Link:** ${r.url}\n\n**Text hook:** ${cleanHook(r.text_hook)||'(none)'}\n\n**Transcript:**\n\n> ${r.transcript.replace(/\n/g,'\n> ')}\n\n---\n\n`; });
md+=`\n# Creator Directory\n\n| Creator | Reels | Talking-head | Combined likes |\n|---|---|---|---|\n`;
creators.forEach(([c,v])=>{ md+=`| @${c} | ${v.n} | ${v.th} | ${fmt(v.likes)} |\n`; });
fs.writeFileSync('/Users/shekhar/Claude Code/reel-analysis/Beckie_Sales_SwipeFile.md', md);
console.log('✓ markdown too');
