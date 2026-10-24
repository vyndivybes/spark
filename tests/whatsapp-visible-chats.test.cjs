const test=require('node:test');
const assert=require('node:assert/strict');
const {visibleChatPreviews}=require('../electron/whatsapp-window.cjs');
function row({title,preview,unread}) {
  return {innerText: title+'\n'+preview,
    querySelector:selector=>selector.includes('cell-frame-title')?{getAttribute:()=>null,textContent:title}:
      /unread/i.test(selector)?(unread?{true:true}:null):null};
}
function documentFor(rows,root=true) {
  const rootElement=root?{querySelectorAll:()=>rows}:null;
  return {querySelector:selector=>root&&/pane-side|chat-list|Chat list/i.test(selector)?rootElement:null};
}
test('WhatsApp visible chat previews read a populated mock chat list without a query',()=>{
  const chats=visibleChatPreviews(documentFor([
    row({title:'Alan',preview:'Sounds good, ship it.',unread:true}),
    row({title:'Project team',preview:'Sam: Review at 10 tomorrow.',unread:false}),
    row({title:'Family',preview:'Mom: call when you can.',unread:null}),
  ])).chats;
  assert.equal(chats.length,3);
  assert.deepEqual(chats.map(chat=>chat.title),['Alan','Project team','Family']);
  assert.equal(chats[0].unread,true);
  assert.equal(chats[1].unread,null);
  assert.ok(chats[0].preview.includes('Sounds good'));
});
test('WhatsApp visible chat previews fail closed when no chat rows are loaded',()=>{
  assert.throws(()=>visibleChatPreviews(documentFor([])),/No recognizable chat rows loaded/);
});
test('WhatsApp visible chat previews fail closed when the chat list is unavailable',()=>{
  assert.throws(()=>visibleChatPreviews(documentFor([],false)),/Chat list unavailable/);
});
