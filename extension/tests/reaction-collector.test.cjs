const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");
const source=fs.readFileSync(path.join(__dirname,"../reaction-collector.js"),"utf8");
const env={window:{},URL,location:{origin:"https://www.facebook.com",href:"https://www.facebook.com/a/posts/11"},document:{},setTimeout};
vm.runInNewContext(source,env);
const {postUrl,profileUrl,nameFor}=env.window.__FBReactionCollector;
test("post URL validation",()=>{
  assert.equal(postUrl("https://www.facebook.com/a/posts/123"),true);
  assert.equal(postUrl("https://www.facebook.com/groups/123/posts/5"),true);
  assert.equal(postUrl("https://www.facebook.com/story.php?story_fbid=123&id=7"),true);
  assert.equal(postUrl("https://www.facebook.com/a"),false);
  assert.equal(postUrl("https://evil.example.com/a/posts/1"),false);
});
test("profile URL normalization",()=>{
  assert.equal(profileUrl("/groups/123/user/456"),"https://www.facebook.com/profile.php?id=456");
  assert.equal(profileUrl("/people/Example/456"),"https://www.facebook.com/profile.php?id=456");
  assert.equal(profileUrl("https://www.facebook.com/profile.php?id=789"),"https://www.facebook.com/profile.php?id=789");
  assert.equal(profileUrl("/example.user"),"https://www.facebook.com/example.user");
  assert.equal(profileUrl("https://evil.example.com/fake"),null);
  assert.equal(profileUrl("/groups"),null);
});
test("reject reaction filters as names",()=>{
  assert.equal(nameFor({innerText:"Like",getAttribute:()=>null}),null);
  assert.equal(nameFor({innerText:"Example Person",getAttribute:()=>null}),"Example Person");
});
