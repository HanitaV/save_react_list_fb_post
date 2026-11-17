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
    const raw = (anchor.innerText || anchor.getAttribute("aria-label") || "").replace(/\s+/g, " ").trim();
    if (!raw || raw.length > 90 || /^(?:all|like|love|care|wow|haha|sad|angry|thích|yêu thích|tất cả|theo dõi|follow|add friend|kết bạn|message|nhắn tin|xem thêm|see more|profile|trang cá nhân)$/i.test(raw)) return null;
    return raw;
  };
  const reactionDialogs = () => Array.from(document.querySelectorAll('[role="dialog"], [aria-modal="true"]'))
    .filter(isVisible)
    .filter(el => {
      const label = [(el.getAttribute("aria-label") || ""), (el.innerText || "").slice(0,350)].join(" ");
      return /(?:reactions?|bày tỏ cảm xúc|tất cả|\ball\b)/i.test(label);
    });
  const reactionCandidates = () => Array.from(document.querySelectorAll('button, a, [role="button"]'))
    .filter(isVisible)
    .filter(el => {
      const href = el.getAttribute("href") || "";
      // Never click plain Like/React controls: doing so could itself add engagement.
      if (/\/ufi\/reaction\/profile\/browser\//i.test(href)) return true;
      const label = [el.getAttribute("aria-label"), el.getAttribute("title")].filter(Boolean).join(" ");
      const hasCount = /\d/.test(label);
      return hasCount && /(?:reactions?|people reacted|người.*bày tỏ cảm xúc)/i.test(label);
    });
  const extract = (root, found) => {
    for (const a of root.querySelectorAll("a[href]")) {
      if (found.size >= MAX) return;
      if (!isVisible(a)) continue;
      const url = profileUrl(a.getAttribute("href"));
      const name = nameFor(a);
      if (url && name && !found.has(url)) found.set(url, {profile_url:url, display_name:name});
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
    if (!dialog) throw new Error("Không mở được danh sách reaction. Không có dữ liệu nào được ghi nhận.");
    const found = new Map();
    extract(dialog, found);
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
      throw new Error("Danh sách reaction đã mở nhưng chưa tìm được liên kết hồ sơ hợp lệ. Không giả định danh sách trống.");
    }
    return {post_url:location.href, collected_at:new Date().toISOString(),
      reactors:Array.from(found.values()), truncated:found.size===MAX,
      warnings:["Danh sách phản ánh các tài khoản đọc được trong cửa sổ reaction, không đảm bảo đầy đủ.",
        "Không thu thập dữ liệu ngoài phạm vi người dùng đang có quyền xem."]};
  }
  window.__FBReactionCollector = {collect, profileUrl, postUrl, nameFor};
})();
