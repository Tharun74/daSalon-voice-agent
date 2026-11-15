'use client';
import { useEffect, useState } from 'react';
import { ArrowUpRight, ArrowRight, Sparkles, MapPin, Clock, Mic, Scissors, Flower2 } from 'lucide-react';
import { api, SALON, SalonData, openConcierge } from '@/lib/api';
import VoiceWidget from '@/components/VoiceWidget';

export default function Home() {
  const [data, setData] = useState<SalonData>();
  const [error, setError] = useState('');
  const [category, setCategory] = useState('All');
  const load = () => { setError(''); api<SalonData>(`/salons/${SALON}`).then(setData).catch(() => setError('Our service menu is taking a moment to connect.')); };
  useEffect(load, []);
  const services = data?.services.filter(s => category === 'All' || s.category === category) || [];
  return <>
    <header className="header"><a className="wordmark" href="#">glow<span>STUDIO</span></a><nav aria-label="Main navigation"><a href="#services">The menu</a><a href="#visit">Find us</a><button className="nav-book" onClick={() => openConcierge()}>Book a little me-time <ArrowUpRight size={15}/></button></nav></header>
    <main>
      <section className="hero">
        <div className="hero-copy"><div className="eyebrow"><span className="tiny-sun">✳</span> HAIR, SKIN & A FRESH START</div><h1>A little time.<br/>A whole<br/><em>new glow.</em></h1><p>Good hair. A deep breath. That just-for-you feeling.<br className="desktop"/> Make room for yourself at Glow Studio.</p><button className="primary" onClick={() => openConcierge()}>Find your next appointment <ArrowUpRight size={19}/></button><div className="hero-meta"><MapPin size={14}/> Indiranagar, Bengaluru <span>•</span> All are welcome</div></div>
        <div className="hero-visual"><img src="/salon.jpg" alt="A bright salon interior with styling chairs and mirrors"/><div className="image-shade"/><span className="image-note">YOUR EVERYDAY, A LITTLE ELEVATED.</span><div className="photo-sticker"><Flower2 size={28} strokeWidth={1}/><span>Come as you are.<br/><i>Leave feeling like you.</i></span></div><div className="image-index">01 / THE STUDIO</div></div>
      </section>
      <div className="intro-strip"><span><Scissors size={17}/> Thoughtful cuts & colour</span><span><Flower2 size={18}/> Care from head to toe</span><span><Mic size={17}/> A conversation away</span></div>
      <section className="services section" id="services"><div className="section-heading"><div><div className="eyebrow">THE SERVICE EDIT</div><h2>Find your feel-good.</h2></div><p>A refresh, a reset, or something completely new.<br/>Pick your service. We’ll find your time.</p></div>
        <div className="category-tabs" role="group" aria-label="Filter services">{['All', 'Hair', 'Skin', 'Nails', 'Bridal'].map(c => <button key={c} aria-pressed={category===c} onClick={() => setCategory(c)} className={category===c?'selected':''}>{c==='All'?'All services':c}</button>)}</div>
        {error ? <div className="empty"><p>{error}</p><button onClick={load}>Try again <ArrowRight size={16}/></button></div> : !data ? <div className="loading-menu" aria-live="polite">Getting the studio menu ready…</div> : <div className="service-grid">{services.map((s,i) => <button className="service" key={s._id} onClick={() => openConcierge(`I'd like to book ${s.name}.`)}><div><span className="service-category">{s.category} <span>/{String(i+1).padStart(2,'0')}</span></span><h3>{s.name}</h3><span className="duration"><Clock size={12}/>{s.duration_min} minutes</span></div><div className="service-bottom"><span>₹{s.price.toLocaleString('en-IN')}</span><span className="circle-arrow"><ArrowUpRight size={19}/></span></div></button>)}</div>}
        <p className="menu-footnote">Not sure where to start? <button onClick={() => openConcierge('Can you help me choose a service?')}>Let’s talk it through <ArrowUpRight size={13}/></button></p>
      </section>
      <section className="visit section" id="visit"><div><div className="eyebrow">YOUR NEIGHBOURHOOD PAUSE</div><h2>See you<br/><em>at the studio.</em></h2><p>{data?.salon.address || 'Indiranagar, Bengaluru'}</p></div><div className="visit-details"><div><span>OPENING HOURS</span><p>Monday–Friday <b>{data?.salon.hours.mon || '—'}</b></p><p>Saturday–Sunday <b>{data?.salon.hours.sat || '—'}</b></p><small>All appointment times are in India Standard Time.</small></div><button className="primary" onClick={() => openConcierge()}>Make yourself some time <ArrowUpRight size={18}/></button></div><Sparkles className="visit-spark" size={110} strokeWidth={.7}/></section>
    </main>
    <footer><a className="wordmark" href="#">glow<span>STUDIO</span></a><p>Illustrative salon · Demo bookings only</p><span className="powered">Made possible by <b>da Salon</b></span></footer>
    <VoiceWidget/>
  </>;
}
