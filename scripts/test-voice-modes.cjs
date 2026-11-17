const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { runInNewContext } = require('node:vm');
const scrolls = [];
const timers = new Map();
let timerId = 0;
const window = { matchMedia: () => ({ matches: false }) };
runInNewContext(readFileSync(require('node:path').join(__dirname, '../public/voice/voice.js'), 'utf8'), {
  window, document: { getElementById: () => ({ scrollIntoView: options => scrolls.push(options) }) }, WebSocket: { OPEN: 1 }, AbortController, FormData,
  setTimeout: (callback, delay) => { const id = ++timerId; timers.set(id, {callback, delay}); return id; },
  clearTimeout: id => timers.delete(id),
  fetch: async () => ({ ok: true, json: async () => ({ transcript: 'A haircut please', reply: 'Which day?', audio_chunks: ['unused'], timings: {} }) }),
});
const prototype = window.SalonVoice.prototype;
test('service requests wait for the reply before scrolling, and scroll once per reply', () => {
  const a = Object.create(prototype); a.inline = true;
  scrolls.length = 0;
  a.navigateForRequest('What services do you offer?');
  a.navigateForRequest('What services do you offer?');
  assert.equal(scrolls.length, 0);
  a.showServices(); a.showServices();
  assert.equal(scrolls.length, 1);
  assert.equal(scrolls[0].behavior, 'smooth');
  a.navigateForRequest('Show me the menu');
  a.showServices();
  assert.equal(scrolls.length, 2);
  a.navigateForRequest('Book a haircut tomorrow');
  a.navigateForRequest("Don't show the services");
  a.showServices();
  assert.equal(scrolls.length, 2);
});
test('menu follow-up waits five seconds and is cancelled by customer activity', () => {
  const a = Object.create(prototype);
  a.active = true; a.view = 'text'; a.menuAwaitingChoice = true;
  const replies = []; a.setAssistantText = text => replies.push(text);
  a.armMenuFollowup();
  const timer = timers.get(a.menuFollowupTimer);
  assert.equal(timer.delay, 5000);
  a.cancelMenuFollowup();
  assert.equal(timers.size, 0);
  a.menuAwaitingChoice = true; a.armMenuFollowup();
  timers.get(a.menuFollowupTimer).callback();
  assert.deepEqual(replies, ["Is there something else you're looking for?"]);
  assert.equal(a.menuAwaitingChoice, false);
});
function agent() {
  const calls = [];
  return Object.assign(Object.create(prototype), {
    calls, view: 'voice', cfg: { enabled: true },
    panel: { dataset: {}, querySelectorAll: () => [], querySelector: () => ({}) },
    open: async () => calls.push('open'), listen: async () => calls.push('listen'),
    interrupt: () => calls.push('interrupt'), stopInput: () => calls.push('stop'),
    state: () => {}, textInput: { focus: () => calls.push('focus') }, scrollTranscript: () => {},
  });
}
test('one voice activation initializes the session then listens', async () => {
  const a = agent(); await a.startVoice();
  assert.deepEqual(a.calls, ['open', 'listen']);
  assert.equal(a.startingVoice, false);
});
test('text conversation stops microphone and socket without starting capture', async () => {
  const a = agent(); a.ws = { close: () => a.calls.push('socket-close') };
  await a.setView('text');
  assert.deepEqual(a.calls, ['interrupt', 'stop', 'socket-close', 'open', 'focus']);
  assert.equal(a.panel.dataset.view, 'text'); assert.equal(a.ws, null);
});
test('switching to text during initialization prevents late microphone capture', async () => {
  const a = agent(); a.open = async () => { a.view = 'text'; };
  await a.startVoice(); assert.ok(!a.calls.includes('listen'));
});
test('text replies update history without playing generated audio', async () => {
  const a = agent(); Object.assign(a, {
    view: 'text', bound: { salon_id: 'salon', session_id: 'session' }, epoch: 0,
    valid: () => true, append: () => {}, setUserText: () => a.calls.push('user'),
    setAssistantText: () => a.calls.push('reply'), refreshBooking: () => {},
    playNext: () => a.calls.push('play'), queue: [],
  });
  await a.performSubmit(null, 'A haircut please');
  assert.deepEqual(a.calls, ['user', 'reply']); assert.equal(a.queue.length, 0);
});
