const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");
const source=fs.readFileSync(path.join(__dirname,"../inspector.js"),"utf8");
const sandbox={window:{}, URL, document:{}};
vm.runInNewContext(source,sandbox);
const {allowedProfile,classifyPostText}=sandbox.window.__FBProfileInspector;
test("only eligible Facebook profile paths and HTTPS",()=>{
  assert.equal(allowedProfile("https://www.facebook.com/profile.php?id=123"),true);
  assert.equal(allowedProfile("https://www.facebook.com/example.user"),true);
  assert.equal(allowedProfile("https://www.facebook.com/people/Example/123"),true);
  for (const bad of ["https://evil.test/example","http://www.facebook.com/test","https://www.facebook.com/groups/123","https://www.facebook.com/","https://www.facebook.com/profile.php?id=abc","https://www.facebook.com/posts/22"]) {
    assert.equal(allowedProfile(bad),false,bad);
  }
});
test("only confirmed share-only markers produce SHARE_ONLY",()=>{
  assert.equal(classifyPostText("User đã chia sẻ bài viết của Another User","").type,"SHARE_ONLY");
  assert.equal(classifyPostText("User shared a post","My thought").type,"SHARE_WITH_COMMENT");
  assert.equal(classifyPostText("User shared a post",null).type,"UNKNOWN");
  assert.equal(classifyPostText("Like\nComment\nShare",null).type,"ORIGINAL_OR_OTHER");
});
