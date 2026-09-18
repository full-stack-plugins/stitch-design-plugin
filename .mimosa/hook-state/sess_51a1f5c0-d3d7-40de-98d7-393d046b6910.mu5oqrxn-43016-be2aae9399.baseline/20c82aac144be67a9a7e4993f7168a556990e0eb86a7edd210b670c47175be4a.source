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

const gcloudLogin=document.querySelector("#gcloud-login");
const gcloudVerify=document.querySelector("#gcloud-verify");

async function postPath(path){
  const response=await fetch(path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({csrfToken:csrf})});
  if(!response.ok)return null;
  try{return await response.json();}catch{return {};}
}

async function launchGcloud(){
  gcloudLogin.disabled=true;
  gcloudVerify.disabled=true;
  setStatus("正在检查 gcloud 环境并启动授权…","");
  try{
    const data=await postPath("/api/glaunch");
    if(data&&data.ok){
      setStatus("授权窗口已启动：请在浏览器完成 Google 登录，本页将自动检测授权结果（也可手动点击“完成授权后验证”）。","success");
      pollGverify(12);
    }else if(data&&data.reason==="gcloud-missing"){
      setStatus("本机未安装 gcloud（Google Cloud SDK）。可运行 brew install --cask google-cloud-sdk 安装后重试，或直接使用下方粘贴 Token 方式（立即可用）。","error");
    }else{
      setStatus("授权启动失败，可改用下方粘贴 Token 方式。","error");
    }
  }catch{
    setStatus("授权启动失败，请确认本地设置页仍在运行。","error");
  }finally{gcloudLogin.disabled=false;}
}

let polling=null;
function markAuthorized(){
  gcloudLogin.disabled=true;
  gcloudLogin.textContent="已授权 ✓";
}
function pollGverify(remaining){
  if(polling)clearInterval(polling);
  polling=setInterval(async()=>{
    const done=await verifyGcloud(true);
    if(done||remaining<=0){
      clearInterval(polling);
      polling=null;
      gcloudVerify.disabled=false;
      if(done){
        markAuthorized();
      }else{
        setStatus("暂未检测到授权完成：若浏览器未弹出，请查看下方说明或改用粘贴 Token 方式；完成后可再次点击“完成授权后验证”。","error");
      }
    }
    remaining-=1;
  },3000);
}

async function verifyGcloud(silent){
  if(!silent)gcloudVerify.disabled=true;
  if(!silent)setStatus("正在验证 Google 授权状态…","");
  try{
    const data=await postPath("/api/gverify");
    if(data&&data.ok){
      markAuthorized();
      setStatus(data.quotaProjectSet?"验证成功：Google 授权可用，回到 Codex 即可使用 Stitch。":"验证成功：Google 授权可用；建议设置 GOOGLE_CLOUD_PROJECT 以便计费配额。","success");
      return true;
    }
    if(!silent){
      setStatus(data&&data.gcloudFound===false
        ?"本机未安装 gcloud（Google Cloud SDK）。请安装后重试，或改用粘贴 Token 方式。"
        :"尚未检测到有效授权：请在浏览器完成 Google 登录后重试，或改用粘贴 Token 方式。","error");
    }
    return false;
  }catch{
    if(!silent)setStatus("验证失败，请确认本地设置页仍在运行。","error");
    return false;
  }finally{
    if(!silent)gcloudVerify.disabled=false;
  }
}

gcloudLogin.addEventListener("click",launchGcloud);
gcloudVerify.addEventListener("click",()=>verifyGcloud(false));

// 页面加载即检测授权状态：已授权则锁定按钮，避免"点了没反应"的困惑
(async function detectAuthOnLoad(){
  try{
    const data=await postPath("/api/gverify");
    if(data&&data.ok){
      markAuthorized();
      setStatus(data.quotaProjectSet?"Google 授权已就绪：回到 Codex 即可使用 Stitch，无需再次授权。":"Google 授权已就绪；建议设置 GOOGLE_CLOUD_PROJECT 以便计费配额。","success");
    }
  }catch{/* 首次使用时静默保持初始状态 */}
})();
