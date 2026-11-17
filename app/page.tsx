'use client';
import { useEffect, useState } from 'react';
import Image from 'next/image';
import { ArrowUpRight, MapPin, Clock } from 'lucide-react';
import { api, SALON, SalonData, openConcierge } from '@/lib/api';
import VoiceWidget from '@/components/VoiceWidget';
import './salon-home.css';

const rituals = [
  { name: 'Hair & styling', image: '/hair-ritual.jpg', alt: 'A stylist caring for a client’s hair', note: 'A fresh cut. A beautiful finish.', query: 'What hair services do you offer?' },
  { name: 'Care & renewal', image: '/salon.jpg', alt: 'A bright and relaxing salon space', note: 'A little time to feel your best.', query: 'Tell me about your skin and hair care treatments.' },
  { name: 'Grooming & finishing', image: '/barber-care.jpg', alt: 'A barber carefully shaping a client’s beard', note: 'Thoughtful details. Personal style.', query: 'Tell me about your grooming services.' },
];

export default function Home() {
  const [data, setData] = useState<SalonData>();
  const [error, setError] = useState(false);
  const load = () => { setError(false); api<SalonData>(`/salons/${SALON}`).then(setData).catch(() => setError(true)); };
  useEffect(load, []);
  return <div className="reference-shell"><div className="salon-home">
    <header className="reference-nav">
      <a className="reference-brand" href="#" aria-label="Glow Care home">Glow Care</a>
      <nav aria-label="Main navigation"><a href="#" aria-current="page">Home</a><a href="#studio">About</a><a href="#services">Service</a><a href="#services">Pricing</a></nav>
      <button className="ribbon-button outline-button" onClick={() => openConcierge()}>Book Now</button>
    </header>
    <main>
      <section className="reference-hero" aria-labelledby="hero-title">
        <div className="golden-aura" aria-hidden="true"><svg viewBox="0 0 1600 300" preserveAspectRatio="none"><defs><linearGradient id="aura-gold" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stopColor="#e8cf9c" stopOpacity="0"/><stop offset=".22" stopColor="#d4af65" stopOpacity=".4"/><stop offset=".5" stopColor="#d2a451" stopOpacity=".7"/><stop offset=".78" stopColor="#d4af65" stopOpacity=".4"/><stop offset="1" stopColor="#e8cf9c" stopOpacity="0"/></linearGradient><filter id="aura-soft" filterUnits="userSpaceOnUse" x="-300" y="-300" width="2200" height="900"><feGaussianBlur stdDeviation="14"/></filter></defs><g fill="none" stroke="url(#aura-gold)"><path className="aura-mist" d="M-100 180 C200 15 500 280 800 150 S1380 40 1700 180"/><path className="aura-wave wave-one" d="M-100 180 C200 15 500 280 800 150 S1380 40 1700 180"/><path className="aura-wave wave-two" d="M-100 142 C230 280 500 30 800 150 S1370 270 1700 120"/><path className="aura-wave wave-three" d="M-100 200 C290 65 560 210 800 150 S1390 70 1700 195"/><path className="aura-shimmer" d="M-100 180 C200 15 500 280 800 150 S1380 40 1700 180"/></g></svg></div>
        <div className="reference-hero-copy">
          <div className="salon-welcome"><span>✦</span><p>Personal care. Beautiful results.</p></div>
          <h1 id="hero-title"><span>Your next look,</span><span><em>beautifully yours.</em></span></h1>
          <p className="reference-intro">Thoughtful cuts, beautiful colour, and a little time for you. Find your perfect service and book your visit with Glow.</p>
          <div className="reference-actions"><button className="ribbon-button gold-button" onClick={() => openConcierge()}>Book an appointment</button><a className="ribbon-button outline-button" href="#services">Explore Services</a></div>
        </div>
        <div className="center-concierge" aria-label="Talk to your salon concierge"><div className="concierge-heading"><p>YOUR PERSONAL SALON CONCIERGE</p></div><VoiceWidget/></div>
        <figure className="hero-photo-left"><div><Image src="/hair-ritual.jpg" alt="A stylist giving a client a fresh salon finish" fill sizes="(max-width: 760px) 40vw, 240px" preload/></div><figcaption>A little care. A beautiful feeling.</figcaption></figure>
        <div className="reference-photo"><svg width="0" height="0" aria-hidden="true"><defs><clipPath id="salon-photo-shape" clipPathUnits="objectBoundingBox"><path d="M .1 0 H .78 Q .85 0 .85 .07 V .11 C .85 .18 1 .04 1 .18 V .93 Q 1 1 .93 1 H .22 Q .14 1 .14 .92 V .88 Q .14 .84 .08 .84 Q 0 .84 0 .76 V .08 Q 0 0 .1 0 Z"/></clipPath></defs></svg><div className="photo-gold-outline"/><div className="photo-silhouette"><Image src="/barber-care.jpg" alt="A barber providing careful, personalized grooming at a salon" fill sizes="(max-width: 760px) 40vw, 220px" preload/></div></div>
      </section>
      <section className="reference-services" id="rituals" aria-labelledby="services-title">
        <h2 id="services-title">Choose your <em>ritual</em></h2><p className="section-subtitle">A little care, tailored to you.</p>
        <div className="ritual-grid">{rituals.map(ritual => <button className="ritual-card" key={ritual.name} onClick={() => openConcierge(ritual.query)}><div className="ritual-photo"><Image src={ritual.image} alt={ritual.alt} fill sizes="(max-width: 760px) 80vw, 270px"/></div><h3>{ritual.name}</h3><p>{ritual.note}</p><span>Discover more <ArrowUpRight size={13}/></span></button>)}</div>
      </section>
      <section className="reference-menu" id="services" aria-labelledby="menu-title"><div className="menu-heading"><span>THE SALON MENU</span><h2 id="menu-title">Find your feel-good.</h2><p>Choose a service to hear more from your concierge.</p></div>
        {error ? <div className="menu-message" role="status">The menu couldn't load.<button onClick={load}>Try again</button></div> : !data ? <p className="menu-message" role="status">Getting the salon menu ready…</p> : <div className="reference-menu-list">{data.services.map(service => <button key={service._id} onClick={() => openConcierge(`Tell me about ${service.name}.`)}><span><strong>{service.name}</strong><small>{service.duration_min} min · {service.category}</small></span><span className="service-price">₹{service.price.toLocaleString('en-IN')} <ArrowUpRight size={15}/></span></button>)}</div>}
      </section>
      <section className="reference-studio" id="studio" aria-labelledby="studio-title"><div className="studio-photo"><Image src="/salon.jpg" alt="A sunlit salon with styling chairs and mirrors" fill sizes="(max-width: 760px) 80vw, 400px"/></div><div className="studio-copy"><span>A MOMENT JUST FOR YOU</span><h2 id="studio-title">Good care.<br/><em>Beautiful confidence.</em></h2><p>Your own style, thoughtfully looked after.<br/>We look forward to welcoming you.</p><div><MapPin size={15}/><span>{data?.salon.address || 'Indiranagar, Bengaluru'}</span></div><div><Clock size={15}/><span>{data ? `Monday–Friday · ${data.salon.hours.mon}` : 'Ask your concierge about salon hours'}<small>India Standard Time</small></span></div><button className="ribbon-button gold-button" onClick={() => openConcierge()}>Plan your visit</button></div></section>
    </main>
    <footer className="reference-footer"><a className="reference-brand" href="#">Glow Care</a><p>Illustrative salon · Demo bookings only</p><span>Powered by <strong>da Salon</strong></span></footer>
  </div></div>;
}
