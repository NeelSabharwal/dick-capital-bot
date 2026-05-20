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
