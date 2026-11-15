/* Shared voice client for the customer and owner test panel. No provider keys. */
class SalonVoice {
  constructor(context, append, host) {
    this.context = context;
    this.append = append;
    this.queue = [];
    this.epoch = 0;
    this.active = false;
    this.vadSpeechFrames = 0;   // consecutive frames above threshold
    this.vadSilenceFrames = 0;  // consecutive frames below threshold after speech
    this.vadSpeaking = false;
    this.button = document.createElement('button');
    this.button.type = 'button';
    this.button.className = 'btn-secondary';
    this.button.textContent = '🎙 Talk';
    this.button.setAttribute('aria-label', 'Open voice mode');
    host.append(this.button);
    this.button.onclick = () => this.open();

    this.panel = document.createElement('dialog');
    this.panel.className = 'voice-panel';
    this.panel.setAttribute('aria-label', 'Salon voice assistant');
    this.panel.innerHTML = `
      <div class="voice-card-header">
        <span class="voice-card-title" data-voice-salon-name>Salon guide</span>
        <div class="voice-card-actions">
          <button type="button" tabindex="0" class="voice-icon-btn voice-end-btn" data-end aria-label="End call / switch to text" title="End call">
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-phone-off" aria-hidden="true">
              <path d="M10.1 13.9a14 14 0 0 0 3.732 2.668 1 1 0 0 0 1.213-.303l.355-.465A2 2 0 0 1 17 15h3a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2 18 18 0 0 1-12.728-5.272"></path>
              <path d="M22 2 2 22"></path>
              <path d="M4.76 13.582A18 18 0 0 1 2 4a2 2 0 0 1 2-2h3a2 2 0 0 1 2 2v3a2 2 0 0 1-.8 1.6l-.468.351a1 1 0 0 0-.292 1.233 14 14 0 0 0 .244.473"></path>
            </svg>
          </button>
          <button type="button" tabindex="0" class="voice-icon-btn voice-minimize-btn" data-close aria-label="Minimize" title="Minimize">
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-chevron-down" aria-hidden="true">
              <path d="m6 9 6 6 6-6"></path>
            </svg>
          </button>
        </div>
      </div>

      <div class="voice-hero">
        <button type="button" class="voice-orb-button" data-orb-button aria-label="Talk to salon" tabindex="0">
          <div class="voice-orb-glow" aria-hidden="true"></div>
          <div class="voice-orb-ripple" aria-hidden="true"></div>
          <div class="voice-orb" aria-hidden="true">
            <div class="voice-orb-inner"></div>
            <canvas class="voice-orb-canvas" width="160" height="160" aria-hidden="true"></canvas>
          </div>
          <span class="voice-orb-mark" aria-hidden="true">
            <svg xmlns="http://www.w3.org/2000/svg" width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-mic" aria-hidden="true">
              <path d="M12 19v3"></path>
              <path d="M19 10v2a7 7 0 0 1-14 0v-2"></path>
              <rect x="9" y="2" width="6" height="13" rx="3"></rect>
            </svg>
          </span>
        </button>
      </div>

      <p class="voice-prompt-text" data-status>Speak or type a message</p>

      <div class="transcript-lines scroll-fade" data-transcript-container>
        <div class="transcript-inner">
          <div class="transcript-spacer"></div>
          <div class="transcript-row user" data-user-row style="display: none;">
            <span class="voice-user-bubble" data-user-text></span>
          </div>
          <div class="transcript-row bot">
            <span class="voice-captions" aria-live="polite">Hello, how can I help you today?</span>
          </div>
        </div>
      </div>

      <form class="voice-input-form" data-voice-form>
        <input type="text" data-voice-input placeholder="Type a message" aria-label="Message the voice agent" class="voice-text-input" autocomplete="off" />
        <button type="submit" data-voice-send class="voice-send-btn">Send</button>
      </form>

      <!-- Headless / hidden controls for automated testing and programmatic contract -->
      <div class="voice-headless-controls" style="display: none !important;" aria-hidden="true">
        <select data-mode aria-label="Conversation mode">
          <option value="push">Push to talk</option>
          <option value="live" selected>Hands-free</option>
        </select>
        <button type="button" data-talk>Start speaking</button>
        <button type="button" data-stop>Finish speaking</button>
        <button type="button" data-interrupt>Interrupt</button>
        <button type="button" data-mute aria-pressed="false">Mute mic</button>
        <pre data-debug>No turn yet</pre>
      </div>`;

    document.body.append(this.panel);
    this.status = this.panel.querySelector('[data-status]');
    this.captions = this.panel.querySelector('.voice-captions');
    this.userRow = this.panel.querySelector('[data-user-row]');
    this.userText = this.panel.querySelector('[data-user-text]');
    this.transcriptContainer = this.panel.querySelector('[data-transcript-container]');
    this.mode = this.panel.querySelector('[data-mode]');
    this.textInput = this.panel.querySelector('[data-voice-input]');
    this.textForm = this.panel.querySelector('[data-voice-form]');

    this.panel.querySelector('[data-close]')?.addEventListener('click', () => this.close());
    const orbBtn = this.panel.querySelector('[data-orb-button]');
    if (orbBtn) {
      orbBtn.onclick = () => {
        if (!this.listening) this.listen().catch(e => this.failure(e));
        else this.interrupt();
      };
    }
    this.panel.querySelector('[data-talk]').onclick = () => this.listen().catch(e => this.failure(e));
    this.panel.querySelector('[data-stop]').onclick = () => this.finish();
    this.panel.querySelector('[data-interrupt]').onclick = () => this.interrupt();
    this.panel.querySelector('[data-end]').onclick = () => this.close();
    this.panel.querySelector('[data-mute]').onclick = e => {
      this.muted = !this.muted;
      this.stream?.getAudioTracks().forEach(t => { t.enabled = !this.muted; });
      if (this.muted) this.recognition?.abort();
      e.target.setAttribute('aria-pressed', String(this.muted));
    };

    if (this.textForm && this.textInput) {
      this.textForm.addEventListener('submit', (e) => {
        e.preventDefault();
        const msg = this.textInput.value.trim();
        if (!msg) return;
        this.textInput.value = '';
        this.setUserText(msg);
        if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify({type:'text', text:msg}));
        else this.submit(null, msg).catch(err => this.failure(err));
      });
    }

    this.panel.addEventListener('cancel', e => { e.preventDefault(); this.close(); });
    this.mode.onchange = () => { this.stopInput(); this.ws?.close(); this.ws = null; this.interrupt(); this.state('idle'); };
    this.initOrbCanvas();
  }

  setUserText(text) {
    if (this.userRow && this.userText) {
      this.userText.textContent = text;
      this.userRow.style.display = 'flex';
      this.scrollTranscript();
    }
  }

  setAssistantText(text) {
    if (this.captions) {
      this.captions.textContent = text;
      this.scrollTranscript();
    }
  }

  scrollTranscript() {
    // Keep panel firmly pinned at top
    if (this.panel) this.panel.scrollTop = 0;
    // Scroll transcript lines to bottom so latest text is in view
    if (this.transcriptContainer) {
      requestAnimationFrame(() => {
        this.transcriptContainer.scrollTop = this.transcriptContainer.scrollHeight;
      });
    }
  }

  initOrbCanvas() {
    const canvas = this.panel.querySelector('.voice-orb-canvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let animId = null;
    let t = 0;

    const render = () => {
      if (!this.active) {
        if (animId) cancelAnimationFrame(animId);
        animId = null;
        return;
      }
      const state = this.panel.dataset.state || 'idle';
      const speed = state === 'speaking' ? 0.038 : state === 'listening' ? 0.026 : 0.010;
      t += speed;

      const w = canvas.width;
      const h = canvas.height;
      ctx.clearRect(0, 0, w, h);

      const cx = w / 2;
      const cy = h / 2;
      const r = w * 0.44;

      // Draw soft harmonic fluid blobs to simulate living marble/clouds
      for (let i = 0; i < 5; i++) {
        const angle = t * 0.8 + (i * Math.PI * 0.4);
        const radiusDist = (r * 0.28) * Math.sin(t * 0.5 + i);
        const ox = cx + Math.cos(angle) * radiusDist;
        const oy = cy + Math.sin(angle * 1.1) * radiusDist;
        const blobR = r * (0.45 + 0.15 * Math.cos(t * 0.6 + i));

        const grad = ctx.createRadialGradient(ox, oy, 2, cx, cy, blobR);
        if (i % 2 === 0) {
          grad.addColorStop(0, getComputedStyle(this.panel).getPropertyValue('--voice-value-52').trim());
          grad.addColorStop(0.5, getComputedStyle(this.panel).getPropertyValue('--voice-value-53').trim());
          grad.addColorStop(1, 'transparent');
        } else {
          grad.addColorStop(0, getComputedStyle(this.panel).getPropertyValue('--voice-value-54').trim());
          grad.addColorStop(0.6, getComputedStyle(this.panel).getPropertyValue('--voice-value-55').trim());
          grad.addColorStop(1, 'transparent');
        }

        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(ox, oy, blobR, 0, Math.PI * 2);
        ctx.fill();
      }

      if (!matchMedia('(prefers-reduced-motion: reduce)').matches) animId = requestAnimationFrame(render);
    };

    this.startOrbCanvas = () => {
      if (!animId) render();
    };
    this.stopOrbCanvas = () => {
      if (animId) {
        cancelAnimationFrame(animId);
        animId = null;
      }
    };
  }

  state(state, message) {
    this.panel.dataset.state = state;
    if (message) {
      this.status.textContent = message;
    } else if (state === 'idle') {
      this.status.textContent = 'Speak or type a message';
    } else if (state === 'listening' && this.mode?.value === 'live') {
      this.status.textContent = 'Listening... speak naturally';
    } else {
      this.status.textContent = state[0].toUpperCase() + state.slice(1) + '...';
    }

    const orbBtn = this.panel.querySelector('[data-orb-button]');
    if (orbBtn) {
      orbBtn.setAttribute('aria-label',
        state === 'listening' ? 'Listening continuously' :
        state === 'speaking' ? 'Speaking... Click to interrupt' :
        'Click to start speaking'
      );
    }
  }

  async open() {
    try {
      this.bound = {...this.context()};
      const response = await fetch(`/voice/config/${encodeURIComponent(this.bound.salon_id)}`);
      if (!response.ok) throw new Error('Voice settings could not be loaded. Please type your message.');
      this.cfg = await response.json();
      if (!this.cfg.enabled) throw new Error('Voice is disabled for this salon. You can still type.');
      this.active = true;

      // Update dynamic salon branding in header
      const titleEl = this.panel.querySelector('[data-voice-salon-name]');
      const sMap = {
        'glow-studio': 'Glow Studio guide',
        'serenity-spa': 'Serenity Spa guide',
        'gentlemans-cut': "The Gentleman's Cut guide"
      };
      const guideTitle = window.currentSalonData ? `${window.currentSalonData.name} guide` : (sMap[this.bound.salon_id] || 'Salon guide');
      if (titleEl) titleEl.textContent = guideTitle;

      if (this.userRow) this.userRow.style.display = 'none';
      this.setAssistantText(this.cfg.greeting);

      this.playbackContext = new AudioContext({sampleRate:24000});
      await this.playbackContext.resume();
      this.pcmSources = new Set();
      this.panel.showModal();
      this.panel.scrollTop = 0;
      this.startOrbCanvas();
      this.state('idle');

      if (this.mode.value === 'live') {
        setTimeout(() => { if (this.valid()) this.listen().catch(e => this.failure(e)); }, 500);
      }

      // Focus text input without scrolling dialog
      setTimeout(() => {
        this.panel.scrollTop = 0;
        this.textInput?.focus({preventScroll: true});
      }, 50);

    } catch (e) { this.append('bot', e.message); }
  }

  valid() {
    const now = this.context();
    return this.active && now.salon_id === this.bound.salon_id && now.session_id === this.bound.session_id;
  }

  async listen() {
    if (!this.valid()) return this.close();
    if (this.listening) return;
    this.interrupt();
    this.muted = false;
    this.panel.querySelector('[data-mute]').setAttribute('aria-pressed', 'false');
    const r = await fetch(`/voice/config/${encodeURIComponent(this.bound.salon_id)}`);
    if (!r.ok) throw new Error('Unable to load voice settings.');
    this.cfg = await r.json();
    if (!this.cfg.enabled) throw new Error('Voice has been disabled for this salon.');
    this.listening = true;
    if (this.mode.value === 'live') await this.connect();
    if (this.mode.value === 'live' && this.cfg.stt === 'browser') throw new Error('Configure Sarvam to use live voice calls. You can still type.');
    if (this.cfg.stt === 'browser' || this.browserFallback) return this.browserListen();
    if (!navigator.mediaDevices?.getUserMedia || !window.AudioWorkletNode) {
      this.listening = false;
      throw new Error('This browser cannot stream microphone audio. Please use a current browser or type.');
    }
    this.stream = await navigator.mediaDevices.getUserMedia({audio: {channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true}});
    if (!this.valid()) return this.stopInput();
    this.audioContext = new AudioContext();
    await this.audioContext.audioWorklet.addModule('/static/js/voice-worklet.js');
    await this.audioContext.resume();
    this.source = this.audioContext.createMediaStreamSource(this.stream);
    this.capture = new AudioWorkletNode(this.audioContext, 'voice-capture');
    this.source.connect(this.capture);
    this.capture.connect(this.audioContext.destination);
    this.frames = [];
    this.speechFrames = 0;
    this.vadSpeechFrames = 0;
    this.vadSilenceFrames = 0;
    this.vadSpeaking = false;
    this.capture.port.onmessage = ({data}) => {
      if (!this.valid() || this.muted) return;
      // Unpack worklet message: either {pcm, rms} object or plain ArrayBuffer (fallback)
      const pcmBuffer = (data && data.pcm) ? data.pcm : data;
      const rms = (data && data.rms != null) ? data.rms
        : Math.sqrt(new Int16Array(pcmBuffer).reduce((n, v) => n + (v / 32768) ** 2, 0) / (pcmBuffer.byteLength / 2));

      if (this.mode.value === 'live' && this.ws?.readyState === WebSocket.OPEN) {
        this.speechFrames = rms > 0.025 ? this.speechFrames + 1 : 0;
        if (rms > 0.025) this.lastVoiceAt = performance.now();
        // Pause locally within 80ms; the transcript decides whether to resume a backchannel.
        if (this.speechFrames === 4 && this.playing) this.pausePlayback();
        if (rms > 0.025 && this.playbackContext?.state === 'suspended') {
          clearTimeout(this.resumeTimer);
          this.resumeTimer = setTimeout(() => this.playbackContext?.resume(), 2000);
        }
        if (this.ws.bufferedAmount < 64000) this.ws.send(pcmBuffer);
        else this.failure(new Error('Connection is too slow. Please use push-to-talk.'));
      } else {
        this.frames.push(pcmBuffer);
      }
    };
    if (this.mode.value === 'push') this.recordTimer = setTimeout(() => this.finish(), 29000);
    this.state('listening');
  }

  browserListen() {
    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Recognition) {
      this.listening = false;
      throw new Error('Speech recognition is unavailable in this browser. Use a configured microphone provider or switch to text.');
    }
    this.listening = true;
    this.recognition = new Recognition();
    this.recognition.lang = this.cfg.language_default;
    this.recognition.interimResults = true;
    this.recognition.continuous = this.mode.value === 'live';
    this.recognition.onspeechstart = () => { if (this.playing) this.interrupt(); };
    this.recognition.onresult = e => {
      if (!this.valid()) return;
      let partial = '';
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const result = e.results[i];
        if (result.isFinal) {
          const text = result[0].transcript.trim();
          const confidence = result[0].confidence;
          if (confidence > 0 && confidence < .5) { this.state('listening', 'I could not hear clearly. Please repeat.'); continue; }
          if (this.mode.value === 'live' && this.ws?.readyState === WebSocket.OPEN) {
            this.interrupt();
            this.ws.send(JSON.stringify({type:'text', text}));
          } else {
            this.recognition.stop();
            this.listening = false;
            this.setUserText(text);
            this.submit(null, text, confidence || null).catch(err => this.failure(err));
          }
        } else partial += result[0].transcript;
      }
      if (partial) this.setAssistantText(partial);
    };
    this.recognition.onerror = e => {
      if (e.error === 'aborted') return;
      this.failure(new Error(e.error === 'not-allowed' ? 'Microphone access was denied. Allow it in browser settings or switch to text.' : 'Browser speech is unavailable. Please try again or type.'));
    };
    this.recognition.onend = () => { this.listening = false; };
    this.recognition.start();
    this.state('listening', 'Listening with browser speech recognition.');
  }

  stopInput() {
    clearTimeout(this.recordTimer);
    this.listening = false;
    this.recognition?.abort(); this.recognition = null;
    this.capture?.disconnect(); this.source?.disconnect();
    this.stream?.getTracks().forEach(t => t.stop()); this.stream = null;
    this.audioContext?.close(); this.audioContext = null;
  }

  async finish() {
    if (this.recognition) { this.recognition.stop(); return; }
    if (this.mode.value === 'live') {
      this.ws?.send(JSON.stringify({type:'stop'}));
      return;
    }
    const frames = this.frames || [];
    this.frames = [];
    this.stopInput();
    if (!frames.length) return this.state('idle', 'No speech recorded. Try Start speaking.');
    try { await this.submit(this.wav(frames)); } catch (e) { this.failure(e); }
  }

  wav(frames) {
    const size = frames.reduce((n, f) => n + f.byteLength, 0);
    const out = new ArrayBuffer(44 + size), view = new DataView(out);
    const str = (offset, s) => [...s].forEach((c,i) => view.setUint8(offset+i,c.charCodeAt(0)));
    str(0,'RIFF'); view.setUint32(4,36+size,true); str(8,'WAVE'); str(12,'fmt ');
    view.setUint32(16,16,true); view.setUint16(20,1,true); view.setUint16(22,1,true);
    view.setUint32(24,16000,true); view.setUint32(28,32000,true); view.setUint16(32,2,true); view.setUint16(34,16,true);
    str(36,'data'); view.setUint32(40,size,true);
    let offset = 44;
    for (const frame of frames) { new Uint8Array(out,offset,frame.byteLength).set(new Uint8Array(frame)); offset += frame.byteLength; }
    return new Blob([out],{type:'audio/wav'});
  }

  async submit(audio, text='', confidence=null) {
    this.state('thinking');
    const epoch = this.epoch;
    this.request = new AbortController();
    const form = new FormData();
    form.set('salon_id',this.bound.salon_id); form.set('session_id',this.bound.session_id);
    if (audio) form.set('audio',audio,'speech.wav');
    if (text) form.set('text',text);
    if (confidence !== null) form.set('confidence',confidence);
    const r = await fetch('/voice/turn',{method:'POST',body:form,signal:this.request.signal});
    const result = await r.json();
    if (!this.valid() || epoch !== this.epoch) return;
    if (!r.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Voice request failed.');
    if (result.fallback === 'browser_stt') {
      this.browserFallback = true;
      this.state('idle', 'Speech provider unavailable. Press Start speaking to repeat with browser recognition.');
      return;
    }
    this.append('user',result.transcript); this.append('bot',result.reply);
    this.setUserText(result.transcript);
    this.setAssistantText(result.reply);
    this.panel.querySelector('[data-debug]').textContent = JSON.stringify(result.timings,null,2);
    if (result.audio_chunks?.length) {
      for (const bytes of result.audio_chunks) this.queue.push({url:`data:audio/wav;base64,${bytes}`});
    } else this.queue.push({text:result.speech_text,language:result.language,pace:this.cfg.pace});
    this.playNext();
  }

  async connect() {
    if (this.ws?.readyState === WebSocket.OPEN) return;
    const query = new URLSearchParams(this.bound);
    this.ws = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/voice/ws?${query}`);
    this.ws.binaryType = 'blob';
    await new Promise((resolve,reject) => {
      this.ws.onopen = resolve;
      this.ws.onerror = () => reject(new Error('Realtime connection unavailable. Select push-to-talk.'));
    });
    this.ws.onmessage = ({data}) => {
      if (!this.valid()) return this.close();
      if (data instanceof Blob) { this.queue.push({url:URL.createObjectURL(data),revoke:true}); this.playNext(); return; }
      const event = JSON.parse(data);
      if (event.type === 'audio_chunk') {
        if (event.generation < (this.generation || 0)) return;
        this.generation = event.generation;
        this.playPCM(event);
      } else if (event.type === 'playback_pause') {
        this.pausePlayback();
      } else if (event.type === 'playback_resume') {
        this.playbackContext?.resume();
      } else if (event.type === 'partial_transcript') {
        this.setUserText(event.text);
      } else if (event.type === 'audio_end') {
        this.audioEnded = true;
        this.pcmDone();
      } else if (event.type === 'state') {
        if (event.generation != null) this.generation = event.generation;
        if (event.interrupted) this.clearPlayback();
        if (!this.playing) this.state(event.state);
      } else if (event.type === 'final_transcript') {
        this.append('user',event.text); this.setUserText(event.text); this.delta = '';
      } else if (event.type === 'assistant_text_delta') {
        this.delta = (this.delta || '') + event.text; this.setAssistantText(this.delta);
      } else if (event.type === 'assistant_text') {
        this.append('bot',event.text); this.setAssistantText(event.text);
      } else if (event.type === 'speech') {
        this.queue.push(event); this.playNext();
      } else if (event.type === 'timings') {
        this.panel.querySelector('[data-debug]').textContent = JSON.stringify(event,null,2);
      } else if (event.type === 'error') {
        if (event.fallback === 'browser_stt') { this.browserFallback = true; this.stopInput(); }
        this.state('idle',event.message);
      }
    };
    this.ws.onclose = () => {
      if (this.active) { this.stopInput(); this.state('idle','Voice connection ended. Try push-to-talk or switch to text.'); }
    };
  }

  pausePlayback() {
    if (this.playing) this.playbackContext?.suspend();
  }

  playPCM(event) {
    const ctx = this.playbackContext;
    if (!ctx) return;
    const bytes = Uint8Array.from(atob(event.audio), c => c.charCodeAt(0));
    const samples = new DataView(bytes.buffer);
    const buffer = ctx.createBuffer(1, bytes.length / 2, event.sample_rate);
    const output = buffer.getChannelData(0);
    for (let i = 0; i < output.length; i++) output[i] = samples.getInt16(i * 2, true) / 32768;
    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(ctx.destination);
    const at = Math.max(ctx.currentTime + .015, this.pcmAt || 0);
    this.pcmAt = at + buffer.duration;
    this.pcmSources.add(source);
    source.onended = () => { this.pcmSources.delete(source); this.pcmDone(); };
    source.start(at);
    this.playing = true;
    this.state('speaking');
    if (this.audioGeneration !== event.generation) {
      this.audioGeneration = event.generation;
      this.audioEnded = false;
      const gap = this.lastVoiceAt ? Math.round(performance.now() - this.lastVoiceAt + (at - ctx.currentTime) * 1000) : null;
      this.ws?.send(JSON.stringify({type:'playback_started', generation:event.generation, turn_id:event.turn_id, gap_ms:gap}));
    }
  }

  pcmDone() {
    if (this.audioEnded && !this.pcmSources?.size) {
      this.playing = false;
      this.state('listening');
      if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify({type:'playback_done'}));
    }
  }

  playNext() {
    if (this.playing || !this.queue.length || !this.valid()) return;
    const item = this.queue.shift(), epoch = this.epoch;
    this.playing = true; this.state('speaking');
    const done = () => {
      if (item.revoke) URL.revokeObjectURL(item.url);
      if (epoch !== this.epoch) return;
      this.playing = false;
      if (this.queue.length) this.playNext(); else this.state(this.listening ? 'listening' : 'idle');
    };
    if (item.url) {
      this.player = new Audio(item.url);
      this.player.onended = done;
      this.player.onerror = done;
      this.player.play().catch(() => { done(); this.state('idle','Audio playback was blocked. Captions are available; press Start speaking to continue.'); });
    } else if ('speechSynthesis' in window) {
      const speech = new SpeechSynthesisUtterance(item.text);
      speech.lang = item.language || this.cfg.language_default;
      speech.rate = item.pace || 1;
      speech.onend = done; speech.onerror = done;
      speechSynthesis.speak(speech);
    } else { done(); this.state('idle','Spoken playback is unavailable. Read the captions or switch to text.'); }
  }

  clearPlayback() {
    clearTimeout(this.resumeTimer);
    this.epoch++;
    this.pcmSources?.forEach(source => { try { source.stop(); } catch (_) {} });
    this.pcmSources?.clear();
    this.pcmAt = 0;
    this.audioEnded = false;
    this.audioGeneration = null;
    this.playbackContext?.resume();
    this.player?.pause(); this.player = null;
    window.speechSynthesis?.cancel();
    this.queue.forEach(item => { if (item.revoke) URL.revokeObjectURL(item.url); });
    this.queue = []; this.playing = false;
  }

  interrupt() {
    this.clearPlayback();
    this.request?.abort();
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify({type:'interrupt'}));
  }

  close() {
    this.active = false;
    this.stopOrbCanvas?.();
    this.interrupt();
    this.stopInput();
    this.ws?.close();
    this.ws = null;
    this.playbackContext?.close(); this.playbackContext = null;
    if (this.panel.open) this.panel.close();
    this.button.focus();
  }

  failure(e) {
    if (e.name === 'AbortError') return;
    this.stopInput();
    this.state('idle',e.name === 'NotAllowedError' ? 'Microphone access was denied. Allow it in browser settings or switch to text.' : e.message);
  }
}
window.SalonVoice = SalonVoice;
