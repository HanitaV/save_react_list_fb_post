/* Loaded only after the user clicks Inspect. No network, scrolling, or background collection. */
(() => {
  "use strict";
  const ALLOWED_HOSTS = new Set(["facebook.com", "www.facebook.com", "m.facebook.com"]);
  const SHARE_MARKER = /(?:^|\n)[^\n]{0,100}(?:đã chia sẻ (?:một |bài |video |ảnh )?|shared (?:a |an |the |someone's )|đã chia sẻ lại)/i;
  const DEFAULT_AVATAR = /(?:default (?:profile (?:picture|photo)|avatar)|(?:ảnh|hình) đại diện mặc định|avatar mặc định)/i;
  const RESTRICTED = /(?:this content isn't available|this profile is locked|nội dung này hiện không hiển thị|trang cá nhân đã khóa|you must log in|đăng nhập để tiếp tục)/i;
  const POST_PATH = /\/(?:posts|permalink|videos|photos|photo|reel)\/|(?:\?|&)story_fbid=/i;

  function allowedProfile(raw) {
    try {
      const url = new URL(raw);
      if (url.protocol !== "https:" || !ALLOWED_HOSTS.has(url.hostname)) return false;
      const path = url.pathname.toLowerCase();
      if (path === "/" || path === "/profile.php") return path !== "/" && /^\d+$/.test(url.searchParams.get("id") || "");
      if (/^\/(?:groups|watch|reel|reels|stories|marketplace|events|gaming|messages|settings|notifications|friends|search|login|checkpoint|photo|photos|permalink|posts)(?:\/|$)/.test(path)) return false;
      return /^\/people\/[^/]+\/\d+\/?$/.test(path) || /^\/[a-z0-9._-]+\/?$/i.test(path);
    } catch { return false; }
  }

  function canonicalProfile(raw) {
    const url = new URL(raw);
    if (url.pathname.toLowerCase() === "/profile.php") {
      return "https://www.facebook.com/profile.php?id=" + encodeURIComponent(url.searchParams.get("id") || "");
    }
    return "https://www.facebook.com" + url.pathname.replace(/\/$/, "");
  }

  function text(el, max = 300) {
    return (el?.innerText || el?.textContent || "").replace(/\s+/g, " ").trim().slice(0, max);
  }

  function visible(el) {
    if (!el || el.closest('[aria-hidden="true"]')) return false;
    const style = getComputedStyle(el);
    return style.display !== "none" && style.visibility !== "hidden";
  }

  function avatarStatus() {
    const roots = [document.querySelector('[role="main"]'), document.querySelector("main"), document.body].filter(Boolean);
    const selectors = [
      'img[alt*="profile picture" i]', 'img[alt*="profile photo" i]',
      'img[alt*="ảnh đại diện" i]', 'img[alt*="hình đại diện" i]',
      '[aria-label*="profile picture" i] img', '[aria-label*="ảnh đại diện" i] img'
    ];
    for (const root of roots) {
      for (const selector of selectors) {
        const candidate = Array.from(root.querySelectorAll(selector)).find(visible);
        if (!candidate) continue;
        const description = [candidate.getAttribute("alt"), candidate.getAttribute("aria-label"), candidate.parentElement?.getAttribute("aria-label")].filter(Boolean).join(" ");
        if (DEFAULT_AVATAR.test(description)) return {status:"DEFAULT", evidence:"Nhãn truy cập mô tả ảnh đại diện mặc định.", confidence:"MEDIUM"};
        return {status:"PRESENT_UNVERIFIED", evidence:"Tìm thấy ảnh avatar nhưng chưa xác minh có phải ảnh mặc định hay không.", confidence:"LOW"};
      }
    }
    return {status:"UNKNOWN",evidence:"Không xác định được phần tử avatar của chủ hồ sơ.",confidence:"LOW"};
  }

  function classifyPostText(body, ownMessage) {
    const share = SHARE_MARKER.test(body);
    if (share && ownMessage && ownMessage.trim()) return {type:"SHARE_WITH_COMMENT",confidence:"MEDIUM"};
    if (share && ownMessage === "") return {type:"SHARE_ONLY",confidence:"LOW"};
    if (share) return {type:"UNKNOWN",confidence:"LOW"};
    return {type:"ORIGINAL_OR_OTHER",confidence:"LOW"};
  }

  function findPermalink(article) {
    const links = Array.from(article.querySelectorAll("a[href]"));
    for (const a of links) {
      try {
        const url = new URL(a.href);
        if (ALLOWED_HOSTS.has(url.hostname) && POST_PATH.test(url.pathname + url.search)) {
          url.hash = "";
          return url.toString();
        }
      } catch { /* malformed link */ }
    }
    return null;
  }

  function extractOwnMessage(article) {
    const own = article.querySelector('[data-ad-preview="message"], [data-testid="post_message"]');
    if (own && visible(own)) return text(own, 300);
    // Without an unambiguous author-message container, don't guess share-only.
    return null;
  }

  function extractDate(article) {
    const time = article.querySelector("time[datetime]");
    if (time) {
      const ms = Date.parse(time.getAttribute("datetime"));
      if (Number.isFinite(ms)) return new Date(ms).toISOString();
    }
    const epoch = article.querySelector("abbr[data-utime]")?.getAttribute("data-utime");
    if (epoch && /^\d+$/.test(epoch)) {
      const ms = Number(epoch) * 1000;
      if (Number.isFinite(ms)) return new Date(ms).toISOString();
    }
    return null;
  }

  function posts() {
    const root = document.querySelector('[role="main"]') || document.querySelector("main");
    if (!root) return [];
    const articles = Array.from(root.querySelectorAll('[role="article"]')).filter(el =>
      visible(el) && !el.parentElement?.closest('[role="article"]')
    );
    const seen = new Set();
    const rows = [];
    articles.forEach((article, order) => {
      const body = (article.innerText || "").slice(0, 3500);
      if (!body.trim()) return;
      const permalink = findPermalink(article);
      const key = permalink || body.slice(0, 220);
      if (seen.has(key)) return;
      seen.add(key);
      const cls = classifyPostText(body, extractOwnMessage(article));
      rows.push({
        url:permalink,
        published_at:extractDate(article),
        classification:cls.type,
        confidence:cls.confidence,
        snippet:body.replace(/\s+/g, " ").trim().slice(0, 180),
        pinned:/(?:^|\n)\s*(?:Pinned|Đã ghim)\s*(?:\n|$)/i.test(body.slice(0, 500)),
        order
      });
    });
    rows.sort((a,b) => {
      if (a.published_at && b.published_at) return b.published_at.localeCompare(a.published_at);
      if (a.published_at !== b.published_at) return a.published_at ? -1 : 1;
      if (a.pinned !== b.pinned) return a.pinned ? 1 : -1;
      return a.order - b.order;
    });
    return rows.slice(0,5).map(({order,...post})=>post);
  }

  function inspect() {
    if (!allowedProfile(location.href)) throw new Error("Hãy mở trang cá nhân Facebook (không phải News Feed, Group hoặc bài đăng).");
    const root = document.querySelector('[role="main"]') || document.querySelector("main") || document.body;
    const heading = root.querySelector("h1");
    const title = (document.title || "").replace(/\s*[|\-–]\s*Facebook\s*$/i,"").trim();
    const bodyIntro = text(root, 2500);
    if (RESTRICTED.test(bodyIntro)) {
      return {schema_version:1,profile_url:canonicalProfile(location.href),display_name:text(heading,120)||title||"Unknown",
        inspected_at:new Date().toISOString(),avatar:avatarStatus(),wall_status:"RESTRICTED",
        posts:[],limitations:["Facebook hạn chế nội dung; không cố vượt quyền truy cập."]};
    }
    const found = posts();
    return {
      schema_version:1,profile_url:canonicalProfile(location.href),
      display_name:text(heading,120)||title||"Unknown",
      inspected_at:new Date().toISOString(),
      avatar:avatarStatus(),
      wall_status:found.length ? "HAS_VISIBLE_POSTS" : "NO_VISIBLE_POSTS",
      posts:found,
      limitations:[
        "Chỉ các bài đã tải và hiển thị trong DOM khi người dùng nhấn kiểm tra.",
        "Không có bài quan sát được không có nghĩa là tài khoản chưa từng đăng.",
        "Phân loại nội dung là heuristic; cần kiểm tra thủ công."
      ]
    };
  }
  window.__FBProfileInspector = {inspect, classifyPostText, allowedProfile};
})();
