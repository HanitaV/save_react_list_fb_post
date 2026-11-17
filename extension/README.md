# Facebook Engagement Inspector — one-click MV3 extension

A standalone Chrome/Edge **user-initiated** inspection workflow, based on the request to combine reaction-list inspection and profile-wall review into a **single button**. No external browser or Python service is required.

## How to install and use

1. Open `chrome://extensions` or `edge://extensions`, enable Developer mode, choose **Load unpacked** and select `extension/`.
2. Sign in to Facebook normally and open a specific **post URL**, such as `https://www.facebook.com/example/posts/123` or a group post you can already access.
3. Click the extension icon and select **Quét reaction + kiểm tra wall**.
4. The extension tries to open the reaction dialog, reads up to **20 visible reactor profiles**, and opens one **inactive tab** at a time in the **same browser** to inspect the wall already available to your current session.
5. Reopen the popup to view progress; export a JSON snapshot when done.

You do **not** need to separately press an Inspect button on each profile. The scanner makes a bounded attempt and reports unknown/unavailable observations rather than inventing results.

## Architecture

- `reaction-collector.js` runs in the current post tab after the explicit click. It opens the reaction dialog when recognizable, reads profile links, scrolls its list at most five times, and stops at 20 unique accounts.
- `background.js` owns the one-click workflow. It opens and closes one background tab at a time and stores progress in `chrome.storage.local`. The process uses Chrome tabs, **not** CloakBrowser or a second independent browser instance.
- `inspector.js` checks accessible profile DOM, avatar accessibility labels and up to five already loaded timeline articles.
- `popup.js` renders progress, findings and JSON export. No remote API calls or cookies copied out of the browser.
- No backend integration is required. The export schema differs from the backend's reaction-import schema; it is **not** automatically sent to the backend.

## Limitations and consent

- The extension asks for Facebook host permissions to inspect inactive profile tabs. This is broader than `activeTab` alone and must be reviewed before installation.
- It is **not** a complete Facebook reaction-list crawler; it reads at most 20 profiles and has a bounded scroll. Reactions may be omitted when not loaded.
- Facebook frequently changes its DOM and accessibility labels. Automatic dialog opening, links, avatar recognition, and post classification are best effort. If the interface doesn't match, the scan reports an error instead of producing guesses.
- `NO_VISIBLE_POSTS` means no posts found in the **currently loaded accessible DOM**, not proof that a wall is empty. `SHARE_ONLY` is heuristic and low-confidence.
- Facebook may request login or show restrictions; those profiles are marked unavailable. No authentication, challenge, rate-limit or privacy-control bypass is attempted.
- Chrome MV3 background workers may be suspended. A one-minute alarm marks a stalled profile unavailable and advances to the next profile; stored progress remains visible. For reliable large-scale queues a different architecture would be needed.
- Store/export personal data only with authorization and comply with applicable platform policies. This extension does **not** like, share, comment, log into multiple accounts, or create fake engagement.

## Run tests

```sh
cd extension
npm test
```

Node's built-in test runner is used; no external package installation necessary.
