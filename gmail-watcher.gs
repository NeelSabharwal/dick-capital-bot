/**
 * Dick Capital -> Discord: Gmail watcher (Google Apps Script)
 * ----------------------------------------------------------------------
 * Lives on nsabharwal2006@gmail.com and runs every minute. When a new
 * "New thread from Dick Capital" email arrives from dickcapital@substack.com,
 * it pokes the GitHub Actions bot with the email's text. The bot then
 * extracts the pick and posts it to Discord (~2-4 min after Dick posts).
 *
 * ONE-TIME SETUP:
 *   1. Create a GitHub fine-grained token:
 *        github.com -> Settings -> Developer settings ->
 *        Fine-grained tokens -> Generate new token
 *        - Repository access: Only select repositories -> dick-capital-bot
 *        - Permissions -> Repository permissions -> Contents: Read and write
 *      Copy the token (starts with "github_pat_...").
 *   2. script.google.com (signed in as nsabharwal2006@gmail.com)
 *        -> New project -> delete the sample -> paste THIS whole file -> Save.
 *   3. Gear (Project Settings) -> Script properties -> Add script property:
 *        Property: GITHUB_TOKEN     Value: <the token from step 1>
 *   4. Pick "checkDickCapital" in the top toolbar -> Run -> approve the
 *      permission prompts (Gmail access + connect to an external service).
 *   5. Clock icon (Triggers) -> Add trigger:
 *        function = checkDickCapital, source = Time-driven,
 *        type = Minutes timer, interval = Every minute -> Save.
 */

const GITHUB_OWNER = 'NeelSabharwal';
const GITHUB_REPO  = 'dick-capital-bot';
const SENDER       = 'dickcapital@substack.com';
const DONE_LABEL   = 'DC-Bot-Done';

function checkDickCapital() {
  const token = PropertiesService.getScriptProperties().getProperty('GITHUB_TOKEN');
  if (!token) throw new Error('Missing GITHUB_TOKEN script property (setup step 3).');

  const label = GmailApp.getUserLabelByName(DONE_LABEL) || GmailApp.createLabel(DONE_LABEL);

  // New mail from Dick Capital in the last 2 days we haven't handled yet.
  const threads = GmailApp.search('from:' + SENDER + ' newer_than:2d -label:' + DONE_LABEL, 0, 20);

  threads.forEach(function (thread) {
    thread.getMessages().forEach(function (msg) {
      if (msg.getFrom().indexOf(SENDER) === -1) return;
      poke(token, {
        body: msg.getPlainBody().slice(0, 6000),
        chat_url: findChatUrl(msg.getBody()) || 'https://substack.com/chat/6321441',
        date: msg.getDate().toISOString(),
        subject: msg.getSubject()
      });
    });
    thread.addLabel(label); // mark handled so we never double-post
  });
}

function poke(token, clientPayload) {
  const resp = UrlFetchApp.fetch(
    'https://api.github.com/repos/' + GITHUB_OWNER + '/' + GITHUB_REPO + '/dispatches',
    {
      method: 'post',
      contentType: 'application/json',
      headers: { Authorization: 'Bearer ' + token, Accept: 'application/vnd.github+json' },
      payload: JSON.stringify({ event_type: 'new-substack-email', client_payload: clientPayload }),
      muteHttpExceptions: true
    }
  );
  Logger.log('GitHub dispatch -> HTTP ' + resp.getResponseCode()); // 204 = success
}

function findChatUrl(html) {
  const m = html.match(/https?:\/\/substack\.com\/chat\/\d+\/post\/[a-z0-9-]+/i);
  return m ? m[0] : null;
}
