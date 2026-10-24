const test=require('node:test');
const assert=require('node:assert/strict');
const {globalSearchResults}=require('../electron/whatsapp-window.cjs');
function documentFor(query,text,rows=[]){
 const side={innerText:text,querySelector:selector=>selector.includes('progressbar')?null:rows.length?{querySelectorAll:()=>rows}:null};
 return {querySelector:selector=>selector.includes('data-tab')?{value:query}:selector==='#side'?side:null};
}
test('WhatsApp global search rejects stale queries and unrecognized empty interfaces',()=>{
 assert.deepEqual(globalSearchResults(documentFor('old','No results found'),'new'),{ready:false});
 assert.deepEqual(globalSearchResults(documentFor('Alan',''),'Alan'),{ready:false});
 assert.deepEqual(globalSearchResults(documentFor('Alan','Searching'),'Alan'),{ready:false});
});
test('WhatsApp global search accepts explicit no-results state only for current query',()=>{
 assert.deepEqual(globalSearchResults(documentFor('Alan','No chats, contacts or messages found'),'Alan'),{ready:true,chats:[]});
});
test('WhatsApp search returns bounded matching snippets without opening conversations',()=>{
 const row={innerText:'Alan\nA message matching the search',querySelector:()=>({getAttribute:()=> 'Alan',textContent:'Alan'})};
 const result=globalSearchResults(documentFor('Alan','Messages',[row]),'Alan');
 assert.equal(result.ready,true);assert.equal(result.chats[0].title,'Alan');assert.equal(result.chats[0].unread,null);
 assert.ok(result.chats[0].preview.includes('matching'));
});
