const { Document, Packer, Paragraph, TextRun, ExternalHyperlink, HeadingLevel, BorderStyle } = require('docx');
const fs = require('fs');
const data = JSON.parse(fs.readFileSync('/Users/shekhar/Claude Code/reel-analysis/tim_progress.json','utf8'))
  .filter(r=>r.status==='ok').sort((a,b)=>b.views-a.views);
function fmt(n){ if(n==null)return '—'; if(n>=1e6)return (n/1e6).toFixed(1)+'M'; if(n>=1e3)return (n/1e3).toFixed(1)+'K'; return ''+n; }

const children=[];
children.push(new Paragraph({heading:HeadingLevel.HEADING_1,children:[new TextRun('@timbiohacker — Top 30 Reels by Views')]}));
children.push(new Paragraph({spacing:{after:180},children:[new TextRun({text:`30 highest-viewed reels, transcribed. Stats from your report. Generated ${new Date().toISOString().slice(0,10)}.`,italics:true,color:'666666'})]}));

data.forEach((r,i)=>{
  children.push(new Paragraph({heading:HeadingLevel.HEADING_2,spacing:{before:160,after:40},children:[new TextRun(`#${i+1} · ${fmt(r.views)} views · ${fmt(r.likes)} likes · ${fmt(r.comments)} comments`)]}));
  children.push(new Paragraph({spacing:{after:60},children:[new TextRun({text:'Link: ',bold:true}),new ExternalHyperlink({children:[new TextRun({text:r.url,style:'Hyperlink'})],link:r.url})]}));
  children.push(new Paragraph({spacing:{after:40},children:[new TextRun({text:'Transcript',bold:true,size:20})]}));
  children.push(new Paragraph({spacing:{after:140},indent:{left:360},border:{left:{style:BorderStyle.SINGLE,size:18,color:'2E8B57',space:12}},children:[new TextRun({text:r.transcript||'(no speech)',color:'222222'})]}));
  children.push(new Paragraph({border:{bottom:{style:BorderStyle.SINGLE,size:4,color:'DDDDDD',space:8}},spacing:{after:120},children:[new TextRun('')]}));
});

const doc=new Document({creator:'Reel Transcriber',title:'timbiohacker Top 30',
  styles:{default:{document:{run:{font:'Arial',size:22}}},paragraphStyles:[
    {id:'Heading1',name:'Heading 1',basedOn:'Normal',next:'Normal',quickFormat:true,run:{size:32,bold:true,font:'Arial',color:'111111'},paragraph:{spacing:{before:200,after:120},outlineLevel:0}},
    {id:'Heading2',name:'Heading 2',basedOn:'Normal',next:'Normal',quickFormat:true,run:{size:20,bold:true,font:'Arial',color:'2E8B57'},paragraph:{spacing:{before:160,after:40},outlineLevel:1}}]},
  sections:[{properties:{page:{size:{width:12240,height:15840},margin:{top:1440,right:1440,bottom:1440,left:1440}}},children}]});
Packer.toBuffer(doc).then(buf=>{const out='/Users/shekhar/Claude Code/reel-analysis/Tim_Biohacker_Top30.docx';fs.writeFileSync(out,buf);console.log('✓ docx:',out,'(',(buf.length/1024).toFixed(0),'KB )');});

let md=`# @timbiohacker — Top 30 Reels by Views\n\n`;
data.forEach((r,i)=>{md+=`## #${i+1} · ${fmt(r.views)} views · ${fmt(r.likes)} likes\n${r.url}\n\n> ${(r.transcript||'(no speech)').replace(/\n/g,'\n> ')}\n\n---\n\n`;});
fs.writeFileSync('/Users/shekhar/Claude Code/reel-analysis/Tim_Biohacker_Top30.md',md);
console.log('✓ markdown too');
