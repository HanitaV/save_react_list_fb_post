"use strict";
const $ = id => document.getElementById(id);
const KEY="postAudit";
const WALL={HAS_VISIBLE_POSTS:"Có bài hiển thị",NO_VISIBLE_POSTS:"Không thấy bài",RESTRICTED:"Bị giới hạn",UNKNOWN:"Không xác định"};
const AVATAR={DEFAULT:"Avatar mặc định",PRESENT_UNVERIFIED:"Có avatar (chưa xác minh)",CUSTOM:"Avatar riêng",UNKNOWN:"Chưa rõ"};
function show(state) {
  $("result").hidden=!state;
  $("start").disabled=state?.status==="RUNNING";
  if(!state){$("message").textContent="Sẵn sàng kiểm tra một bài đăng.";$("message").classList.remove("error");return;}
  $("message").textContent=state.message || state.status;
  $("message").classList.toggle("error",state.status==="ERROR");
  const total=state.reactors?.length||0, processed=state.profiles?.length||0;
  $("total").textContent=String(total);$("progress").textContent=String(processed)+"/"+total;
  $("progressBar").style.width=(total?Math.round(processed/total*100):0)+"%";
  $("profiles").replaceChildren();
  for(const profile of state.profiles||[]) {
    const li=document.createElement("li");
    const title=document.createElement("strong");title.textContent=profile.display_name||profile.reaction_display_name||"Unknown";li.append(title);
    const sub=document.createElement("small");
    sub.textContent=(AVATAR[profile.avatar?.status]||"Chưa rõ")+" · "+(WALL[profile.wall_status]||"Chưa rõ")+
      " · "+(profile.posts?.length||0)+" bài";li.append(sub);
    const shareCount=(profile.posts||[]).filter(p=>p.classification==="SHARE_ONLY").length;
    if(shareCount){const summary=document.createElement("p");summary.textContent=shareCount+" bài được nhận diện là chia sẻ thuần túy (ước lượng).";li.append(summary);}
    if(profile.error){const p=document.createElement("p");p.textContent=profile.error;li.append(p);}
    if(/^https:\/\/(?:www\.|m\.)?facebook\.com\//.test(profile.profile_url||"")){
      const a=document.createElement("a");a.href=profile.profile_url;a.textContent="Mở hồ sơ";a.target="_blank";a.rel="noopener noreferrer";li.append(a);
    }
    $("profiles").append(li);
  }
}
async function refresh(){const data=await chrome.storage.local.get(KEY);show(data[KEY]||null);}
$("start").addEventListener("click",async()=>{
  $("start").disabled=true;
  $("message").textContent="Đang bắt đầu quét...";
  try{
    const [tab]=await chrome.tabs.query({active:true,currentWindow:true});
    if(!tab?.id)throw new Error("Không tìm thấy tab đang mở.");
    const result=await chrome.runtime.sendMessage({type:"START_POST_AUDIT",tabId:tab.id});
    if(!result?.ok)throw new Error(result?.error||"Không thể bắt đầu.");
    await refresh();
  }catch(e){$("message").textContent=e?.message||String(e);$("message").classList.add("error");}
  finally{const {postAudit}=await chrome.storage.local.get(KEY);$("start").disabled=postAudit?.status==="RUNNING";}
});
$("export").addEventListener("click",async()=>{
  const {postAudit}=await chrome.storage.local.get(KEY);
  if(!postAudit)return;
  const data={...postAudit,reactors:undefined};
  const blob=new Blob([JSON.stringify(data,null,2)],{type:"application/json"});
  const url=URL.createObjectURL(blob),a=document.createElement("a");
  a.href=url;a.download="facebook-post-audit-"+new Date().toISOString().slice(0,10)+".json";a.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
});
$("clear").addEventListener("click",async()=>{
  const {postAudit}=await chrome.storage.local.get(KEY);
  if(postAudit?.status==="RUNNING"){
    $("message").textContent="Không thể xóa dữ liệu khi đang quét.";return;
  }
  await chrome.storage.local.remove(KEY);show(null);
});
chrome.storage.onChanged.addListener((changes,area)=>{
  if(area==="local" && changes[KEY])show(changes[KEY].newValue||null);
});
refresh().then(()=>chrome.runtime.sendMessage({type:"CHECK_POST_AUDIT"}).catch(()=>{})).catch(()=>{});
