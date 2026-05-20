// Dick Capital -> Discord: Gmail watcher (Apps Script).
// Runs every minute on nsabharwal2006@gmail.com. On a new
// email from Dick Capital, it pokes the GitHub bot, which
// reads the pick from the email and posts it to Discord.
// Setup steps are in the chat with Claude.

var OWNER = 'NeelSabharwal';
var REPO = 'dick-capital-bot';
var SENDER = 'dickcapital@substack.com';
var LBL = 'DC-Bot-Done';
var CHAT = 'https://substack.com/chat/6321441';

function checkDickCapital() {
  var props = PropertiesService.getScriptProperties();
  var token = props.getProperty('GITHUB_TOKEN');
  if (!token) {
    throw new Error('Set GITHUB_TOKEN first');
  }
  var label = GmailApp.getUserLabelByName(LBL);
  if (!label) {
    label = GmailApp.createLabel(LBL);
  }
  var q = 'from:' + SENDER + ' newer_than:2d';
  q = q + ' -label:' + LBL;
  var threads = GmailApp.search(q, 0, 20);
  for (var i = 0; i < threads.length; i++) {
    var msgs = threads[i].getMessages();
    for (var j = 0; j < msgs.length; j++) {
      handle(msgs[j], token);
    }
    threads[i].addLabel(label);
  }
}

function handle(msg, token) {
  if (msg.getFrom().indexOf(SENDER) < 0) {
    return;
  }
  var data = {
    body: msg.getPlainBody().slice(0, 6000),
    chat_url: CHAT,
    date: msg.getDate().toISOString(),
    subject: msg.getSubject()
  };
  poke(token, data);
}

function poke(token, data) {
  var base = 'https://api.github.com/repos/';
  var api = base + OWNER + '/' + REPO + '/dispatches';
  var body = {
    event_type: 'new-substack-email',
    client_payload: data
  };
  var opts = {
    method: 'post',
    contentType: 'application/json',
    muteHttpExceptions: true,
    headers: {
      Authorization: 'Bearer ' + token,
      Accept: 'application/vnd.github+json'
    },
    payload: JSON.stringify(body)
  };
  var resp = UrlFetchApp.fetch(api, opts);
  Logger.log('HTTP ' + resp.getResponseCode());
}

// --- Nudge when Dick replies inside one of his threads ---
var DICK_ID = 394376039;

function checkDickReplies() {
  var p = PropertiesService.getScriptProperties();
  var ck = p.getProperty('SUBSTACK_COOKIE');
  var tok = p.getProperty('DISCORD_BOT_TOKEN');
  var chan = p.getProperty('DISCORD_CHANNEL_ID');
  var u = 'https://substack.com/api/v1/community/';
  u = u + 'publications/6321441/posts';
  var r = UrlFetchApp.fetch(u, {
    muteHttpExceptions: true,
    headers: { Cookie: ck }
  });
  if (r.getResponseCode() != 200) {
    Logger.log('Substack HTTP ' + r.getResponseCode());
    return;
  }
  var threads = (JSON.parse(r.getContentText()).threads) || [];
  var primed = p.getProperty('PRIMED_REPLIES');
  for (var i = 0; i < threads.length; i++) {
    var cp = threads[i].communityPost;
    if (!cp || cp.user_id !== DICK_ID) continue;
    var rc = cp.recent_commenters || [];
    if (rc.length === 0 || rc[0].id !== DICK_ID) continue;
    var ts = cp.most_recent_comment_created_at;
    if (!ts) ts = cp.max_comment_created_at;
    var key = 'NUDGED_' + cp.id;
    if (!primed) { p.setProperty(key, ts); continue; }
    if (p.getProperty(key) === ts) continue;
    nudge(tok, chan, cp);
    p.setProperty(key, ts);
  }
  if (!primed) p.setProperty('PRIMED_REPLIES', '1');
}

function nudge(tok, chan, cp) {
  var t = tickerOf(cp.body);
  var link = 'https://substack.com/chat/6321441/post/' + cp.id;
  var msg = '💬 Dick replied in the ' + t + ' thread → ' + link;
  var url = 'https://discord.com/api/v10/channels/';
  url = url + chan + '/messages';
  UrlFetchApp.fetch(url, {
    method: 'post',
    contentType: 'application/json',
    muteHttpExceptions: true,
    headers: { Authorization: 'Bot ' + tok },
    payload: JSON.stringify({ content: msg })
  });
}

function tickerOf(body) {
  var m = (body || '').match(/\$[A-Za-z]{1,6}/);
  if (m) return m[0];
  var s = (body || '').slice(0, 30);
  return s ? '"' + s + '"' : 'a';
}
