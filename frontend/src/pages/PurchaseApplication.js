import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import AddressAutocomplete from '../components/AddressAutocomplete';
import EmployerAutocomplete from '../components/EmployerAutocomplete';
import './AdaptiveURLA.css';

/**
 * PurchaseApplication - Streamlined Home Purchase Application
 *
 * Tailored 6-Stage Flow for Home Buyers:
 * 1. Declarations - Key questions for personalization
 * 2. Profile - Personal information
 * 3. Income - Employment and income details
 * 4. Assets - Savings and down payment funds
 * 5. Property - New home details and loan program
 * 6. Review - Summary and submit
 */

const STAGES = [
  { id: 'declarations', label: 'Your Story', icon: 'story', description: 'Quick questions to personalize' },
  { id: 'profile', label: 'About You', icon: 'profile', description: 'The basics about you' },
  { id: 'income', label: 'Your Income', icon: 'income', description: 'How you earn' },
  { id: 'assets', label: 'Your Assets', icon: 'assets', description: 'Down payment funds' },
  { id: 'property', label: 'New Home', icon: 'home', description: 'Property details' },
  { id: 'review', label: 'Review', icon: 'review', description: 'Review your info' },
  { id: 'planning', label: 'Your Goals', icon: 'goals', description: 'Mortgage preferences' },
  { id: 'schedule', label: 'Schedule', icon: 'calendar', description: 'Book a call' },
];

// Professional SVG Icon component
const Icon = ({ name, size = 24, className = '' }) => {
  const icons = {
    story: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/>
        <polyline points="14,2 14,8 20,8"/>
        <line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><line x1="10" y1="9" x2="8" y2="9"/>
      </svg>
    ),
    profile: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>
      </svg>
    ),
    income: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="2" y="7" width="20" height="14" rx="2" ry="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/>
      </svg>
    ),
    assets: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>
      </svg>
    ),
    home: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9,22 9,12 15,12 15,22"/>
      </svg>
    ),
    review: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22,4 12,14.01 9,11.01"/>
      </svg>
    ),
    goals: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>
      </svg>
    ),
    calendar: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>
      </svg>
    ),
    check: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="20,6 9,17 4,12"/>
      </svg>
    ),
    user: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>
      </svg>
    ),
    users: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>
      </svg>
    ),
    family: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="9" cy="7" r="3"/><circle cx="17" cy="7" r="2"/><path d="M13 21v-4a4 4 0 0 0-8 0v4"/><path d="M21 21v-3a3 3 0 0 0-4-2.83"/>
      </svg>
    ),
    star: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polygon points="12,2 15.09,8.26 22,9.27 17,14.14 18.18,21.02 12,17.77 5.82,21.02 7,14.14 2,9.27 8.91,8.26"/>
      </svg>
    ),
    celebration: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 2v4m-6 2L4 6m16 2 2-2M4 16l-2 2m18-2 2 2"/><circle cx="12" cy="12" r="6"/>
      </svg>
    ),
    heart: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
      </svg>
    ),
    document: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14,2 14,8 20,8"/>
      </svg>
    ),
    medal: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="14" r="6"/><path d="M9 6.8V2h6v4.8M12 2v6"/><path d="M15.5 8 18 2M8.5 8 6 2"/>
      </svg>
    ),
    shield: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
      </svg>
    ),
    briefcase: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="2" y="7" width="20" height="14" rx="2" ry="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/>
      </svg>
    ),
    building: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="4" y="2" width="16" height="20" rx="2" ry="2"/><line x1="9" y1="6" x2="9" y2="6"/><line x1="15" y1="6" x2="15" y2="6"/><line x1="9" y1="10" x2="9" y2="10"/><line x1="15" y1="10" x2="15" y2="10"/><line x1="9" y1="14" x2="9" y2="14"/><line x1="15" y1="14" x2="15" y2="14"/><path d="M9 22V18h6v4"/>
      </svg>
    ),
    tie: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 2l3 4-3 2-3-2 3-4z"/><path d="M9 8l-2 14 5-4 5 4-2-14"/>
      </svg>
    ),
    trendDown: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="23,18 13.5,8.5 8.5,13.5 1,6"/><polyline points="17,18 23,18 23,12"/>
      </svg>
    ),
    balance: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 3v18"/><path d="M5 6l7-3 7 3"/><path d="M2 12l3-6 3 6"/><path d="M16 12l3-6 3 6"/><path d="M2 12a3 3 0 0 0 6 0M16 12a3 3 0 0 0 6 0"/>
      </svg>
    ),
    trendUp: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="23,6 13.5,15.5 8.5,10.5 1,18"/><polyline points="17,6 23,6 23,12"/>
      </svg>
    ),
    alertTriangle: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
      </svg>
    ),
    clipboard: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><rect x="8" y="2" width="8" height="4" rx="1" ry="1"/>
      </svg>
    ),
    creditCard: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="1" y="4" width="22" height="16" rx="2" ry="2"/><line x1="1" y1="10" x2="23" y2="10"/>
      </svg>
    ),
    gift: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="20,12 20,22 4,22 4,12"/><rect x="2" y="7" width="20" height="5"/><line x1="12" y1="22" x2="12" y2="7"/><path d="M12 7H7.5a2.5 2.5 0 0 1 0-5C11 2 12 7 12 7z"/><path d="M12 7h4.5a2.5 2.5 0 0 0 0-5C13 2 12 7 12 7z"/>
      </svg>
    ),
    helpCircle: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/>
      </svg>
    ),
    dollarSign: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>
      </svg>
    ),
    search: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
      </svg>
    ),
    arrowRight: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <line x1="5" y1="12" x2="19" y2="12"/><polyline points="12,5 19,12 12,19"/>
      </svg>
    ),
    edit: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
      </svg>
    ),
    thumbsUp: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/>
      </svg>
    ),
    barChart: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <line x1="12" y1="20" x2="12" y2="10"/><line x1="18" y1="20" x2="18" y2="4"/><line x1="6" y1="20" x2="6" y2="16"/>
      </svg>
    ),
    beach: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="8" r="5"/><path d="M3 21h18"/><path d="M12 13v8"/>
      </svg>
    ),
    award: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="8" r="7"/><polyline points="8.21,13.89 7,23 12,20 17,23 15.79,13.88"/>
      </svg>
    ),
    bank: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 21h18"/><path d="M3 10h18"/><path d="M5 6l7-3 7 3"/><path d="M4 10v11"/><path d="M20 10v11"/><path d="M8 14v3"/><path d="M12 14v3"/><path d="M16 14v3"/>
      </svg>
    ),
    lock: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>
      </svg>
    ),
    refresh: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="23,4 23,10 17,10"/><polyline points="1,20 1,14 7,14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
      </svg>
    ),
    target: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>
      </svg>
    ),
    bolt: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polygon points="13,2 3,14 12,14 11,22 21,10 12,10"/>
      </svg>
    ),
    homeEquity: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M12 11v4"/><path d="M9 13h6"/>
      </svg>
    ),
    predictable: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <line x1="12" y1="20" x2="12" y2="10"/><line x1="18" y1="20" x2="18" y2="10"/><line x1="6" y1="20" x2="6" y2="10"/>
      </svg>
    ),
    netWorth: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/>
      </svg>
    ),
    largerHome: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M15 3l4 3"/><path d="M19 6v3"/>
      </svg>
    ),
    freedom: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M18 8h1a4 4 0 0 1 0 8h-1"/><path d="M2 8h16v9a4 4 0 0 1-4 4H6a4 4 0 0 1-4-4V8z"/><line x1="6" y1="1" x2="6" y2="4"/><line x1="10" y1="1" x2="10" y2="4"/><line x1="14" y1="1" x2="14" y2="4"/>
      </svg>
    ),
    scissors: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><line x1="20" y1="4" x2="8.12" y2="15.88"/><line x1="14.47" y1="14.48" x2="20" y2="20"/><line x1="8.12" y1="8.12" x2="12" y2="12"/>
      </svg>
    ),
    retirement: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9Z"/>
      </svg>
    ),
    graduation: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M22 10v6M2 10l10-5 10 5-10 5z"/><path d="M6 12v5c0 2 2 3 6 3s6-1 6-3v-5"/>
      </svg>
    ),
    rocket: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z"/><path d="M12 15l-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z"/><path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0"/><path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5"/>
      </svg>
    ),
    calculator: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="4" y="2" width="16" height="20" rx="2"/><line x1="8" y1="6" x2="16" y2="6"/><line x1="8" y1="10" x2="8" y2="10"/><line x1="12" y1="10" x2="12" y2="10"/><line x1="16" y1="10" x2="16" y2="10"/><line x1="8" y1="14" x2="8" y2="14"/><line x1="12" y1="14" x2="12" y2="14"/><line x1="16" y1="14" x2="16" y2="14"/><line x1="8" y1="18" x2="8" y2="18"/><line x1="12" y1="18" x2="12" y2="18"/><line x1="16" y1="18" x2="16" y2="18"/>
      </svg>
    ),
    fileText: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14,2 14,8 20,8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>
      </svg>
    ),
    clock: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10"/><polyline points="12,6 12,12 16,14"/>
      </svg>
    ),
    mapPin: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/>
      </svg>
    ),
    x: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
      </svg>
    ),
    info: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>
      </svg>
    ),
    play: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polygon points="5,3 19,12 5,21"/>
      </svg>
    ),
    car: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M19 17h2c.6 0 1-.4 1-1v-3c0-.9-.7-1.7-1.5-1.9C18.7 10.6 16 10 16 10s-1.3-1.4-2.2-2.3c-.5-.4-1.1-.7-1.8-.7H5c-.6 0-1.1.4-1.4.9l-1.4 2.9A3.7 3.7 0 0 0 2 12v4c0 .6.4 1 1 1h2"/>
        <circle cx="7" cy="17" r="2"/><circle cx="17" cy="17" r="2"/>
      </svg>
    ),
    search: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
      </svg>
    ),
    refresh: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>
      </svg>
    ),
  };

  return (
    <span className={`icon ${className}`} style={{ width: size, height: size, display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
      {icons[name] || icons.document}
    </span>
  );
};

// Purchase-specific declaration questions
const DECLARATION_QUESTIONS = [
  {
    id: 'borrower_count',
    question: 'How many people will be on this loan application?',
    type: 'choice',
    options: [
      { value: '1', label: 'Just me', icon: 'user' },
      { value: '2', label: 'Two of us', icon: 'users' },
      { value: '3', label: 'Three people', icon: 'family' },
      { value: '4+', label: 'Four or more', icon: 'family' },
    ],
    hint: 'This helps us know how many borrowers to include in the application.',
  },
  {
    id: 'co_borrower_relationship',
    question: 'What is your relationship to the other borrower(s)?',
    type: 'choice',
    options: [
      { value: 'spouse', label: 'Spouse/Partner', icon: 'heart' },
      { value: 'relative', label: 'Family member', icon: 'family' },
      { value: 'friend', label: 'Friend/Non-relative', icon: 'users' },
      { value: 'business_partner', label: 'Business partner', icon: 'briefcase' },
    ],
    hint: 'This helps us understand the borrower structure.',
    showIf: { field: 'borrower_count', values: ['2', '3', '4+'] },
  },
  {
    id: 'co_borrower_first_name',
    question: 'What is the co-borrower\'s first name?',
    type: 'text',
    placeholder: 'First name',
    hint: 'We\'ll need their information for the application.',
    showIf: { field: 'borrower_count', values: ['2', '3', '4+'] },
  },
  {
    id: 'co_borrower_last_name',
    question: 'What is the co-borrower\'s last name?',
    type: 'text',
    placeholder: 'Last name',
    showIf: { field: 'borrower_count', values: ['2', '3', '4+'] },
  },
  {
    id: 'co_borrower_email',
    question: 'What is the co-borrower\'s email address?',
    type: 'email',
    placeholder: 'email@example.com',
    hint: 'They\'ll receive updates about the application.',
    showIf: { field: 'borrower_count', values: ['2', '3', '4+'] },
  },
  {
    id: 'co_borrower_phone',
    question: 'What is the co-borrower\'s phone number?',
    type: 'phone',
    placeholder: '(555) 555-5555',
    showIf: { field: 'borrower_count', values: ['2', '3', '4+'] },
  },
  {
    id: 'first_time_buyer',
    question: 'Is this your first home purchase?',
    type: 'choice',
    options: [
      { value: 'yes', label: 'Yes, first-time buyer!', icon: 'celebration' },
      { value: 'no', label: 'No, I\'ve bought before', icon: 'home' },
    ],
    hint: 'First-time buyers may qualify for special programs!',
  },
  {
    id: 'previous_home_status',
    question: 'What happened to your previous home?',
    type: 'choice',
    options: [
      { value: 'sold', label: 'Sold it', icon: 'check' },
      { value: 'still_own', label: 'Still own it', icon: 'home' },
      { value: 'renting_out', label: 'Renting it out', icon: 'dollarSign' },
      { value: 'foreclosure', label: 'Lost to foreclosure/short sale', icon: 'alertTriangle' },
    ],
    hint: 'This affects your loan options and what we need to document.',
    showIf: { field: 'first_time_buyer', values: ['no'] },
  },
  {
    id: 'foreclosure_timeline',
    question: 'When did the foreclosure or short sale occur?',
    type: 'choice',
    options: [
      { value: 'less_than_2_years', label: 'Less than 2 years ago', icon: 'clock' },
      { value: '2_to_4_years', label: '2-4 years ago', icon: 'clock' },
      { value: '4_to_7_years', label: '4-7 years ago', icon: 'calendar' },
      { value: 'more_than_7_years', label: 'More than 7 years ago', icon: 'calendar' },
    ],
    hint: 'Different loan programs have different waiting periods after foreclosure.',
    showIf: { field: 'previous_home_status', values: ['foreclosure'] },
  },
  {
    id: 'rental_income_previous',
    question: 'How much rental income do you receive monthly from the property?',
    type: 'currency',
    placeholder: 'Monthly rental income',
    hint: 'This rental income can help qualify you for more home.',
    showIf: { field: 'previous_home_status', values: ['renting_out'] },
  },
  {
    id: 'marital_status',
    question: 'Are you married?',
    type: 'choice',
    options: [
      { value: 'married', label: 'Yes, married', icon: 'heart' },
      { value: 'single', label: 'Single', icon: 'user' },
      { value: 'divorced', label: 'Divorced', icon: 'document' },
      { value: 'separated', label: 'Separated', icon: 'users' },
      { value: 'widowed', label: 'Widowed', icon: 'heart' },
    ],
    unlocks: ['spouse_section'],
    hideIf: { field: 'co_borrower_relationship', values: ['spouse'] }, // Skip if already indicated spouse/partner
  },
  {
    id: 'spouse_on_loan',
    question: 'Will your spouse be on the loan application?',
    type: 'choice',
    options: [
      { value: 'yes', label: 'Yes, both of us', icon: 'users' },
      { value: 'no', label: 'No, just me', icon: 'user' },
    ],
    hint: 'In community property states, spouse income/debts may still be considered.',
    showIf: { field: 'marital_status', values: ['married'] },
  },
  {
    id: 'divorce_finalized',
    question: 'Is your divorce finalized?',
    type: 'choice',
    options: [
      { value: 'yes', label: 'Yes, finalized', icon: 'check' },
      { value: 'pending', label: 'Still pending', icon: 'clock' },
    ],
    hint: 'A pending divorce may require additional documentation.',
    showIf: { field: 'marital_status', values: ['divorced', 'separated'] },
  },
  {
    id: 'child_support_alimony',
    question: 'Do you receive or pay child support or alimony?',
    type: 'choice',
    options: [
      { value: 'receive', label: 'I receive payments', icon: 'dollarSign' },
      { value: 'pay', label: 'I make payments', icon: 'creditCard' },
      { value: 'both', label: 'Both receive and pay', icon: 'refresh' },
      { value: 'neither', label: 'Neither', icon: 'arrowRight' },
    ],
    hint: 'This income/expense will be considered in your loan qualification.',
    showIf: { field: 'marital_status', values: ['divorced', 'separated'] },
  },
  {
    id: 'support_amount_received',
    question: 'How much do you receive per month in child support/alimony?',
    type: 'currency',
    placeholder: 'Monthly amount received',
    hint: 'This can count as qualifying income if documented.',
    showIf: { field: 'child_support_alimony', values: ['receive', 'both'] },
  },
  {
    id: 'support_duration_received',
    question: 'How long have you been receiving this income?',
    type: 'choice',
    options: [
      { value: 'less_than_6_months', label: 'Less than 6 months', icon: 'clock' },
      { value: '6_to_12_months', label: '6-12 months', icon: 'clock' },
      { value: '1_to_3_years', label: '1-3 years', icon: 'calendar' },
      { value: 'more_than_3_years', label: 'More than 3 years', icon: 'calendar' },
    ],
    hint: 'Income must typically continue for at least 3 more years to count.',
    showIf: { field: 'child_support_alimony', values: ['receive', 'both'] },
  },
  {
    id: 'support_amount_paid',
    question: 'How much do you pay per month in child support/alimony?',
    type: 'currency',
    placeholder: 'Monthly amount paid',
    hint: 'This will be factored into your debt-to-income ratio.',
    showIf: { field: 'child_support_alimony', values: ['pay', 'both'] },
  },
  {
    id: 'support_type_paid',
    question: 'What type of payments are you making?',
    type: 'choice',
    options: [
      { value: 'child_support', label: 'Child Support only', icon: 'family' },
      { value: 'alimony', label: 'Alimony/Spousal Support only', icon: 'heart' },
      { value: 'both', label: 'Both Child Support and Alimony', icon: 'users' },
    ],
    hint: 'Different payment types may have different documentation requirements.',
    showIf: { field: 'child_support_alimony', values: ['pay', 'both'] },
  },
  {
    id: 'support_duration_paid',
    question: 'How long will you continue making these payments?',
    type: 'choice',
    options: [
      { value: 'less_than_1_year', label: 'Less than 1 year', icon: 'clock' },
      { value: '1_to_3_years', label: '1-3 years', icon: 'calendar' },
      { value: '3_to_5_years', label: '3-5 years', icon: 'calendar' },
      { value: 'more_than_5_years', label: 'More than 5 years', icon: 'calendar' },
      { value: 'until_child_18', label: 'Until child turns 18', icon: 'family' },
    ],
    hint: 'Payments ending within 10 months may not be counted against you.',
    showIf: { field: 'child_support_alimony', values: ['pay', 'both'] },
  },
  {
    id: 'support_type_received',
    question: 'What type of payments are you receiving?',
    type: 'choice',
    options: [
      { value: 'child_support', label: 'Child Support only', icon: 'family' },
      { value: 'alimony', label: 'Alimony/Spousal Support only', icon: 'heart' },
      { value: 'both', label: 'Both Child Support and Alimony', icon: 'users' },
    ],
    hint: 'Different payment types may count differently as qualifying income.',
    showIf: { field: 'child_support_alimony', values: ['receive', 'both'] },
  },
  {
    id: 'support_years_remaining',
    question: 'How many more years will you receive these payments?',
    type: 'choice',
    options: [
      { value: 'less_than_3_years', label: 'Less than 3 years', icon: 'clock' },
      { value: '3_to_5_years', label: '3-5 years', icon: 'calendar' },
      { value: '5_to_10_years', label: '5-10 years', icon: 'calendar' },
      { value: 'more_than_10_years', label: 'More than 10 years', icon: 'calendar' },
    ],
    hint: 'Income must typically continue for at least 3 more years to count.',
    showIf: { field: 'child_support_alimony', values: ['receive', 'both'] },
  },
  {
    id: 'property_interest',
    question: 'Do you have interest in any other real estate property?',
    type: 'choice',
    options: [
      { value: 'yes', label: 'Yes, I own property', icon: 'home' },
      { value: 'no', label: 'No other properties', icon: 'arrowRight' },
    ],
    hint: 'This includes properties you own, co-own, or have ownership interest in.',
  },
  {
    id: 'property_interest_address',
    question: 'What is the address of the property you have interest in?',
    type: 'address',
    placeholder: 'Enter property address',
    hint: 'We\'ll need details about this property for your application.',
    showIf: { field: 'property_interest', values: ['yes'] },
  },
  {
    id: 'veteran',
    question: 'Have you or your spouse served in the military?',
    type: 'choice',
    options: [
      { value: 'yes', label: 'Yes, I\'m a Veteran', icon: 'medal' },
      { value: 'active', label: 'Currently Active Duty', icon: 'star' },
      { value: 'spouse', label: 'My spouse served', icon: 'heart' },
      { value: 'no', label: 'No military service', icon: 'arrowRight' },
    ],
    hint: 'Veterans can get VA loans with $0 down!',
  },
  {
    id: 'va_loan_before',
    question: 'Have you used a VA loan before?',
    type: 'choice',
    options: [
      { value: 'yes_paid_off', label: 'Yes, paid it off', icon: 'check' },
      { value: 'yes_still_have', label: 'Yes, still have it', icon: 'home' },
      { value: 'no', label: 'No, first VA loan', icon: 'star' },
    ],
    hint: 'You can use your VA benefit multiple times!',
    showIf: { field: 'veteran', values: ['yes', 'active', 'spouse'] },
  },
  {
    id: 'va_disability',
    question: 'Do you have a VA disability rating?',
    type: 'choice',
    options: [
      { value: 'yes_10_plus', label: 'Yes, 10% or higher', icon: 'shield' },
      { value: 'pending', label: 'Claim pending', icon: 'clock' },
      { value: 'no', label: 'No disability rating', icon: 'arrowRight' },
    ],
    hint: '10%+ disability rating waives the VA funding fee - saves thousands!',
    showIf: { field: 'veteran', values: ['yes', 'active'] },
  },
  {
    id: 'self_employed',
    question: 'Are you self-employed or own a business?',
    type: 'choice',
    options: [
      { value: 'yes', label: 'Yes, self-employed', icon: 'building' },
      { value: 'side_business', label: 'I have a side business', icon: 'briefcase' },
      { value: 'no', label: 'No, I\'m an employee', icon: 'tie' },
    ],
    hint: 'This helps us know what income documents you\'ll need.',
  },
  {
    id: 'business_years',
    question: 'How long have you been self-employed?',
    type: 'choice',
    options: [
      { value: 'less_than_1_year', label: 'Less than 1 year', icon: 'clock' },
      { value: '1_to_2_years', label: '1-2 years', icon: 'calendar' },
      { value: 'more_than_2_years', label: 'More than 2 years', icon: 'check' },
    ],
    hint: 'Most loan programs require 2 years of self-employment history.',
    showIf: { field: 'self_employed', values: ['yes'] },
  },
  {
    id: 'business_type',
    question: 'What type of business do you have?',
    type: 'choice',
    options: [
      { value: 'sole_proprietor', label: 'Sole proprietor', icon: 'user' },
      { value: 'llc', label: 'LLC', icon: 'building' },
      { value: 's_corp', label: 'S-Corp', icon: 'briefcase' },
      { value: 'partnership', label: 'Partnership', icon: 'users' },
    ],
    hint: 'This determines what tax documents we\'ll need.',
    showIf: { field: 'self_employed', values: ['yes', 'side_business'] },
  },
  {
    id: 'write_off_expenses',
    question: 'Do you write off most expenses to minimize taxable income?',
    type: 'choice',
    options: [
      { value: 'yes', label: 'Yes, I maximize deductions', icon: 'trendDown' },
      { value: 'some', label: 'Some, but I show decent income', icon: 'balance' },
      { value: 'no', label: 'No, I show most of my income', icon: 'trendUp' },
    ],
    hint: 'Self-employed income is based on your adjusted gross income after expenses. If you write off heavily, we may need 12 months of business bank statements.',
    showIf: { field: 'self_employed', values: ['yes', 'side_business'] },
  },
  {
    id: 'irs_balance_owed',
    question: 'Do you have an outstanding balance owed to the IRS?',
    type: 'choice',
    options: [
      { value: 'yes', label: 'Yes, I owe the IRS', icon: 'alertTriangle' },
      { value: 'payment_plan', label: 'Yes, but on a payment plan', icon: 'clipboard' },
      { value: 'no', label: 'No outstanding balance', icon: 'check' },
    ],
    hint: 'Having a balance doesn\'t disqualify you - we just need to know.',
  },
  {
    id: 'irs_amount_owed',
    question: 'Approximately how much do you owe the IRS?',
    type: 'currency',
    placeholder: 'Amount owed',
    hint: 'This helps us understand your full financial picture.',
    showIf: { field: 'irs_balance_owed', values: ['yes', 'payment_plan'] },
  },
  {
    id: 'irs_payment_current',
    question: 'Are you current on your IRS payment plan?',
    type: 'choice',
    options: [
      { value: 'yes', label: 'Yes, fully current', icon: 'check' },
      { value: 'behind', label: 'Behind on payments', icon: 'alertTriangle' },
    ],
    hint: 'Being current on payments is usually required for loan approval.',
    showIf: { field: 'irs_balance_owed', values: ['payment_plan'] },
  },
  {
    id: 'recent_credit_applications',
    question: 'Have you applied for any credit in the past 3 months?',
    type: 'choice',
    options: [
      { value: 'yes', label: 'Yes, I applied recently', icon: 'creditCard' },
      { value: 'no', label: 'No recent applications', icon: 'check' },
    ],
    hint: 'Car loans, credit cards, personal loans, etc. Recent inquiries can affect your score.',
  },
  {
    id: 'credit_application_type',
    question: 'What type of credit did you apply for?',
    type: 'choice',
    options: [
      { value: 'auto_loan', label: 'Auto loan', icon: 'car' },
      { value: 'credit_card', label: 'Credit card', icon: 'creditCard' },
      { value: 'personal_loan', label: 'Personal loan', icon: 'dollarSign' },
      { value: 'other', label: 'Other', icon: 'document' },
    ],
    hint: 'Recent auto loans can significantly impact your debt-to-income ratio.',
    showIf: { field: 'recent_credit_applications', values: ['yes'] },
  },
  {
    id: 'credit_application_approved',
    question: 'Was the credit application approved?',
    type: 'choice',
    options: [
      { value: 'yes', label: 'Yes, approved', icon: 'check' },
      { value: 'pending', label: 'Still pending', icon: 'clock' },
      { value: 'no', label: 'No, denied', icon: 'x' },
    ],
    hint: 'If approved, we\'ll need to factor in the new payment.',
    showIf: { field: 'recent_credit_applications', values: ['yes'] },
  },
  {
    id: 'gift_funds',
    question: 'Will you use gift funds for your down payment?',
    type: 'choice',
    options: [
      { value: 'yes', label: 'Yes, receiving a gift', icon: 'gift' },
      { value: 'maybe', label: 'Maybe, not sure yet', icon: 'helpCircle' },
      { value: 'no', label: 'No, using my own funds', icon: 'dollarSign' },
    ],
    hint: 'Gift funds from family are totally okay!',
  },
  {
    id: 'gift_amount',
    question: 'How much gift money will you receive?',
    type: 'currency',
    placeholder: 'Gift amount',
    hint: 'We\'ll need a gift letter from the donor.',
    showIf: { field: 'gift_funds', values: ['yes'] },
  },
  {
    id: 'gift_donor',
    question: 'Who is providing the gift?',
    type: 'choice',
    options: [
      { value: 'parent', label: 'Parent', icon: 'family' },
      { value: 'grandparent', label: 'Grandparent', icon: 'family' },
      { value: 'sibling', label: 'Sibling', icon: 'users' },
      { value: 'other_relative', label: 'Other relative', icon: 'users' },
      { value: 'non_relative', label: 'Non-relative', icon: 'user' },
    ],
    hint: 'Gift rules vary based on relationship and loan type.',
    showIf: { field: 'gift_funds', values: ['yes'] },
  },
  {
    id: 'found_property',
    question: 'Have you found a property yet?',
    type: 'choice',
    options: [
      { value: 'yes', label: 'Yes, under contract', icon: 'document' },
      { value: 'looking', label: 'Still shopping', icon: 'search' },
      { value: 'pre_approval', label: 'Just getting pre-approved', icon: 'check' },
    ],
  },
  {
    id: 'closing_date',
    question: 'When is your target closing date?',
    type: 'choice',
    options: [
      { value: 'less_than_30', label: 'Less than 30 days', icon: 'clock' },
      { value: '30_to_45', label: '30-45 days', icon: 'calendar' },
      { value: '45_to_60', label: '45-60 days', icon: 'calendar' },
      { value: 'more_than_60', label: 'More than 60 days', icon: 'calendar' },
    ],
    hint: 'Knowing your timeline helps us prioritize appropriately.',
    showIf: { field: 'found_property', values: ['yes'] },
  },
  {
    id: 'working_with_agent',
    question: 'Are you working with a real estate agent?',
    type: 'choice',
    options: [
      { value: 'yes', label: 'Yes, have an agent', icon: 'users' },
      { value: 'no', label: 'Not yet', icon: 'search' },
    ],
    hint: 'We can recommend great agents in your area if needed.',
  },
  {
    id: 'agent_name',
    question: 'What is your real estate agent\'s name?',
    type: 'text',
    placeholder: 'Agent\'s full name',
    hint: 'We\'ll coordinate with your agent throughout the process.',
    showIf: { field: 'working_with_agent', values: ['yes'] },
  },
  {
    id: 'agent_phone',
    question: 'What is your agent\'s phone number?',
    type: 'phone',
    placeholder: '(555) 555-5555',
    showIf: { field: 'working_with_agent', values: ['yes'] },
  },
  {
    id: 'agent_email',
    question: 'What is your agent\'s email address?',
    type: 'email',
    placeholder: 'agent@example.com',
    hint: 'We\'ll send them updates on your loan progress.',
    showIf: { field: 'working_with_agent', values: ['yes'] },
  },
  {
    id: 'credit_issues',
    question: 'Have you had any credit challenges in the past 2 years?',
    type: 'choice',
    options: [
      { value: 'none', label: 'No issues', icon: 'check' },
      { value: 'late_payments', label: 'Late payments', icon: 'clock' },
      { value: 'collections', label: 'Collections/charge-offs', icon: 'alertTriangle' },
      { value: 'bankruptcy', label: 'Bankruptcy', icon: 'document' },
    ],
    hint: 'Being upfront helps us find the right program for you.',
  },
  {
    id: 'bankruptcy_type',
    question: 'What type of bankruptcy did you file?',
    type: 'choice',
    options: [
      { value: 'chapter_7', label: 'Chapter 7', icon: 'document' },
      { value: 'chapter_13', label: 'Chapter 13', icon: 'document' },
    ],
    hint: 'Different waiting periods apply for each type.',
    showIf: { field: 'credit_issues', values: ['bankruptcy'] },
  },
  {
    id: 'bankruptcy_discharge',
    question: 'When was your bankruptcy discharged?',
    type: 'choice',
    options: [
      { value: 'less_than_2_years', label: 'Less than 2 years ago', icon: 'clock' },
      { value: '2_to_4_years', label: '2-4 years ago', icon: 'calendar' },
      { value: 'more_than_4_years', label: 'More than 4 years ago', icon: 'calendar' },
    ],
    hint: 'Most loan programs require at least 2-4 years since discharge.',
    showIf: { field: 'credit_issues', values: ['bankruptcy'] },
  },
];

// Common employers for autocomplete
const COMMON_EMPLOYERS = [
  'CMG Home Loans', 'CMG Financial', 'Wells Fargo', 'Bank of America', 'JPMorgan Chase',
  'Citibank', 'US Bank', 'PNC Bank', 'Capital One', 'TD Bank',
  'Amazon', 'Apple', 'Google', 'Microsoft', 'Meta', 'Netflix', 'Tesla',
  'Walmart', 'Target', 'Costco', 'Home Depot', 'Lowes',
  'UnitedHealth Group', 'CVS Health', 'Cigna', 'Anthem', 'Kaiser Permanente',
  'AT&T', 'Verizon', 'T-Mobile', 'Comcast', 'Charter Communications',
  'FedEx', 'UPS', 'USPS', 'DHL',
  'Boeing', 'Lockheed Martin', 'Raytheon', 'Northrop Grumman',
  'General Motors', 'Ford', 'Toyota', 'Honda', 'BMW',
  'Starbucks', 'McDonalds', 'Chipotle', 'Subway',
  'United Airlines', 'Delta Airlines', 'American Airlines', 'Southwest Airlines',
  'Marriott', 'Hilton', 'Hyatt',
  'Disney', 'Warner Bros', 'NBC Universal', 'Paramount',
  'Deloitte', 'PwC', 'EY', 'KPMG', 'Accenture', 'McKinsey',
  'IBM', 'Oracle', 'Salesforce', 'Adobe', 'SAP', 'Intuit',
  'Johnson & Johnson', 'Pfizer', 'Merck', 'Abbott', 'AbbVie',
];

// Planning questions - mortgage priorities and goals (excludes questions already asked in declarations)
const PLANNING_QUESTIONS = {
  mortgagePriorities: {
    question: 'What matters most to you in your mortgage?',
    hint: 'Select all that apply - this helps us find the best loan structure for you.',
    options: [
      { value: 'lowest_payment', label: 'Lowest Monthly Payment', icon: 'dollarSign' },
      { value: 'lowest_rate', label: 'Lowest Interest Rate', icon: 'trendDown' },
      { value: 'fastest_payoff', label: 'Pay Off Fastest', icon: 'bolt' },
      { value: 'lowest_total', label: 'Lowest Total Cost', icon: 'target' },
      { value: 'flexibility', label: 'Maximum Flexibility', icon: 'refresh' },
      { value: 'tax_benefits', label: 'Tax Benefits', icon: 'clipboard' },
      { value: 'build_equity', label: 'Build Equity Faster', icon: 'homeEquity' },
      { value: 'predictable', label: 'Predictable Payments', icon: 'predictable' },
    ],
  },
  personalGoals: {
    question: 'What are your personal financial goals?',
    hint: 'Select all that apply - helps us align your mortgage with your life plans.',
    options: [
      { value: 'net_worth', label: 'Building Net Worth', icon: 'netWorth' },
      { value: 'larger_home', label: 'Moving to Larger Home', icon: 'largerHome' },
      { value: 'financial_freedom', label: 'Financial Freedom', icon: 'freedom' },
      { value: 'pay_debt', label: 'Paying Off Debt', icon: 'scissors' },
      { value: 'retirement', label: 'Saving for Retirement', icon: 'retirement' },
      { value: 'education', label: 'Children\'s Education', icon: 'graduation' },
      { value: 'investments', label: 'Investment Portfolio', icon: 'barChart' },
      { value: 'business', label: 'Starting a Business', icon: 'rocket' },
    ],
  },
  financialPhilosophy: {
    question: 'How would you describe your financial approach?',
    options: [
      { value: 'conservative', label: 'Conservative', icon: 'shield', description: 'Prefer stability and lower risk' },
      { value: 'moderate', label: 'Moderate', icon: 'balance', description: 'Balance between safety and growth' },
      { value: 'aggressive', label: 'Aggressive', icon: 'rocket', description: 'Willing to take risks for higher returns' },
    ],
  },
  professionalNetwork: {
    question: 'Do you currently work with any of these professionals?',
    hint: 'We can coordinate with your existing team for a comprehensive financial plan.',
    options: [
      { value: 'financial_planner', label: 'Financial Planner', icon: 'trendUp' },
      { value: 'accountant', label: 'CPA / Accountant', icon: 'calculator' },
      { value: 'insurance_agent', label: 'Life Insurance Agent', icon: 'shield' },
      { value: 'estate_planner', label: 'Estate Planner', icon: 'fileText' },
    ],
  },
  taxDeferredRetirement: {
    question: 'Are you currently contributing to a tax-deferred retirement account?',
    hint: '401(k), IRA, or similar retirement savings',
    options: [
      { value: 'yes', label: 'Yes, I contribute regularly', icon: 'check' },
      { value: 'some', label: 'Sometimes / Not maxing out', icon: 'refresh' },
      { value: 'no', label: 'Not currently', icon: 'x' },
      { value: 'not_sure', label: 'Not sure', icon: 'helpCircle' },
    ],
  },
};

export default function PurchaseApplication() {
  const { token } = useParams();
  const navigate = useNavigate();
  const isDemoMode = !token || token === 'start';

  // State
  const [currentStage, setCurrentStage] = useState('declarations');
  const [currentQuestionIndex, setCurrentQuestionIndex] = useState(0);
  const [declarations, setDeclarations] = useState({});
  const [profileData, setProfileData] = useState({});
  const [incomeData, setIncomeData] = useState({});
  const [incomeStep, setIncomeStep] = useState(1); // 1 = type selection, 2 = details
  const [propertyStep, setPropertyStep] = useState(1); // 1 = type/occupancy, 2 = price/down, 3 = loan program
  const [assetData, setAssetData] = useState({});
  const [propertyData, setPropertyData] = useState({});
  const [planningData, setPlanningData] = useState({
    mortgagePriorities: [],
    personalGoals: [],
    financialPhilosophy: '',
    professionalNetwork: [],
    taxDeferredRetirement: '',
  });
  const [needsList, setNeedsList] = useState([]);
  const [showMicroWin, setShowMicroWin] = useState(false);
  const [microWinMessage, setMicroWinMessage] = useState('');
  const [isAnimating, setIsAnimating] = useState(false);
  const [selectedTimeSlot, setSelectedTimeSlot] = useState(null);
  const [scheduleStep, setScheduleStep] = useState(1); // 1 = calendar, 2 = video/next steps
  const [planningStep, setPlanningStep] = useState(1); // 1-5 for each planning question
  const [employerSuggestions, setEmployerSuggestions] = useState([]);
  const [showEmployerDropdown, setShowEmployerDropdown] = useState(false);

  // Filter employers
  const filterEmployers = (input) => {
    if (!input || input.length < 2) {
      setEmployerSuggestions([]);
      setShowEmployerDropdown(false);
      return;
    }
    const filtered = COMMON_EMPLOYERS.filter(emp =>
      emp.toLowerCase().includes(input.toLowerCase())
    ).slice(0, 8);
    setEmployerSuggestions(filtered);
    setShowEmployerDropdown(filtered.length > 0);
  };

  // Calculate progress
  const getProgress = useCallback(() => {
    const stageIndex = STAGES.findIndex(s => s.id === currentStage);
    const stageProgress = (stageIndex / STAGES.length) * 100;
    if (currentStage === 'declarations') {
      const questionProgress = (currentQuestionIndex / DECLARATION_QUESTIONS.length) * (100 / STAGES.length);
      return Math.round(stageProgress + questionProgress);
    }
    return Math.round(stageProgress);
  }, [currentStage, currentQuestionIndex]);

  // Helper to check if a question should be shown based on conditions
  const shouldShowQuestion = useCallback((question, currentDeclarations) => {
    // Check hideIf condition first - if matches, hide the question
    if (question.hideIf) {
      const { field, values } = question.hideIf;
      if (values.includes(currentDeclarations[field])) {
        return false;
      }
    }
    // Then check showIf condition
    if (!question.showIf) return true;
    const { field, values } = question.showIf;
    return values.includes(currentDeclarations[field]);
  }, []);

  // Get filtered questions based on current declarations
  const getVisibleQuestions = useCallback(() => {
    return DECLARATION_QUESTIONS.filter(q => shouldShowQuestion(q, declarations));
  }, [declarations, shouldShowQuestion]);

  // Update needs list
  useEffect(() => {
    const newNeeds = [];
    newNeeds.push({ id: 'id', label: 'Government-issued ID', category: 'identity' });

    if (declarations.self_employed === 'yes' || declarations.self_employed === 'side_business') {
      newNeeds.push({ id: 'tax_returns', label: '2 years tax returns', category: 'income' });
      newNeeds.push({ id: 'profit_loss', label: 'Year-to-date P&L statement', category: 'income' });

      // If they write off heavily, need 12 months business bank statements
      if (declarations.write_off_expenses === 'yes') {
        newNeeds.push({ id: 'business_bank_statements', label: '12 months business bank statements', category: 'income' });
      }
    } else {
      newNeeds.push({ id: 'paystubs', label: 'Recent pay stubs (30 days)', category: 'income' });
      newNeeds.push({ id: 'w2', label: 'W-2s (last 2 years)', category: 'income' });
    }

    if (declarations.gift_funds === 'yes') {
      newNeeds.push({ id: 'gift_letter', label: 'Gift letter from donor', category: 'assets' });
      newNeeds.push({ id: 'gift_source', label: 'Donor bank statements', category: 'assets' });
    }

    if (declarations.veteran && declarations.veteran !== 'no') {
      newNeeds.push({ id: 'dd214', label: 'DD-214 or Certificate of Eligibility', category: 'military' });
    }

    // IRS payment plan documentation
    if (declarations.irs_balance_owed === 'yes' || declarations.irs_balance_owed === 'payment_plan') {
      newNeeds.push({ id: 'irs_docs', label: 'IRS payment arrangement documentation', category: 'legal' });
    }

    newNeeds.push({ id: 'bank_statements', label: 'Bank statements (2 months)', category: 'assets' });

    if (declarations.found_property === 'yes') {
      newNeeds.push({ id: 'purchase_contract', label: 'Purchase contract', category: 'property' });
    }

    setNeedsList(newNeeds);
  }, [declarations]);

  // Micro-win animation
  const showMicroWinAnimation = (message) => {
    setMicroWinMessage(message);
    setShowMicroWin(true);
    setTimeout(() => setShowMicroWin(false), 2500);
  };

  // Handle declaration answer
  const handleDeclarationAnswer = (questionId, value) => {
    setIsAnimating(true);
    const newDeclarations = { ...declarations, [questionId]: value };
    setDeclarations(newDeclarations);

    setTimeout(() => {
      setIsAnimating(false);

      // Find next visible question
      let nextIndex = currentQuestionIndex + 1;
      while (nextIndex < DECLARATION_QUESTIONS.length) {
        const nextQuestion = DECLARATION_QUESTIONS[nextIndex];
        if (shouldShowQuestion(nextQuestion, newDeclarations)) {
          setCurrentQuestionIndex(nextIndex);
          return;
        }
        nextIndex++;
      }

      // No more visible questions - move to next stage
      showMicroWinAnimation('Great! Your checklist is ready!');
      setTimeout(() => setCurrentStage('profile'), 1500);
    }, 300);
  };

  // Go back to previous visible question
  const goToPrevQuestion = () => {
    let prevIndex = currentQuestionIndex - 1;
    while (prevIndex >= 0) {
      const prevQuestion = DECLARATION_QUESTIONS[prevIndex];
      if (shouldShowQuestion(prevQuestion, declarations)) {
        setCurrentQuestionIndex(prevIndex);
        return;
      }
      prevIndex--;
    }
  };

  // Get current visible question number for display
  const getVisibleQuestionNumber = () => {
    const visibleQuestions = getVisibleQuestions();
    const currentQuestion = DECLARATION_QUESTIONS[currentQuestionIndex];
    return visibleQuestions.findIndex(q => q.id === currentQuestion.id) + 1;
  };

  // Navigation
  const goToNextStage = () => {
    const currentIndex = STAGES.findIndex(s => s.id === currentStage);
    if (currentIndex < STAGES.length - 1) {
      setCurrentStage(STAGES[currentIndex + 1].id);
      showMicroWinAnimation(getStageMicroWin(STAGES[currentIndex].id));
    }
  };

  const goToPrevStage = () => {
    const currentIndex = STAGES.findIndex(s => s.id === currentStage);
    if (currentIndex > 0) {
      setCurrentStage(STAGES[currentIndex - 1].id);
    }
  };

  const getStageMicroWin = (stageId) => {
    const wins = {
      declarations: 'Great start!',
      profile: 'Profile complete!',
      income: 'Income captured!',
      assets: 'Assets recorded!',
      property: 'Almost done!',
    };
    return wins[stageId] || 'Section complete!';
  };

  // Render declarations
  // Handle input-type declaration answers (currency, address)
  const handleInputAnswer = (questionId, value) => {
    setDeclarations(prev => ({ ...prev, [questionId]: value }));
  };

  const submitInputAnswer = (questionId) => {
    if (declarations[questionId]) {
      setIsAnimating(true);
      setTimeout(() => {
        setIsAnimating(false);
        // Find next visible question
        let nextIndex = currentQuestionIndex + 1;
        while (nextIndex < DECLARATION_QUESTIONS.length) {
          const nextQuestion = DECLARATION_QUESTIONS[nextIndex];
          if (shouldShowQuestion(nextQuestion, declarations)) {
            setCurrentQuestionIndex(nextIndex);
            return;
          }
          nextIndex++;
        }
        // No more visible questions - move to next stage
        showMicroWinAnimation('Great! Your checklist is ready!');
        setTimeout(() => setCurrentStage('profile'), 1500);
      }, 300);
    }
  };

  const renderDeclarationsStage = () => {
    const question = DECLARATION_QUESTIONS[currentQuestionIndex];
    const visibleQuestions = getVisibleQuestions();
    const visibleQuestionNum = getVisibleQuestionNumber();

    // Guard: if question is undefined, reset to first question
    if (!question) {
      setCurrentQuestionIndex(0);
      return <div className="stage-content">Loading...</div>;
    }

    // Render different input types
    const renderQuestionInput = () => {
      if (question.type === 'currency') {
        return (
          <div className="declaration-input-container">
            <div className="currency-input-wrapper">
              <span className="currency-prefix">$</span>
              <input
                type="number"
                className="declaration-currency-input fun-input"
                value={declarations[question.id] || ''}
                onChange={(e) => handleInputAnswer(question.id, e.target.value)}
                placeholder={question.placeholder || '0'}
                onKeyPress={(e) => e.key === 'Enter' && submitInputAnswer(question.id)}
              />
              <span className="currency-suffix">/month</span>
            </div>
            <button
              className="btn-continue declaration-continue"
              onClick={() => submitInputAnswer(question.id)}
              disabled={!declarations[question.id]}
            >
              Continue →
            </button>
          </div>
        );
      }

      if (question.type === 'address') {
        return (
          <div className="declaration-input-container">
            <div className="address-input-wrapper">
              <Icon name="mapPin" size={20} className="address-icon" />
              <input
                type="text"
                className="declaration-address-input fun-input"
                value={declarations[question.id] || ''}
                onChange={(e) => handleInputAnswer(question.id, e.target.value)}
                placeholder={question.placeholder || 'Enter address'}
                onKeyPress={(e) => e.key === 'Enter' && submitInputAnswer(question.id)}
              />
            </div>
            <button
              className="btn-continue declaration-continue"
              onClick={() => submitInputAnswer(question.id)}
              disabled={!declarations[question.id]}
            >
              Continue →
            </button>
          </div>
        );
      }

      // Default: choice type
      if (!question.options) {
        return <div className="declaration-options">No options available</div>;
      }
      return (
        <div className="declaration-options">
          {question.options.map(option => (
            <button
              key={option.value}
              className={`declaration-option ${declarations[question.id] === option.value ? 'selected' : ''}`}
              onClick={() => handleDeclarationAnswer(question.id, option.value)}
            >
              <span className="option-icon"><Icon name={option.icon} size={32} /></span>
              <span className="option-label">{option.label}</span>
              {option.description && <span className="option-description">{option.description}</span>}
            </button>
          ))}
        </div>
      );
    };

    return (
      <div className={`declaration-screen ${isAnimating ? 'animating-out' : 'animating-in'}`}>
        <div className="question-number">
          Question {visibleQuestionNum} of {visibleQuestions.length}
        </div>
        <h2 className="declaration-question">{question.question}</h2>
        {question.hint && <p className="declaration-hint"><Icon name="info" size={16} /> {question.hint}</p>}
        {renderQuestionInput()}
        {currentQuestionIndex > 0 && (
          <button className="back-link" onClick={goToPrevQuestion}>
            ← Go back
          </button>
        )}
      </div>
    );
  };

  // Render profile
  const renderProfileStage = () => (
    <div className="stage-content">
      <div className="stage-header">
        <h2>Let's get to know you</h2>
        <p>This should take about 2 minutes</p>
      </div>
      <div className="form-card">
        <div className="form-row">
          <div className="form-group">
            <label>First Name</label>
            <input
              type="text"
              value={profileData.firstName || ''}
              onChange={(e) => setProfileData(prev => ({ ...prev, firstName: e.target.value }))}
              placeholder="Your first name"
              className="fun-input"
            />
          </div>
          <div className="form-group">
            <label>Last Name</label>
            <input
              type="text"
              value={profileData.lastName || ''}
              onChange={(e) => setProfileData(prev => ({ ...prev, lastName: e.target.value }))}
              placeholder="Your last name"
              className="fun-input"
            />
          </div>
        </div>
        <div className="form-row">
          <div className="form-group">
            <label>Email</label>
            <input
              type="email"
              value={profileData.email || ''}
              onChange={(e) => setProfileData(prev => ({ ...prev, email: e.target.value }))}
              placeholder="you@example.com"
              className="fun-input"
            />
          </div>
          <div className="form-group">
            <label>Phone</label>
            <input
              type="tel"
              value={profileData.phone || ''}
              onChange={(e) => setProfileData(prev => ({ ...prev, phone: e.target.value }))}
              placeholder="(555) 123-4567"
              className="fun-input"
            />
          </div>
        </div>
        <div className="form-group">
          <label>Date of Birth</label>
          <input
            type="date"
            value={profileData.dob || ''}
            onChange={(e) => setProfileData(prev => ({ ...prev, dob: e.target.value }))}
            className="fun-input"
          />
        </div>
        <div className="form-group">
          <label>Current Address</label>
          <input
            type="text"
            value={profileData.address || ''}
            onChange={(e) => setProfileData(prev => ({ ...prev, address: e.target.value }))}
            placeholder="Start typing your address..."
            className="fun-input"
          />
        </div>
        {declarations.marital_status === 'married' && (
          <div className="spouse-section">
            <h3><Icon name="users" size={20} /> Spouse Information</h3>
            <div className="form-row">
              <div className="form-group">
                <label>Spouse's First Name</label>
                <input
                  type="text"
                  value={profileData.spouseFirstName || ''}
                  onChange={(e) => setProfileData(prev => ({ ...prev, spouseFirstName: e.target.value }))}
                  className="fun-input"
                />
              </div>
              <div className="form-group">
                <label>Spouse's Last Name</label>
                <input
                  type="text"
                  value={profileData.spouseLastName || ''}
                  onChange={(e) => setProfileData(prev => ({ ...prev, spouseLastName: e.target.value }))}
                  className="fun-input"
                />
              </div>
            </div>
          </div>
        )}
      </div>
      <div className="stage-navigation">
        <button className="btn-back" onClick={goToPrevStage}>← Back</button>
        <button className="btn-continue" onClick={goToNextStage}>Continue →</button>
      </div>
    </div>
  );

  // Render income
  const renderIncomeStage = () => {
    const isSelfEmployed = declarations.self_employed === 'yes' || declarations.self_employed === 'side_business';

    // Determine income type from declarations
    const getIncomeType = () => {
      if (declarations.self_employed === 'yes') return 'self_employed';
      if (declarations.self_employed === 'side_business') return 'employed_with_business';
      return 'employed'; // Default to employed if 'no' or not set
    };

    const currentIncomeType = getIncomeType();

    // Show income details directly (skip the duplicate question)
    return (
      <div className="stage-content">
        <div className="stage-header">
          <h2>
            {currentIncomeType === 'employed' && 'Employment Details'}
            {currentIncomeType === 'self_employed' && 'Business Details'}
            {currentIncomeType === 'employed_with_business' && 'Employment & Business Details'}
          </h2>
          <p>Tell us more about your income</p>
        </div>

        {(currentIncomeType === 'employed' || currentIncomeType === 'employed_with_business') && (
          <div className="form-card">
            <EmployerAutocomplete
              value={incomeData.employerName || ''}
              onChange={(value) => setIncomeData(prev => ({ ...prev, employerName: value }))}
              onEmployerSelect={(employer) => {
                setIncomeData(prev => ({
                  ...prev,
                  employerName: employer.name,
                  employerAddress: employer.address,
                  employerCity: employer.city,
                  employerState: employer.state,
                  employerPhone: employer.phone,
                }));
              }}
              label="Employer Name"
              placeholder="Start typing company name..."
              className="fun-input-wrapper"
            />
            <div className="form-row">
              <div className="form-group">
                <label>Job Title</label>
                <input
                  type="text"
                  value={incomeData.jobTitle || ''}
                  onChange={(e) => setIncomeData(prev => ({ ...prev, jobTitle: e.target.value }))}
                  className="fun-input"
                />
              </div>
              <div className="form-group">
                <label>Years There</label>
                <input
                  type="number"
                  value={incomeData.yearsAtJob || ''}
                  onChange={(e) => setIncomeData(prev => ({ ...prev, yearsAtJob: e.target.value }))}
                  className="fun-input"
                  min="0"
                />
              </div>
            </div>
            <div className="form-group">
              <label>Annual Base Salary</label>
              <div className="input-with-prefix">
                <span className="input-prefix">$</span>
                <input
                  type="number"
                  value={incomeData.annualSalary || ''}
                  onChange={(e) => setIncomeData(prev => ({ ...prev, annualSalary: e.target.value }))}
                  className="fun-input"
                  placeholder="0"
                />
              </div>
            </div>
          </div>
        )}

        {(currentIncomeType === 'self_employed' || currentIncomeType === 'employed_with_business') && (
          <div className="form-card">
            <div className="form-group">
              <label>Business Name</label>
              <input
                type="text"
                value={incomeData.businessName || ''}
                onChange={(e) => setIncomeData(prev => ({ ...prev, businessName: e.target.value }))}
                className="fun-input"
              />
            </div>
            <div className="form-row">
              <div className="form-group">
                <label>Business Type</label>
                <select
                  value={incomeData.businessType || ''}
                  onChange={(e) => setIncomeData(prev => ({ ...prev, businessType: e.target.value }))}
                  className="fun-input"
                >
                  <option value="">Select...</option>
                  <option value="sole_prop">Sole Proprietorship</option>
                  <option value="llc">LLC</option>
                  <option value="s_corp">S-Corporation</option>
                  <option value="c_corp">C-Corporation</option>
                </select>
              </div>
              <div className="form-group">
                <label>Ownership %</label>
                <input
                  type="number"
                  value={incomeData.ownershipPercent || ''}
                  onChange={(e) => setIncomeData(prev => ({ ...prev, ownershipPercent: e.target.value }))}
                  className="fun-input"
                  min="0"
                  max="100"
                  placeholder="25"
                />
              </div>
            </div>
            <div className="form-group">
              <label>Annual Net Income (from business)</label>
              <div className="input-with-prefix">
                <span className="input-prefix">$</span>
                <input
                  type="number"
                  value={incomeData.businessIncome || ''}
                  onChange={(e) => setIncomeData(prev => ({ ...prev, businessIncome: e.target.value }))}
                  className="fun-input"
                />
              </div>
              <span className="input-hint">Use your net income from Schedule C or K-1</span>
            </div>
          </div>
        )}

        {/* Additional income section for rental, retirement, etc. */}
        <div className="form-card">
          <h3>Additional Income (Optional)</h3>
          <div className="form-row">
            <div className="form-group">
              <label>Monthly Rental Income</label>
              <div className="input-with-prefix">
                <span className="input-prefix">$</span>
                <input
                  type="number"
                  value={incomeData.rentalIncome || ''}
                  onChange={(e) => setIncomeData(prev => ({ ...prev, rentalIncome: e.target.value }))}
                  className="fun-input"
                  placeholder="0"
                />
              </div>
            </div>
            <div className="form-group">
              <label>Other Monthly Income</label>
              <div className="input-with-prefix">
                <span className="input-prefix">$</span>
                <input
                  type="number"
                  value={incomeData.otherIncome || ''}
                  onChange={(e) => setIncomeData(prev => ({ ...prev, otherIncome: e.target.value }))}
                  className="fun-input"
                  placeholder="0"
                />
              </div>
            </div>
          </div>
        </div>

        <div className="stage-navigation">
          <button className="btn-back" onClick={goToPrevStage}>← Back</button>
          <button className="btn-continue" onClick={goToNextStage}>Continue →</button>
        </div>
      </div>
    );
  };

  // Render assets
  const renderAssetsStage = () => {
    const hasGiftFunds = declarations.gift_funds === 'yes';

    return (
      <div className="stage-content">
        <div className="stage-header">
          <h2>Your Down Payment Funds</h2>
          <p>Let's see what you have saved for your new home</p>
        </div>
        <div className="form-card">
          <div className="connect-bank-section">
            <div className="connect-bank-card">
              <span className="bank-icon"><Icon name="bank" size={40} /></span>
              <h3>Connect Your Bank</h3>
              <p>Securely link your accounts to auto-fill your balances</p>
              <button className="btn-connect-bank">Connect with Plaid</button>
              <span className="security-note"><Icon name="lock" size={14} /> Bank-level encryption</span>
            </div>
            <div className="or-divider"><span>or enter manually</span></div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label>Checking Accounts</label>
              <div className="input-with-prefix">
                <span className="input-prefix">$</span>
                <input
                  type="number"
                  value={assetData.checking || ''}
                  onChange={(e) => setAssetData(prev => ({ ...prev, checking: e.target.value }))}
                  className="fun-input"
                  placeholder="0"
                />
              </div>
            </div>
            <div className="form-group">
              <label>Savings Accounts</label>
              <div className="input-with-prefix">
                <span className="input-prefix">$</span>
                <input
                  type="number"
                  value={assetData.savings || ''}
                  onChange={(e) => setAssetData(prev => ({ ...prev, savings: e.target.value }))}
                  className="fun-input"
                  placeholder="0"
                />
              </div>
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label>Investment Accounts</label>
              <div className="input-with-prefix">
                <span className="input-prefix">$</span>
                <input
                  type="number"
                  value={assetData.investments || ''}
                  onChange={(e) => setAssetData(prev => ({ ...prev, investments: e.target.value }))}
                  className="fun-input"
                  placeholder="0"
                />
              </div>
            </div>
            <div className="form-group">
              <label>Retirement (401k, IRA)</label>
              <div className="input-with-prefix">
                <span className="input-prefix">$</span>
                <input
                  type="number"
                  value={assetData.retirement || ''}
                  onChange={(e) => setAssetData(prev => ({ ...prev, retirement: e.target.value }))}
                  className="fun-input"
                  placeholder="0"
                />
              </div>
            </div>
          </div>

          {hasGiftFunds && (
            <div className="gift-funds-section">
              <h3><Icon name="gift" size={20} /> Gift Funds Details</h3>
              <p className="section-hint">Great news! Gift funds can help with your down payment.</p>
              <div className="form-group">
                <label>Gift Amount</label>
                <div className="input-with-prefix">
                  <span className="input-prefix">$</span>
                  <input
                    type="number"
                    value={assetData.giftAmount || ''}
                    onChange={(e) => setAssetData(prev => ({ ...prev, giftAmount: e.target.value }))}
                    className="fun-input"
                  />
                </div>
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label>Donor Name</label>
                  <input
                    type="text"
                    value={assetData.donorName || ''}
                    onChange={(e) => setAssetData(prev => ({ ...prev, donorName: e.target.value }))}
                    className="fun-input"
                    placeholder="Who is giving the gift?"
                  />
                </div>
                <div className="form-group">
                  <label>Relationship</label>
                  <select
                    value={assetData.donorRelationship || ''}
                    onChange={(e) => setAssetData(prev => ({ ...prev, donorRelationship: e.target.value }))}
                    className="fun-input"
                  >
                    <option value="">Select...</option>
                    <option value="parent">Parent</option>
                    <option value="grandparent">Grandparent</option>
                    <option value="sibling">Sibling</option>
                    <option value="other_family">Other Family</option>
                  </select>
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="total-assets-display">
          <span>Total Available for Down Payment:</span>
          <strong>
            ${(
              (parseFloat(assetData.checking) || 0) +
              (parseFloat(assetData.savings) || 0) +
              (parseFloat(assetData.investments) || 0) +
              (parseFloat(assetData.giftAmount) || 0)
            ).toLocaleString()}
          </strong>
        </div>

        <div className="stage-navigation">
          <button className="btn-back" onClick={goToPrevStage}>← Back</button>
          <button className="btn-continue" onClick={goToNextStage}>Continue →</button>
        </div>
      </div>
    );
  };

  // Render property (purchase-specific)
  const renderPropertyStage = () => {
    const isVeteran = declarations.veteran === 'yes' || declarations.veteran === 'active';
    const isFirstTimeBuyer = declarations.first_time_buyer === 'yes';

    // Step 1: Property Type and Occupancy
    if (propertyStep === 1) {
      return (
        <div className="stage-content">
          <div className="stage-header">
            <h2>Property Type</h2>
            <p>What type of property are you looking for?</p>
          </div>

          <div className="form-card">
            <div className="property-type-selector">
              <label>Property Type</label>
              <div className="type-pills">
                {['Single Family', 'Condo', 'Townhouse', 'Multi-Family'].map(type => (
                  <button
                    key={type}
                    className={`type-pill ${propertyData.propertyType === type ? 'selected' : ''}`}
                    onClick={() => setPropertyData(prev => ({ ...prev, propertyType: type }))}
                  >
                    {type}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="stage-navigation">
            <button className="btn-back" onClick={goToPrevStage}>← Back</button>
            <button
              className="btn-continue"
              onClick={() => setPropertyStep(2)}
              disabled={!propertyData.propertyType}
            >
              Continue →
            </button>
          </div>
        </div>
      );
    }

    // Step 2: Occupancy Type
    if (propertyStep === 2) {
      return (
        <div className="stage-content">
          <div className="stage-header">
            <h2>How Will You Use This Home?</h2>
            <p>This affects your loan options and rates</p>
          </div>

          <div className="form-card">
            <div className="occupancy-selector">
              <div className="income-cards">
                <div
                  className={`income-card ${propertyData.occupancy === 'primary' ? 'selected' : ''}`}
                  onClick={() => setPropertyData(prev => ({ ...prev, occupancy: 'primary' }))}
                >
                  <span className="card-icon"><Icon name="home" size={28} /></span>
                  <span className="card-label">Primary Home</span>
                  <span className="card-desc">I'll live here</span>
                </div>
                <div
                  className={`income-card ${propertyData.occupancy === 'second' ? 'selected' : ''}`}
                  onClick={() => setPropertyData(prev => ({ ...prev, occupancy: 'second' }))}
                >
                  <span className="card-icon"><Icon name="beach" size={28} /></span>
                  <span className="card-label">Second Home</span>
                  <span className="card-desc">Vacation property</span>
                </div>
                <div
                  className={`income-card ${propertyData.occupancy === 'investment' ? 'selected' : ''}`}
                  onClick={() => setPropertyData(prev => ({ ...prev, occupancy: 'investment' }))}
                >
                  <span className="card-icon"><Icon name="trendUp" size={28} /></span>
                  <span className="card-label">Investment</span>
                  <span className="card-desc">Rental income</span>
                </div>
              </div>
            </div>
          </div>

          <div className="stage-navigation">
            <button className="btn-back" onClick={() => setPropertyStep(1)}>← Back</button>
            <button
              className="btn-continue"
              onClick={() => setPropertyStep(3)}
              disabled={!propertyData.occupancy}
            >
              Continue →
            </button>
          </div>
        </div>
      );
    }

    // Step 3: Price, Down Payment, and Loan Program
    return (
      <div className="stage-content">
        <div className="stage-header">
          <h2>Price & Loan Details</h2>
          <p>Tell us about your budget and preferred loan program</p>
        </div>

        <div className="form-card">
          {declarations.found_property === 'yes' && (
            <AddressAutocomplete
              value={propertyData.address || ''}
              onChange={(value) => setPropertyData(prev => ({ ...prev, address: value }))}
              onAddressSelect={(addressData) => {
                setPropertyData(prev => ({
                  ...prev,
                  address: addressData.formatted,
                  street: addressData.street,
                  city: addressData.city,
                  state: addressData.state_code,
                  zip: addressData.zip,
                  county: addressData.county,
                }));
              }}
              label="Property Address"
              placeholder="Enter property address..."
              className="fun-input-wrapper"
            />
          )}

          <div className="form-row">
            <div className="form-group">
              <label>{declarations.found_property === 'yes' ? 'Purchase Price' : 'Target Price Range'}</label>
              <div className="input-with-prefix">
                <span className="input-prefix">$</span>
                <input
                  type="number"
                  value={propertyData.purchasePrice || ''}
                  onChange={(e) => setPropertyData(prev => ({ ...prev, purchasePrice: e.target.value }))}
                  className="fun-input"
                  placeholder="0"
                />
              </div>
            </div>
            <div className="form-group">
              <label>Down Payment</label>
              <div className="input-with-prefix">
                <span className="input-prefix">$</span>
                <input
                  type="number"
                  value={propertyData.downPayment || ''}
                  onChange={(e) => setPropertyData(prev => ({ ...prev, downPayment: e.target.value }))}
                  className="fun-input"
                  placeholder="0"
                />
              </div>
              {propertyData.purchasePrice && propertyData.downPayment && (
                <span className="calculated-hint">
                  {((propertyData.downPayment / propertyData.purchasePrice) * 100).toFixed(1)}% down
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Loan Program Selection */}
        <div className="form-card">
          <h3>Recommended Loan Programs</h3>
          <div className="program-cards">
            {isVeteran && (
              <div
                className={`program-card va ${propertyData.program === 'va' ? 'selected' : ''}`}
                onClick={() => setPropertyData(prev => ({ ...prev, program: 'va' }))}
              >
                <span className="program-badge"><Icon name="medal" size={12} /> FOR YOU</span>
                <span className="program-name">VA Loan</span>
                <span className="program-rate">~6.0% APR</span>
                <span className="program-note">$0 down, no PMI</span>
              </div>
            )}
            <div
              className={`program-card ${propertyData.program === 'conventional' ? 'selected' : ''}`}
              onClick={() => setPropertyData(prev => ({ ...prev, program: 'conventional' }))}
            >
              <span className="program-name">Conventional</span>
              <span className="program-rate">~6.5% APR</span>
              <span className="program-note">Best for 20%+ down</span>
            </div>
            <div
              className={`program-card ${propertyData.program === 'fha' ? 'selected' : ''}`}
              onClick={() => setPropertyData(prev => ({ ...prev, program: 'fha' }))}
            >
              {isFirstTimeBuyer && <span className="program-badge"><Icon name="thumbsUp" size={12} /> POPULAR</span>}
              <span className="program-name">FHA</span>
              <span className="program-rate">~6.25% APR</span>
              <span className="program-note">3.5% down, flexible credit</span>
            </div>
            <div
              className={`program-card ${propertyData.program === 'usda' ? 'selected' : ''}`}
              onClick={() => setPropertyData(prev => ({ ...prev, program: 'usda' }))}
            >
              <span className="program-name">USDA</span>
              <span className="program-rate">~6.25% APR</span>
              <span className="program-note">$0 down, rural areas</span>
            </div>
          </div>
        </div>

        <div className="stage-navigation">
          <button className="btn-back" onClick={() => setPropertyStep(2)}>← Back</button>
          <button className="btn-continue" onClick={goToNextStage}>Continue →</button>
        </div>
      </div>
    );
  };

  // Render review
  const renderReviewStage = () => (
    <div className="stage-content">
      <div className="stage-header">
        <h2>Review Your Application</h2>
        <p>Let's make sure everything looks good!</p>
      </div>

      <div className="review-sections">
        <div className="review-section">
          <div className="section-header">
            <h3><Icon name="profile" size={18} /> Your Profile</h3>
            <button className="edit-btn" onClick={() => setCurrentStage('profile')}><Icon name="edit" size={14} /></button>
          </div>
          <div className="section-content">
            <p><strong>Name:</strong> {profileData.firstName} {profileData.lastName}</p>
            <p><strong>Email:</strong> {profileData.email}</p>
            <p><strong>Phone:</strong> {profileData.phone}</p>
          </div>
        </div>

        <div className="review-section">
          <div className="section-header">
            <h3><Icon name="briefcase" size={18} /> Income</h3>
            <button className="edit-btn" onClick={() => setCurrentStage('income')}><Icon name="edit" size={14} /></button>
          </div>
          <div className="section-content">
            <p><strong>Type:</strong> {incomeData.primaryType}</p>
            {incomeData.employerName && <p><strong>Employer:</strong> {incomeData.employerName}</p>}
            {incomeData.annualSalary && <p><strong>Annual Income:</strong> ${parseFloat(incomeData.annualSalary).toLocaleString()}</p>}
          </div>
        </div>

        <div className="review-section">
          <div className="section-header">
            <h3><Icon name="dollarSign" size={18} /> Down Payment</h3>
            <button className="edit-btn" onClick={() => setCurrentStage('assets')}><Icon name="edit" size={14} /></button>
          </div>
          <div className="section-content">
            <p><strong>Total Available:</strong> ${(
              (parseFloat(assetData.checking) || 0) +
              (parseFloat(assetData.savings) || 0) +
              (parseFloat(assetData.investments) || 0) +
              (parseFloat(assetData.giftAmount) || 0)
            ).toLocaleString()}</p>
            {declarations.gift_funds === 'yes' && (
              <p><strong>Gift Funds:</strong> ${parseFloat(assetData.giftAmount || 0).toLocaleString()}</p>
            )}
          </div>
        </div>

        <div className="review-section">
          <div className="section-header">
            <h3><Icon name="home" size={18} /> New Home</h3>
            <button className="edit-btn" onClick={() => setCurrentStage('property')}><Icon name="edit" size={14} /></button>
          </div>
          <div className="section-content">
            <p><strong>Property Type:</strong> {propertyData.propertyType}</p>
            <p><strong>Purchase Price:</strong> ${parseFloat(propertyData.purchasePrice || 0).toLocaleString()}</p>
            <p><strong>Down Payment:</strong> ${parseFloat(propertyData.downPayment || 0).toLocaleString()}</p>
            <p><strong>Loan Program:</strong> {propertyData.program?.toUpperCase()}</p>
          </div>
        </div>
      </div>

      <div className="stage-navigation">
        <button className="btn-back" onClick={goToPrevStage}>← Back</button>
        <button className="btn-continue" onClick={goToNextStage}>Continue →</button>
      </div>
    </div>
  );

  // Toggle multi-select options for planning
  const togglePlanningOption = (field, value) => {
    setPlanningData(prev => {
      const current = prev[field] || [];
      if (current.includes(value)) {
        return { ...prev, [field]: current.filter(v => v !== value) };
      } else {
        return { ...prev, [field]: [...current, value] };
      }
    });
  };

  // Render planning stage with mortgage questionnaire - split into 5 pages
  const renderPlanningStage = () => {
    // Step 1: Mortgage Priorities
    if (planningStep === 1) {
      return (
        <div className="stage-content planning-stage">
          <div className="stage-header">
            <h2>What matters most to you in your mortgage?</h2>
            <p>Select all that apply - this helps us find the best loan options for you.</p>
          </div>

          <div className="form-card planning-section">
            <div className="multi-select-grid">
              {PLANNING_QUESTIONS.mortgagePriorities.options.map(option => (
                <button
                  key={option.value}
                  className={`multi-select-option ${planningData.mortgagePriorities.includes(option.value) ? 'selected' : ''}`}
                  onClick={() => togglePlanningOption('mortgagePriorities', option.value)}
                >
                  <span className="option-icon"><Icon name={option.icon} size={32} /></span>
                  <span className="option-label">{option.label}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="stage-navigation">
            <button className="btn-back" onClick={goToPrevStage}>← Back</button>
            <button className="btn-continue" onClick={() => setPlanningStep(2)}>Continue →</button>
          </div>
        </div>
      );
    }

    // Step 2: Personal Goals
    if (planningStep === 2) {
      return (
        <div className="stage-content planning-stage">
          <div className="stage-header">
            <h2>What are your personal financial goals?</h2>
            <p>Select all that apply - help us align your mortgage with your life plans.</p>
          </div>

          <div className="form-card planning-section">
            <div className="multi-select-grid">
              {PLANNING_QUESTIONS.personalGoals.options.map(option => (
                <button
                  key={option.value}
                  className={`multi-select-option ${planningData.personalGoals.includes(option.value) ? 'selected' : ''}`}
                  onClick={() => togglePlanningOption('personalGoals', option.value)}
                >
                  <span className="option-icon"><Icon name={option.icon} size={32} /></span>
                  <span className="option-label">{option.label}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="stage-navigation">
            <button className="btn-back" onClick={() => setPlanningStep(1)}>← Back</button>
            <button className="btn-continue" onClick={() => setPlanningStep(3)}>Continue →</button>
          </div>
        </div>
      );
    }

    // Step 3: Financial Philosophy
    if (planningStep === 3) {
      return (
        <div className="stage-content planning-stage">
          <div className="stage-header">
            <h2>How would you describe your financial approach?</h2>
            <p>This helps us recommend the right loan structure for your style.</p>
          </div>

          <div className="form-card planning-section">
            <div className="philosophy-options">
              {PLANNING_QUESTIONS.financialPhilosophy.options.map(option => (
                <button
                  key={option.value}
                  className={`philosophy-option ${planningData.financialPhilosophy === option.value ? 'selected' : ''}`}
                  onClick={() => setPlanningData(prev => ({ ...prev, financialPhilosophy: option.value }))}
                >
                  <span className="option-icon"><Icon name={option.icon} size={32} /></span>
                  <span className="option-label">{option.label}</span>
                  <span className="option-description">{option.description}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="stage-navigation">
            <button className="btn-back" onClick={() => setPlanningStep(2)}>← Back</button>
            <button className="btn-continue" onClick={() => setPlanningStep(4)}>Continue →</button>
          </div>
        </div>
      );
    }

    // Step 4: Tax-Deferred Retirement
    if (planningStep === 4) {
      return (
        <div className="stage-content planning-stage">
          <div className="stage-header">
            <h2>Are you currently contributing to a tax-deferred retirement account?</h2>
            <p>We can coordinate with your existing team for a comprehensive financial plan.</p>
          </div>

          <div className="form-card planning-section">
            <div className="single-select-options">
              {PLANNING_QUESTIONS.taxDeferredRetirement.options.map(option => (
                <button
                  key={option.value}
                  className={`single-select-option ${planningData.taxDeferredRetirement === option.value ? 'selected' : ''}`}
                  onClick={() => setPlanningData(prev => ({ ...prev, taxDeferredRetirement: option.value }))}
                >
                  <span className="option-icon"><Icon name={option.icon} size={32} /></span>
                  <span className="option-label">{option.label}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="stage-navigation">
            <button className="btn-back" onClick={() => setPlanningStep(3)}>← Back</button>
            <button className="btn-continue" onClick={() => setPlanningStep(5)}>Continue →</button>
          </div>
        </div>
      );
    }

    // Step 5: Professional Network
    return (
      <div className="stage-content planning-stage">
        <div className="stage-header">
          <h2>Do you currently work with any of these professionals?</h2>
          <p>We can coordinate with your existing team for a comprehensive financial plan.</p>
        </div>

        <div className="form-card planning-section">
          <div className="multi-select-grid compact">
            {PLANNING_QUESTIONS.professionalNetwork.options.map(option => (
              <button
                key={option.value}
                className={`multi-select-option ${planningData.professionalNetwork.includes(option.value) ? 'selected' : ''}`}
                onClick={() => togglePlanningOption('professionalNetwork', option.value)}
              >
                <span className="option-icon"><Icon name={option.icon} size={32} /></span>
                <span className="option-label">{option.label}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="stage-navigation">
          <button className="btn-back" onClick={() => setPlanningStep(4)}>← Back</button>
          <button className="btn-continue" onClick={() => { setPlanningStep(1); goToNextStage(); }}>Continue →</button>
        </div>
      </div>
    );
  };

  // Generate available time slots
  const generateTimeSlots = () => {
    const slots = [];
    const today = new Date();
    for (let d = 1; d <= 5; d++) {
      const date = new Date(today);
      date.setDate(today.getDate() + d);
      if (date.getDay() === 0 || date.getDay() === 6) continue; // Skip weekends

      ['9:00 AM', '10:30 AM', '1:00 PM', '2:30 PM', '4:00 PM'].forEach(time => {
        slots.push({
          id: `${date.toISOString().split('T')[0]}-${time}`,
          date: date.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' }),
          time: time,
        });
      });
    }
    return slots.slice(0, 12); // Return first 12 slots
  };

  // Render schedule stage - split into 2 steps: calendar first, then video/next steps
  const renderScheduleStage = () => {
    const timeSlots = generateTimeSlots();

    // Step 1: Calendar selection
    if (scheduleStep === 1) {
      return (
        <div className="stage-content scheduling-page">
          <div className="scheduling-header">
            <h2>Schedule Your Consultation</h2>
            <p>Let's find a time that works for you to discuss your mortgage options.</p>
          </div>

          <div className="calendar-section">
            <div className="calendar-placeholder">
              <span className="cal-icon"><Icon name="calendar" size={48} /></span>
              <h4>Pick a Time That Works For You</h4>
              <p>Select an available time slot below for your 15-minute consultation call</p>

              <div className="time-slots">
                {timeSlots.map(slot => (
                  <div
                    key={slot.id}
                    className={`time-slot ${selectedTimeSlot === slot.id ? 'selected' : ''}`}
                    onClick={() => setSelectedTimeSlot(slot.id)}
                  >
                    <div className="time-slot-time">{slot.time}</div>
                    <div className="time-slot-date">{slot.date}</div>
                  </div>
                ))}
              </div>

              <button
                className="btn-schedule"
                disabled={!selectedTimeSlot}
                onClick={() => {
                  showMicroWinAnimation('Consultation Scheduled!');
                  setScheduleStep(2);
                }}
              >
                {selectedTimeSlot ? 'Confirm Appointment' : 'Select a Time Slot'}
              </button>
            </div>
          </div>

          <div className="stage-navigation">
            <button className="btn-back" onClick={goToPrevStage}>← Back</button>
          </div>
        </div>
      );
    }

    // Step 2: Video and next steps
    return (
      <div className="stage-content scheduling-page">
        <div className="scheduling-header">
          <h2>You're All Set!</h2>
          <p>Your consultation is scheduled. Here's what to expect next.</p>
        </div>

        <div className="video-section">
          <div className="video-container">
            <div className="video-placeholder">
              <span className="play-icon"><Icon name="play" size={48} /></span>
              <p>What to Expect: Your Home Buying Journey</p>
            </div>
          </div>

          <div className="next-steps-list">
            <h3><Icon name="clipboard" size={18} /> What Happens Next</h3>
            <ol>
              <li><strong>Consultation Call</strong> - We'll review your application and answer any questions</li>
              <li><strong>Document Collection</strong> - Upload your documents through our secure portal</li>
              <li><strong>Pre-Approval Letter</strong> - Receive your pre-approval to make offers with confidence</li>
              <li><strong>Find Your Dream Home</strong> - Shop with confidence knowing your financing is ready</li>
            </ol>
          </div>
        </div>

        <div className="submit-section">
          <p className="demo-notice">
            <span>DEMO:</span> Check your email for confirmation and document upload instructions.
          </p>
          <button className="btn-submit" onClick={() => showMicroWinAnimation('Application Complete! Welcome to your home buying journey.')}>
            Complete Application
          </button>
        </div>

        <div className="stage-navigation">
          <button className="btn-back" onClick={() => setScheduleStep(1)}>← Back</button>
        </div>
      </div>
    );
  };

  // Render current stage
  const renderStage = () => {
    switch (currentStage) {
      case 'declarations': return renderDeclarationsStage();
      case 'profile': return renderProfileStage();
      case 'income': return renderIncomeStage();
      case 'assets': return renderAssetsStage();
      case 'property': return renderPropertyStage();
      case 'review': return renderReviewStage();
      case 'planning': return renderPlanningStage();
      case 'schedule': return renderScheduleStage();
      default: return renderDeclarationsStage();
    }
  };

  return (
    <div className="adaptive-urla">
      {isDemoMode && (
        <div className="demo-banner">
          <span className="demo-badge">DEMO</span>
          Home Purchase Application
        </div>
      )}

      <div className="progress-header">
        <div className="progress-chapters">
          {STAGES.map((stage, index) => {
            const currentIndex = STAGES.findIndex(s => s.id === currentStage);
            const isComplete = index < currentIndex;
            const isCurrent = index === currentIndex;
            return (
              <div
                key={stage.id}
                className={`progress-chapter ${isComplete ? 'complete' : ''} ${isCurrent ? 'current' : ''} clickable`}
                onClick={() => setCurrentStage(stage.id)}
                style={{ cursor: 'pointer' }}
              >
                <span className="chapter-icon">{isComplete ? <Icon name="check" size={20} /> : <Icon name={stage.icon} size={20} />}</span>
                <span className="chapter-label">{stage.label}</span>
              </div>
            );
          })}
        </div>
        <div className="progress-bar-container">
          <div className="progress-bar">
            <div className="progress-fill" style={{ width: `${getProgress()}%` }}></div>
          </div>
          <span className="progress-text">{getProgress()}% Complete</span>
        </div>
      </div>

      {showMicroWin && (
        <div className="micro-win-toast">
          <span className="micro-win-icon"><Icon name="check" size={24} /></span>
          <span className="micro-win-message">{microWinMessage}</span>
        </div>
      )}

      <main className="urla-content">
        {renderStage()}
      </main>
    </div>
  );
}
