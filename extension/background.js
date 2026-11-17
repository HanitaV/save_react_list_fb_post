/* Event-driven one-click audit. Opens at most one inactive profile tab at a time. */
"use strict";
const MAX_ACTORS = 20;
const KEY = "postAudit";
const FACEBOOK = /^https:\/\/(?:www\.|m\.)?facebook\.com\//i;
const now = () => new Date().toISOString();
let inFlight = false;

async function read() { const item = await chrome.storage.local.get(KEY); return item[KEY] || null; }
async function write(state) { await chrome.storage.local.set({[KEY]:state}); }
async function finish(status,message) {
  const state = await read();
  if (!state || state.status !== "RUNNING") return;
  await chrome.alarms.clear("profile-timeout").catch(()=>{});
  await write({...state,status,message,phase:"DONE",updated_at:now(),completed_at:now(),worker_tab_id:null});
}
async function runStart(sourceTabId) {
  const previous = await read();
  if (previous?.status === "RUNNING") throw new Error("Một lượt quét đang chạy. Xem tiến độ trong popup.");
  const tab = await chrome.tabs.get(sourceTabId);
  if (!tab?.url || !FACEBOOK.test(tab.url)) throw new Error("Mở bài đăng facebook.com trong tab hiện tại.");
  const initial = {
    schema_version:1,post_url:tab.url,started_at:now(),updated_at:now(),
    status:"RUNNING",phase:"COLLECTING",message:"Đang đọc danh sách reaction",
    reactors:[],profiles:[],index:0,worker_tab_id:null,warnings:[]
  };
  await write(initial);
  try {
    await chrome.scripting.executeScript({target:{tabId:sourceTabId},files:["reaction-collector.js"]});
    const collected = await chrome.scripting.executeScript({
      target:{tabId:sourceTabId},
      func:async()=>window.__FBReactionCollector.collect()
    });
    const data = collected?.[0]?.result;
    if (!data?.reactors?.length) throw new Error("Không tìm thấy tài khoản reaction.");
    const reactors = data.reactors.slice(0,MAX_ACTORS);
    await write({...initial,reactors,post_url:data.post_url,collected_at:data.collected_at,
      warnings:data.warnings || [],truncated:data.truncated || false,
      phase:"OPENING",message:"Đã tìm thấy "+reactors.length+" tài khoản. Đang kiểm tra wall.",updated_at:now()});
    await openNext();
  } catch (error) {
    await finish("ERROR",error?.message || String(error));
  }
}
async function openNext() {
  if (inFlight) return;
  inFlight = true;
  try {
    const state = await read();
    if (!state || state.status !== "RUNNING") return;
    if (state.index >= state.reactors.length) {
      await finish("COMPLETE","Đã hoàn tất "+state.profiles.length+" hồ sơ.");
      return;
    }
    if (state.worker_tab_id) return;
    const actor = state.reactors[state.index];
    // The profile URLs were validated by the content script; validate again at trust boundary.
    if (!FACEBOOK.test(actor.profile_url)) {
      await write({...state,index:state.index+1,
        profiles:[...state.profiles,{profile_url:actor.profile_url,display_name:actor.display_name,status:"ERROR",error:"Invalid profile URL"}]});
      inFlight=false;await openNext();return;
    }
    const tab = await chrome.tabs.create({url:actor.profile_url,active:false});
    const updated = {...state,worker_tab_id:tab.id,phase:"WAITING",
      message:"Đang kiểm tra "+(state.index+1)+"/"+state.reactors.length+": "+actor.display_name,
      updated_at:now()};
    await write(updated);
    await chrome.alarms.create("profile-timeout", {delayInMinutes:1});
    const currentTab = await chrome.tabs.get(tab.id).catch(()=>null);
    if (currentTab?.status==="complete") {
      // Schedule through the same event handler used by tab completion.
      queueMicrotask(()=>inspectWorker(tab.id).catch(()=>{}));
    }
  } catch (error) {
    await finish("ERROR","Không thể mở tab kiểm tra: "+(error?.message||String(error)));
  } finally { inFlight=false; }
}
async function inspectWorker(tabId) {
  const state=await read();
  if (!state || state.status!=="RUNNING" || state.worker_tab_id!==tabId || state.phase!=="WAITING") return;
  const actor=state.reactors[state.index];
  await write({...state,phase:"INSPECTING",updated_at:now()});
  let result;
  try {
    const tab=await chrome.tabs.get(tabId);
    if (!tab.url || !FACEBOOK.test(tab.url)) throw new Error("Hồ sơ chuyển hướng ngoài Facebook.");
    if (/\/login|\/checkpoint|\/recover/i.test(new URL(tab.url).pathname)) throw new Error("Facebook yêu cầu đăng nhập hoặc xác minh.");
    await chrome.scripting.executeScript({target:{tabId},files:["inspector.js"]});
    const injected=await chrome.scripting.executeScript({target:{tabId},func:async()=>{
      // Allow a few seconds for Facebook's client-side profile header to hydrate.
      const started=Date.now();
      while(!document.querySelector('[role="main"] h1, main h1') && Date.now()-started<4000){
        await new Promise(resolve=>setTimeout(resolve,200));
      }
      return window.__FBProfileInspector.inspect();
    }});
    if (!injected?.[0]?.result) throw new Error("Không đọc được wall trong trang hiện tại.");
    result={...injected[0].result,reaction_display_name:actor.display_name,status:"INSPECTED"};
  } catch(error) {
    result={profile_url:actor.profile_url,display_name:actor.display_name,status:"UNAVAILABLE",
      inspected_at:now(),avatar:{status:"UNKNOWN"},wall_status:"UNKNOWN",posts:[],
      error:error?.message||String(error)};
  } finally {
    await chrome.alarms.clear("profile-timeout").catch(()=>{});
    await chrome.tabs.remove(tabId).catch(()=>{});
  }
  const latest=await read();
  if (!latest || latest.status!=="RUNNING" || latest.worker_tab_id!==tabId) return;
  await write({...latest,index:latest.index+1,worker_tab_id:null,phase:"OPENING",
    profiles:[...latest.profiles,result],updated_at:now()});
  await openNext();
}
chrome.tabs.onUpdated.addListener((tabId,changeInfo)=>{
  if (changeInfo.status!=="complete") return;
  inspectWorker(tabId).catch(async error=>{await finish("ERROR",error?.message||String(error));});
});
chrome.tabs.onRemoved.addListener(async tabId=>{
  const state=await read();
  if (state?.status==="RUNNING" && state.worker_tab_id===tabId && state.phase==="WAITING") {
    await chrome.alarms.clear("profile-timeout").catch(()=>{});
    const actor=state.reactors[state.index];
    await write({...state,index:state.index+1,worker_tab_id:null,phase:"OPENING",
      profiles:[...state.profiles,{profile_url:actor.profile_url,display_name:actor.display_name,status:"UNAVAILABLE",
        wall_status:"UNKNOWN",avatar:{status:"UNKNOWN"},posts:[],error:"Tab kiểm tra đã đóng"}]});
    await openNext();
  }
});
chrome.alarms.onAlarm.addListener(async alarm=>{
  if(alarm.name!=="profile-timeout") return;
  const state=await read();
  if(state?.status!=="RUNNING" || !state.worker_tab_id ||
      !["WAITING","INSPECTING"].includes(state.phase)) return;
  const tabId=state.worker_tab_id;
  const actor=state.reactors[state.index];
  // Persist the timeout before closing the tab to prevent duplicate onRemoved handling.
  await write({...state,index:state.index+1,worker_tab_id:null,phase:"OPENING",
    profiles:[...state.profiles,{profile_url:actor.profile_url,display_name:actor.display_name,
      status:"UNAVAILABLE",wall_status:"UNKNOWN",avatar:{status:"UNKNOWN"},posts:[],
      error:"Hết thời gian tải/kiểm tra hồ sơ (60 giây)."}],updated_at:now()});
  await chrome.tabs.remove(tabId).catch(()=>{});
  await openNext();
});
chrome.runtime.onMessage.addListener((msg,_sender,respond)=>{
  if (msg?.type==="START_POST_AUDIT") {
    read().then(state=>{
      if(state?.status==="RUNNING") throw new Error("Đã có lượt quét đang chạy.");
      // Respond immediately: the popup can close while progress persists in local storage.
      respond({ok:true});
      runStart(msg.tabId).catch(async error=>{await finish("ERROR",error?.message||String(error));});
    }).catch(error=>respond({ok:false,error:error?.message||String(error)}));
    return true;
  }
  if (msg?.type==="CHECK_POST_AUDIT") {
    read().then(async state=>{
      // Attempt to resume a tab that has already completed loading after a worker restart.
      if(state?.status==="RUNNING" && state.worker_tab_id && state.phase==="WAITING"){
        const tab=await chrome.tabs.get(state.worker_tab_id).catch(()=>null);
        if(tab?.status==="complete") inspectWorker(tab.id).catch(()=>{});
      }
      respond({ok:true});
    }).catch(()=>respond({ok:false}));
    return true;
  }
});
