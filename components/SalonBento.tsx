'use client';

import { ArrowUpRight, CalendarDays, Mic, Scissors } from 'lucide-react';
import { BentoGrid, BentoGridItem } from '@/components/ui/bento-grid';
import { openConcierge } from '@/lib/api';

export default function SalonBento() {
  return (
    <section className="section salon-bento" aria-labelledby="studio-experience-title">
      <div className="section-heading">
        <div><div className="eyebrow">YOUR GLOW, YOUR WAY</div><h2 id="studio-experience-title">A little care. Made easy.</h2></div>
        <p>Explore the menu, ask a question,<br/>and make time for yourself.</p>
      </div>
      <BentoGrid className="salon-bento-grid">
        <BentoGridItem
          className="salon-bento-card salon-bento-wide"
          header={<div className="bento-photo"><img src="/salon.jpg" alt="Styling stations in our bright, welcoming studio" loading="lazy"/><span>A fresh perspective starts here.</span></div>}
          icon={<Scissors size={18} aria-hidden="true"/>}
          title={<h3>Find your next feel-good.</h3>}
          description={<><p>From a thoughtful trim to a whole new look. Find the service that feels like you.</p><a className="bento-action" href="#services">Explore the menu <ArrowUpRight size={15}/></a></>}
        />
        <BentoGridItem
          className="salon-bento-card"
          header={<div className="bento-voice-art" aria-hidden="true"><div className="bento-voice-sphere"><Mic size={27} strokeWidth={1.3}/></div><span>Let’s talk it through.</span></div>}
          icon={<Mic size={18} aria-hidden="true"/>}
          title={<h3>A question away.</h3>}
          description={<><p>Ask our AI concierge about services, prices and salon care.</p><button className="bento-action" onClick={() => openConcierge('Can you help me choose a service?')}>Ask the concierge <ArrowUpRight size={15}/></button></>}
        />
        <BentoGridItem
          className="salon-bento-card"
          header={<div className="bento-booking-art" aria-hidden="true"><CalendarDays size={48} strokeWidth={1}/><span>A little space in your day.</span><div className="bento-calendar-dots">{Array.from({length:7},(_,i)=><i key={i}/>)}</div></div>}
          icon={<CalendarDays size={18} aria-hidden="true"/>}
          title={<h3>Your time to unwind.</h3>}
          description={<><p>Tell us your preferred day and stylist. We’ll check the available times.</p><button className="bento-action" onClick={() => openConcierge('I would like to find an appointment.')}>Find a time <ArrowUpRight size={15}/></button></>}
        />
      </BentoGrid>
    </section>
  );
}
