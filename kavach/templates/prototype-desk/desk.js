const $ = s => document.querySelector(s);
const bills = [
  {id:"B-101",name:"Northline Freight",rs:48000,end:"1234",status:"Ready"},
  {id:"B-102",name:"Delta Packaging",rs:12500,end:"4421",status:"Ready"},
  {id:"B-103",name:"Cedar Print",rs:9200,end:"5107",status:"Not approved"},
  {id:"B-104",name:"Harbour Repairs",rs:8400,end:"7206",status:"Possible duplicate"}
];
const names = {A:"Batch brief", B:"Exception inbox", C:"Bill register"};
let view = new URLSearchParams(location.search).get("variant") || "A";
if (!Object.hasOwn(names,view)) view="A";
let source="", syncs=0, file=null, statement=false;
const rows = () => bills.filter(b=>b.status!=="Not approved");
const ready = () => rows().filter(b=>b.status==="Ready");
const held = () => rows().filter(b=>["Possible duplicate","Account change"].includes(b.status));
const money = n => "₹"+n.toLocaleString("en-IN");
const total = a => money(a.reduce((n,b)=>n+b.rs,0));
const button = (action,label,primary=false) => `<button data-action="${action}" class="${primary?'primary':''}">${label}</button>`;
const tag = b => `<span class="pill ${held().includes(b)?'warn':''}">${b.status}</span>`;
const note = text => $("#notice").textContent=text;
const dialog = (title,html) => {
  $("#sheet").innerHTML=`<small>PAYMENT DESK / DEMO</small><h2>${title}</h2>${html}`;
  if (!$("dialog").open) $("dialog").showModal();
};
function explain(b){
  if(b.status==="Account change") return "The new instruction requests account ending 9876. Your separately approved beneficiary still ends in 4421. AP must call the trusted contact; a different authorizer must approve any change. This bill stays out.";
  if(b.status==="Possible duplicate") return "A previous payment to Harbour Repairs was also ₹8,400. AP must compare the invoice references. A similar amount is a reason to check, not proof of a duplicate.";
  if(b.status==="Ready") return `The bill is approved, the requested account matches the trusted account ending ${b.end}, and no matching prior payment was found.`;
  if(b.status==="Cleared") return `One demo statement debit matches KV${b.id.replace("-","")}, the signed amount and INR.`;
  return "Included in the signed demo file. No matching debit has been confirmed.";
}
function list(items){
  return items.map(b=>`<div class="row"><b>${b.name}<small>${b.id}</small></b><span class="amt">${money(b.rs)}</span><span>${tag(b)}</span>${button("bill:"+b.id,"Inspect")}</div>`).join("");
}
function inbox(){return `<aside class="inbox"><small class="warn">NEEDS A PERSON</small><h2>${held().length} on hold</h2>${held().map(b=>`<div class="item"><b>${b.name}</b><p>${b.status} · ${money(b.rs)}</p>${button("bill:"+b.id,"See why")}</div>`).join("")}</aside>`}
function batch(){return `<section class="card hero"><small>${file?"SIGNED BATCH / DEMO-01":"AVAILABLE TO SIGN"}</small><h2>${total(file||ready())}</h2><p>${file?`${file.length} bills signed · ${rows().filter(b=>b.status==="Cleared").length} cleared per statement`:`${ready().length} approved bills can proceed without waiting for the holds.`}</p>${file?button("file","Inspect signed file",true):button("review","Review clean batch",true)} ${file&&!statement?button("statement","Match demo statement"):''}</section>`}
function render(){
  const titles={A:"Your payment brief.",B:"Work the exceptions.",C:"Supplier bill register."};
  const subtitles={A:"See what can be paid now. Leave only the exceptions for a person.",B:"One question per held bill. The clean batch can move independently.",C:"Trace each source bill from approval to a bank-confirmed debit."};
  const tools=`<div class="tools"><b>${source||"Sample snapshot"}</b><span class="stamp">${source?(syncs?"SYNC "+syncs:"READY TO SYNC"):"NOT CONNECTED"}</span>${!file?button("sources",source?"Source details":"Choose source")+ (source?button("sync","Sync approved bills",true):""):"<small>SNAPSHOT FROZEN</small>"}</div>`;
  const register=`<section class="ledger">${list(rows())}</section>`;
  $("#workspace").innerHTML=`<h1>${titles[view]}</h1><p class="lead">${subtitles[view]}</p>${tools}`+
    (view==="A"?`<div class="grid">${batch()}${inbox()}</div>${register}`:view==="B"?`<div class="grid">${inbox()}<div>${batch()}</div></div>`:`${register}<div class="actions">${file?button("file","Inspect signed file"):button("review","Review "+ready().length+" ready bills",true)} ${file&&!statement?button("statement","Match demo statement"):""}</div>`);
  $("#variant").textContent=`${view} / ${names[view]}`;
}
function move(n){const keys=Object.keys(names);view=keys[(keys.indexOf(view)+n+3)%3];const u=new URL(location.href);u.searchParams.set("variant",view);history.replaceState(null,"",u);render()}
function act(a){
  if(a==="sources") return dialog(source||"Where are bills approved?",source?`<p>Read-only demo source. Sync imports approved bills by bill ID; it never edits the source or replaces trusted beneficiary records.</p>`:`<p>Choose the source your team already uses. These are simulated connections, not live integrations.</p>${["Accounting system","Shared sheet","Scheduled ERP export","Sample CSV fallback"].map((s,i)=>button("connect:"+i,s)).join("")}`);
  if(a.startsWith("connect:")){source=["Accounting system","Shared sheet","Scheduled ERP export","Sample CSV fallback"][+a.split(":")[1]];note("Demo source selected. Sync once for the baseline, then again to simulate a changed destination and a newly approved bill.")}
  if(a==="sync"&&!file){syncs++;if(syncs===2){bills[1].status="Account change";bills[2].status="Ready"}note(syncs===1?"3 approved bills matched by ID. Nothing duplicated. B-103 is still awaiting source approval.":syncs===2?"B-103 newly approved. B-102 now requests a different account and is held. B-101 was not duplicated.":"No source changes. No duplicate bills or payment instructions.")}
  if(a.startsWith("bill:")){const b=bills.find(x=>x.id===a.slice(5));return dialog(b.name,`<p>${b.id} · ${money(b.rs)} · ${tag(b)}</p><p>${explain(b)}</p>`)}
  if(a==="review"&&!file)return dialog("Review exact batch",`<p>Only these bills enter the file. Signing is not proof of payment.</p>${ready().map(b=>`<p><b>${b.id} · ${b.name}</b><br>${money(b.rs)} INR · destination ending ${b.end}</p>`).join("")}${button("sign","Sign demo batch · "+total(ready()),true)}`);
  if(a==="sign"&&!file){file=ready().map(b=>({...b}));ready().forEach(b=>b.status="In file");note("Demo batch frozen. Held bills were excluded. No money moved. Match the sample statement next.")}
  if(a==="file"&&file)return dialog("Frozen demo file",`<p>DEMO-01 · ${file.length} items · ${total(file)}. Masked preview only; not for bank upload.</p>${file.map(b=>`<p><b>${b.name}</b> · ${money(b.rs)} · ending ${b.end}<br><small>KV${b.id.replace("-","")}</small></p>`).join("")}`);
  if(a==="statement"&&file&&!statement){statement=true;bills[0].status="Cleared";note("Matched one demo debit: KVB101 · ₹48,000 INR. The other signed bill is still waiting for bank evidence. No second payment was created.")}
  $("dialog").close();render();
}
document.addEventListener("click",e=>{const b=e.target.closest("button");if(!b)return;if(b.dataset.move)move(+b.dataset.move);else if(b.dataset.action)act(b.dataset.action);else if(b.id==="close")$("dialog").close()});
document.addEventListener("keydown",e=>{if($("dialog").open||e.target.closest("input,textarea,select,[contenteditable]"))return;if(["ArrowLeft","ArrowRight"].includes(e.key)){e.preventDefault();move(e.key==="ArrowRight"?1:-1)}});
render();
