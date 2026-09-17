const card=document.querySelector(".setup-card");
const input=document.querySelector("#api-key");
const save=document.querySelector("#save");
const status=document.querySelector("#status");
const csrf=card.dataset.csrf;

async function post(body){
  const response=await fetch("/api/save",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({csrfToken:csrf,...body})});
  return response.ok;
}

function setStatus(message,state){status.textContent=message;status.dataset.state=state;}

async function saveKey(){
  const apiKey=input.value.trim();
  if(!apiKey){setStatus("请先填写 API Key。","error");input.focus();return;}
  save.disabled=true;
  try{
    const ok=await post({apiKey});
    input.value="";
    setStatus(ok?"保存成功，现在可以回到 Codex 使用 Stitch。":"保存失败，请检查 Key 后重试。",ok?"success":"error");
  }catch{
    input.value="";
    setStatus("保存失败，请确认本地设置页仍在运行。","error");
  }finally{save.disabled=false;}
}

save.addEventListener("click",saveKey);
input.addEventListener("keydown",event=>{if(event.key==="Enter")saveKey();});
