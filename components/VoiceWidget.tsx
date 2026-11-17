'use client';
import { useEffect, useRef } from 'react';
import { SALON } from '@/lib/api';

export default function VoiceWidget() {
  const host = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let agent: any;
    let disposed = false;
    let handler: ((e: Event) => void) | undefined;
    const init = async () => {
      const win = window as any;
      if (!win.SalonVoice && !win.glowVoiceLoading) win.glowVoiceLoading = new Promise<void>((resolve, reject) => {
        const script = document.createElement('script'); script.src = '/voice/voice.js?v=concierge-card-2'; script.onload = () => resolve(); script.onerror = reject; document.head.append(script);
      });
      if (!win.SalonVoice) await win.glowVoiceLoading;
      if (disposed || !host.current) return;
      let session = sessionStorage.getItem('glow-session');
      if (!session) { session = crypto.randomUUID(); sessionStorage.setItem('glow-session', session); }
      agent = new (window as any).SalonVoice(() => ({salon_id: SALON, session_id: session}), () => {}, host.current);
      agent.wsUrl = process.env.NEXT_PUBLIC_VOICE_WS_URL || 'ws://127.0.0.1:8001/voice/ws';
      handler = async (event: Event) => {
        const message = (event as CustomEvent).detail;
        if (message && agent.active) {
          agent.cancelMenuFollowup();
          agent.menuNavigationPending = false;
          agent.interrupt();
          agent.setUserText(message);
          if (agent.ws?.readyState === WebSocket.OPEN) agent.ws.send(JSON.stringify({type:'text', text:message}));
          else agent.submit(null, message).catch((e: Error) => agent.failure(e));
          return;
        }
        host.current?.scrollIntoView({behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block:'center'});
        agent.startVoice(message).catch((e: Error) => agent.failure(e));
      };
      window.addEventListener('open-concierge', handler);
    };
    init().catch(() => { if (host.current) host.current.textContent = 'The concierge could not load. Please refresh.'; });
    return () => { disposed = true; if (handler) window.removeEventListener('open-concierge', handler); if (agent) { agent.destroyed = true; agent.close(); agent.destroyOrbCanvas?.(); agent.panel.remove(); agent.button.remove(); } };
  }, []);
  return <div className="voice-hero-host" data-presentation="hero" ref={host}/>;
}
