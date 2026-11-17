/* Intentionally bounded, user-initiated collection of visible reaction-list entries. */
(() => {
  "use strict";
  const ALLOWED = new Set(["facebook.com", "www.facebook.com", "m.facebook.com"]);
  const MAX = 20;
  const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
  const isVisible = el => {
    if (!el || el.closest('[aria-hidden="true"]')) return false;
    const s = getComputedStyle(el);
    return s.display !== "none" && s.visibility !== "hidden";
  };
  const postUrl = raw => {
    try {
      const u = new URL(raw);
      const p = u.pathname.toLowerCase();
      const isPost = /\/(?:posts|permalink|videos|photos|reel)\//.test(p) ||
        /^\/(?:permalink\.php|story\.php|photo\.php|watch\/?)$/.test(p) ||
        (p === "/profile.php" && u.searchParams.has("story_fbid"));
      return u.protocol === "https:" && ALLOWED.has(u.hostname) && isPost;
    } catch { return false; }
  };
  const profileUrl = raw => {
    try {
      const u = new URL(raw, location.origin);
      if (u.protocol !== "https:" || !ALLOWED.has(u.hostname)) return null;
      const path = u.pathname.toLowerCase().replace(/\/$/, "");
      let id;
      if (path === "/profile.php") {
        id = u.searchParams.get("id");
        return /^\d+$/.test(id || "") ? "https://www.facebook.com/profile.php?id=" + id : null;
      }
      const match = path.match(/^\/(?:groups\/[^/]+\/user|people\/[^/]+)\/(\d+)$/);
      if (match) return "https://www.facebook.com/profile.php?id=" + match[1];
      if (/^\/[a-z0-9._-]+$/i.test(path) &&
          !/^\/(?:posts|photo|photos|reel|watch|groups|pages|events|friends|share|marketplace|messages|settings|search|home|login|notifications|profile\.php)$/.test(path)) {
        return "https://www.facebook.com" + path;
      }
    } catch { /* invalid URL */ }
    return null;
  };
  const nameFor = anchor => {
    // Prefer the visible name link, not the avatar link's "Name liked" label.
    const displayed = (anchor.innerText || "").replace(/\s+/g, " ").trim();
    const ariaName = (anchor.getAttribute("aria-label") || "")
      .replace(/\s+(?:liked|loved|reacted|cared|laughed|was surprised|was sad|was angry)(?:, unseen story)?$/i, "")
      .trim();
    const raw = displayed || ariaName;
    if (!raw || raw.length > 90 || /^(?:all|like|love|care|wow|haha|sad|angry|thích|yêu thích|tất cả|theo dõi|follow|add friend|kết bạn|message|nhắn tin|xem thêm|see more|profile|trang cá nhân)$/i.test(raw)) return null;
    return raw;
  };
  const reactionDialogs = () => Array.from(document.querySelectorAll('[role="dialog"], [aria-modal="true"]'))
    .filter(isVisible)
    .filter(el => {
      const tabs = Array.from(el.querySelectorAll('[role="tab"]'));
      const reactionTab = tabs.some(tab => /(?:people who reacted|reacted with|bày tỏ cảm xúc)/i.test(tab.getAttribute("aria-label") || ""));
      const label = [(el.getAttribute("aria-label") || ""), (el.innerText || "").slice(0,350)].join(" ");
      return reactionTab || /(?:reactions?|bày tỏ cảm xúc|tất cả|\ball\b)/i.test(label);
    });
  // Count badges such as "Like: 532 people" and "Love: 435 people" are clickable
  // reaction-list openers in Facebook's 2026 English interface. A bare "Like"
  // button is NEVER clicked: that would add a reaction.
  const isReactionCountLabel = (label, href = "") => {
    if (/\/ufi\/reaction\/profile\/browser\//i.test(href)) return true;
    if (!/\d/.test(label)) return false;
    return /^(?:(?:like|love|care|haha|wow|sad|angry|thích|yêu thích|thương thương|phẫn nộ|buồn|ngạc nhiên)\s*:\s*[\d,. ]+\s*(?:people|người)|(?:reactions?|people reacted|người.*bày tỏ cảm xúc)\s*:?\s*[\d,. ]+)/i.test(label);
  };
  const reactionCandidates = () => Array.from(document.querySelectorAll('button, a, [role="button"]'))
    .filter(isVisible)
    .filter(el => isReactionCountLabel(
      [el.getAttribute("aria-label"), el.getAttribute("title")].filter(Boolean).join(" "),
      el.getAttribute("href") || ""
    ));
  const isAllTab = el => {
    const label = el.getAttribute("aria-label") || "";
    const ownText = (el.innerText || "").trim();
    return /reacted with All\b/i.test(label) ||
      /(?:^|\s)(?:tất cả|all)(?:\s|$)/i.test(ownText);
  };
  const extract = (root, found) => {
    for (const a of root.querySelectorAll("a[href]")) {
      if (found.size >= MAX) return;
      if (!isVisible(a)) continue;
      const url = profileUrl(a.getAttribute("href"));
      const name = nameFor(a);
      if (!url || !name) continue;
      const hasText = Boolean((a.innerText || "").trim());
      const existing = found.get(url);
      if (!existing || (hasText && !existing.has_visible_name)) {
        found.set(url, {profile_url:url, display_name:name, has_visible_name:hasText});
      }
    }
  };
  const scrollable = root => Array.from(root.querySelectorAll("*"))
    .filter(el => el.scrollHeight > el.clientHeight + 120 && el.clientHeight > 100)
    .sort((a,b) => b.clientHeight - a.clientHeight)[0] || null;
  async function collect() {
    if (!postUrl(location.href)) throw new Error("Mở URL bài đăng Facebook cụ thể (posts/permalink/story/reel/photo) trước khi quét.");
    let dialog = reactionDialogs().at(-1);
    if (!dialog) {
      const button = reactionCandidates()[0];
      if (!button) throw new Error("Không tìm thấy nút mở danh sách reaction. Facebook có thể thay đổi giao diện hoặc bài chưa tải xong.");
      button.click();
      for (let i = 0; i < 12; i++) {
        await wait(250);
        dialog = reactionDialogs().at(-1);
        if (dialog) break;
      }
    }
    if (!dialog) throw new Error("Không mở được danh sách reaction. Hãy mở thủ công danh sách cảm xúc rồi bấm quét lại.");
    // The sample Facebook DOM opens directly on the Like tab. Switch to All so
    // the result is not restricted to one emotion. This only changes a view.
    let allTab = Array.from(dialog.querySelectorAll('[role="tab"]')).find(isAllTab);
    if (allTab && allTab.getAttribute("aria-selected") !== "true") {
      allTab.click();
      for (let i = 0; i < 20; i++) {
        await wait(250);
        dialog = reactionDialogs().at(-1) || dialog;
        allTab = Array.from(dialog.querySelectorAll('[role="tab"]')).find(isAllTab);
        if (allTab?.getAttribute("aria-selected") === "true") break;
      }
      await wait(350);
    }
    const found = new Map();
    // Facebook loads dialog entries asynchronously; don't read an empty frame
    // immediately after clicking the count badge or selecting the All tab.
    for (let i = 0; i < 24 && found.size === 0; i++) {
      dialog = reactionDialogs().at(-1) || dialog;
      extract(dialog, found);
      if (!found.size) await wait(250);
    }
    const scroller = scrollable(dialog);
    if (scroller) {
      for (let i = 0; i < 5 && found.size < MAX; i++) {
        const before = scroller.scrollTop;
        scroller.scrollTop += Math.max(150, scroller.clientHeight * 0.8);
        scroller.dispatchEvent(new Event("scroll", {bubbles:true}));
        await wait(350);
        extract(dialog, found);
        if (scroller.scrollTop === before) break;
      }
    }
    if (found.size === 0) {
      const links = dialog.querySelectorAll("a[href]").length;
      throw new Error("Hộp thoại reaction đã mở nhưng chưa đọc được hồ sơ (" + links +
        " liên kết trong DOM). Thử mở tab All và tải lại bài. Không giả định danh sách trống.");
    }
    const reactors = Array.from(found.values()).map(({profile_url,display_name})=>({profile_url,display_name}));
    return {post_url:location.href, collected_at:new Date().toISOString(),
      reactors, truncated:found.size===MAX,
      warnings:["Danh sách phản ánh các tài khoản đọc được trong cửa sổ reaction, không đảm bảo đầy đủ.",
        "Không thu thập dữ liệu ngoài phạm vi người dùng đang có quyền xem."]};
  }
  window.__FBReactionCollector = {collect, profileUrl, postUrl, nameFor, isReactionCountLabel, isAllTab};
})();
