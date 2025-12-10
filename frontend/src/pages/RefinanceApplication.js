import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import AddressAutocomplete from '../components/AddressAutocomplete';
import EmployerAutocomplete from '../components/EmployerAutocomplete';
import './AdaptiveURLA.css';

/**
 * RefinanceApplication - Streamlined Refinance Application
 *
 * Tailored 6-Stage Flow for Refinancing:
 * 1. Declarations - Key questions for personalization
 * 2. Profile - Personal information
 * 3. Income - Employment and income details
 * 4. Current Property - Existing home details
 * 5. Refinance Goals - Cash-out, rate/term, loan program
 * 6. Review - Summary and submit
 */

// Professional Icon component with SVG icons
const Icon = ({ name, size = 24, className = '' }) => {
  const icons = {
    story: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="3" width="7" height="7" rx="1"></rect>
        <rect x="14" y="3" width="7" height="7" rx="1"></rect>
        <rect x="14" y="14" width="7" height="7" rx="1"></rect>
        <rect x="3" y="14" width="7" height="7" rx="1"></rect>
      </svg>
    ),
    profile: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
        <circle cx="12" cy="7" r="4"></circle>
      </svg>
    ),
    income: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="2" y="7" width="20" height="14" rx="2" ry="2"></rect>
        <path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"></path>
      </svg>
    ),
    home: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path>
        <polyline points="9 22 9 12 15 12 15 22"></polyline>
      </svg>
    ),
    target: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10"></circle>
        <circle cx="12" cy="12" r="6"></circle>
        <circle cx="12" cy="12" r="2"></circle>
      </svg>
    ),
    review: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
        <polyline points="22 4 12 14.01 9 11.01"></polyline>
      </svg>
    ),
    goals: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <line x1="18" y1="20" x2="18" y2="10"></line>
        <line x1="12" y1="20" x2="12" y2="4"></line>
        <line x1="6" y1="20" x2="6" y2="14"></line>
      </svg>
    ),
    calendar: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
        <line x1="16" y1="2" x2="16" y2="6"></line>
        <line x1="8" y1="2" x2="8" y2="6"></line>
        <line x1="3" y1="10" x2="21" y2="10"></line>
      </svg>
    ),
    check: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="20 6 9 17 4 12"></polyline>
      </svg>
    ),
    user: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
        <circle cx="12" cy="7" r="4"></circle>
      </svg>
    ),
    users: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
        <circle cx="9" cy="7" r="4"></circle>
        <path d="M23 21v-2a4 4 0 0 0-3-3.87"></path>
        <path d="M16 3.13a4 4 0 0 1 0 7.75"></path>
      </svg>
    ),
    family: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
        <circle cx="9" cy="7" r="4"></circle>
        <path d="M23 21v-2a4 4 0 0 0-3-3.87"></path>
        <path d="M16 3.13a4 4 0 0 1 0 7.75"></path>
      </svg>
    ),
    trendDown: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="23 18 13.5 8.5 8.5 13.5 1 6"></polyline>
        <polyline points="17 18 23 18 23 12"></polyline>
      </svg>
    ),
    dollarSign: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <line x1="12" y1="1" x2="12" y2="23"></line>
        <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"></path>
      </svg>
    ),
    money: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="1" y="4" width="22" height="16" rx="2" ry="2"></rect>
        <circle cx="12" cy="12" r="3"></circle>
        <line x1="1" y1="8" x2="5" y2="8"></line>
        <line x1="19" y1="8" x2="23" y2="8"></line>
        <line x1="1" y1="16" x2="5" y2="16"></line>
        <line x1="19" y1="16" x2="23" y2="16"></line>
      </svg>
    ),
    timer: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10"></circle>
        <polyline points="12 6 12 12 16 14"></polyline>
      </svg>
    ),
    couple: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
        <circle cx="9" cy="7" r="4"></circle>
        <path d="M23 21v-2a4 4 0 0 0-3-3.87"></path>
        <path d="M16 3.13a4 4 0 0 1 0 7.75"></path>
      </svg>
    ),
    document: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
        <polyline points="14 2 14 8 20 8"></polyline>
        <line x1="16" y1="13" x2="8" y2="13"></line>
        <line x1="16" y1="17" x2="8" y2="17"></line>
        <polyline points="10 9 9 9 8 9"></polyline>
      </svg>
    ),
    medal: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="8" r="6"></circle>
        <path d="M15.477 12.89L17 22l-5-3-5 3 1.523-9.11"></path>
      </svg>
    ),
    star: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon>
      </svg>
    ),
    arrowRight: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <line x1="5" y1="12" x2="19" y2="12"></line>
        <polyline points="12 5 19 12 12 19"></polyline>
      </svg>
    ),
    building: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="4" y="2" width="16" height="20" rx="2" ry="2"></rect>
        <path d="M9 22v-4h6v4"></path>
        <line x1="8" y1="6" x2="8" y2="6"></line>
        <line x1="16" y1="6" x2="16" y2="6"></line>
        <line x1="8" y1="10" x2="8" y2="10"></line>
        <line x1="16" y1="10" x2="16" y2="10"></line>
        <line x1="8" y1="14" x2="8" y2="14"></line>
        <line x1="16" y1="14" x2="16" y2="14"></line>
      </svg>
    ),
    briefcase: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="2" y="7" width="20" height="14" rx="2" ry="2"></rect>
        <path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"></path>
      </svg>
    ),
    tie: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 22l-4-4 1-9h6l1 9-4 4z"></path>
        <path d="M9 2h6v4l-3 1-3-1V2z"></path>
      </svg>
    ),
    warning: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path>
        <line x1="12" y1="9" x2="12" y2="13"></line>
        <line x1="12" y1="17" x2="12.01" y2="17"></line>
      </svg>
    ),
    clipboard: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"></path>
        <rect x="8" y="2" width="8" height="4" rx="1" ry="1"></rect>
      </svg>
    ),
    checkCircle: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
        <polyline points="22 4 12 14.01 9 11.01"></polyline>
      </svg>
    ),
    creditCard: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="1" y="4" width="22" height="16" rx="2" ry="2"></rect>
        <line x1="1" y1="10" x2="23" y2="10"></line>
      </svg>
    ),
    bank: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 21h18"></path>
        <path d="M3 10h18"></path>
        <path d="M5 6l7-3 7 3"></path>
        <path d="M4 10v11"></path>
        <path d="M20 10v11"></path>
        <path d="M8 10v11"></path>
        <path d="M12 10v11"></path>
        <path d="M16 10v11"></path>
      </svg>
    ),
    government: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 21h18"></path>
        <path d="M5 21V7l7-4 7 4v14"></path>
        <path d="M9 21v-6h6v6"></path>
      </svg>
    ),
    wheat: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M6 9l6 6 6-6"></path>
        <path d="M6 15l6 6 6-6"></path>
        <path d="M12 3v18"></path>
      </svg>
    ),
    helpCircle: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10"></circle>
        <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"></path>
        <line x1="12" y1="17" x2="12.01" y2="17"></line>
      </svg>
    ),
    condo: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="4" y="2" width="16" height="20" rx="2" ry="2"></rect>
        <path d="M9 22v-4h6v4"></path>
        <line x1="8" y1="6" x2="8" y2="6"></line>
        <line x1="16" y1="6" x2="16" y2="6"></line>
        <line x1="8" y1="10" x2="8" y2="10"></line>
        <line x1="16" y1="10" x2="16" y2="10"></line>
        <line x1="8" y1="14" x2="8" y2="14"></line>
        <line x1="16" y1="14" x2="16" y2="14"></line>
      </svg>
    ),
    townhouse: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 21h6V10L6 7l-3 3v11z"></path>
        <path d="M9 21h6V10l-3-3-3 3v11z"></path>
        <path d="M15 21h6V10l-3-3-3 3v11z"></path>
      </svg>
    ),
    multiFamily: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="4" y="2" width="16" height="20" rx="2" ry="2"></rect>
        <line x1="4" y1="12" x2="20" y2="12"></line>
        <line x1="12" y1="2" x2="12" y2="22"></line>
      </svg>
    ),
    starFilled: (
      <svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon>
      </svg>
    ),
    thumbsUp: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"></path>
      </svg>
    ),
    trendUp: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="23 6 13.5 15.5 8.5 10.5 1 18"></polyline>
        <polyline points="17 6 23 6 23 12"></polyline>
      </svg>
    ),
    info: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10"></circle>
        <line x1="12" y1="16" x2="12" y2="12"></line>
        <line x1="12" y1="8" x2="12.01" y2="8"></line>
      </svg>
    ),
    balance: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 3v18"></path>
        <path d="M5 6l14 0"></path>
        <path d="M3 10l4-4 4 4"></path>
        <path d="M13 10l4-4 4 4"></path>
        <circle cx="5" cy="18" r="2"></circle>
        <circle cx="19" cy="18" r="2"></circle>
      </svg>
    ),
    beach: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="5" r="3"></circle>
        <path d="M12 8v4"></path>
        <path d="M6 12l6 4 6-4"></path>
        <path d="M3 20h18"></path>
      </svg>
    ),
    flash: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon>
      </svg>
    ),
    refresh: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="23 4 23 10 17 10"></polyline>
        <polyline points="1 20 1 14 7 14"></polyline>
        <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
      </svg>
    ),
    homeHeart: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path>
        <path d="M12 14.5c-1.5-2-4-2-4 0s4 4 4 4 4-2 4-4-2.5-2-4 0z"></path>
      </svg>
    ),
    eagle: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 2L2 7l10 5 10-5-10-5z"></path>
        <path d="M2 17l10 5 10-5"></path>
        <path d="M2 12l10 5 10-5"></path>
      </svg>
    ),
    scissors: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="6" cy="6" r="3"></circle>
        <circle cx="6" cy="18" r="3"></circle>
        <line x1="20" y1="4" x2="8.12" y2="15.88"></line>
        <line x1="14.47" y1="14.48" x2="20" y2="20"></line>
        <line x1="8.12" y1="8.12" x2="12" y2="12"></line>
      </svg>
    ),
    graduation: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M22 10v6M2 10l10-5 10 5-10 5z"></path>
        <path d="M6 12v5c0 2 6 3 6 3s6-1 6-3v-5"></path>
      </svg>
    ),
    chart: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <line x1="18" y1="20" x2="18" y2="10"></line>
        <line x1="12" y1="20" x2="12" y2="4"></line>
        <line x1="6" y1="20" x2="6" y2="14"></line>
      </svg>
    ),
    rocket: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z"></path>
        <path d="M12 15l-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z"></path>
        <path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0"></path>
        <path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5"></path>
      </svg>
    ),
    shield: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path>
      </svg>
    ),
    calculator: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="4" y="2" width="16" height="20" rx="2"></rect>
        <line x1="8" y1="6" x2="16" y2="6"></line>
        <line x1="8" y1="10" x2="8" y2="10"></line>
        <line x1="12" y1="10" x2="12" y2="10"></line>
        <line x1="16" y1="10" x2="16" y2="10"></line>
        <line x1="8" y1="14" x2="8" y2="14"></line>
        <line x1="12" y1="14" x2="12" y2="14"></line>
        <line x1="16" y1="14" x2="16" y2="14"></line>
        <line x1="8" y1="18" x2="8" y2="18"></line>
        <line x1="12" y1="18" x2="12" y2="18"></line>
        <line x1="16" y1="18" x2="16" y2="18"></line>
      </svg>
    ),
    scroll: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M8 21h12a2 2 0 0 0 2-2v-2H10v2a2 2 0 1 1-4 0V5a2 2 0 1 0-4 0v3h4"></path>
        <path d="M19 17V5a2 2 0 0 0-2-2H4"></path>
      </svg>
    ),
    play: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polygon points="5 3 19 12 5 21 5 3"></polygon>
      </svg>
    ),
    x: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <line x1="18" y1="6" x2="6" y2="18"></line>
        <line x1="6" y1="6" x2="18" y2="18"></line>
      </svg>
    ),
    thinking: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10"></circle>
        <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"></path>
        <line x1="12" y1="17" x2="12.01" y2="17"></line>
      </svg>
    ),
    clock: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10"></circle>
        <polyline points="12,6 12,12 16,14"></polyline>
      </svg>
    ),
    mapPin: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"></path>
        <circle cx="12" cy="10" r="3"></circle>
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
  };

  return (
    <span className={`icon ${className}`} style={{ width: size, height: size, display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
      {icons[name] || icons.document}
    </span>
  );
};

const STAGES = [
  { id: 'declarations', label: 'Your Story', icon: 'story', description: 'Quick questions' },
  { id: 'profile', label: 'About You', icon: 'profile', description: 'The basics' },
  { id: 'income', label: 'Your Income', icon: 'income', description: 'How you earn' },
  { id: 'property', label: 'Current Home', icon: 'home', description: 'Property details' },
  { id: 'goals', label: 'Refi Goals', icon: 'target', description: 'Refinance options' },
  { id: 'review', label: 'Review', icon: 'review', description: 'Review your info' },
  { id: 'planning', label: 'Planning', icon: 'goals', description: 'Your preferences' },
  { id: 'schedule', label: 'Schedule', icon: 'calendar', description: 'Book a call' },
];

// Refinance-specific declaration questions
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
      { value: 'spouse', label: 'Spouse/Partner', icon: 'couple' },
      { value: 'relative', label: 'Family member', icon: 'family' },
      { value: 'friend', label: 'Friend/Non-relative', icon: 'users' },
      { value: 'business_partner', label: 'Business partner', icon: 'briefcase' },
    ],
    hint: 'This helps us understand the borrower structure.',
    showIf: { field: 'borrower_count', values: ['2', '3', '4+'] },
  },
  {
    id: 'refi_goal',
    question: 'What\'s your main goal for refinancing?',
    type: 'choice',
    options: [
      { value: 'lower_rate', label: 'Lower my interest rate', icon: 'trendDown' },
      { value: 'lower_payment', label: 'Lower my monthly payment', icon: 'dollarSign' },
      { value: 'cash_out', label: 'Get cash from my equity', icon: 'money' },
      { value: 'shorter_term', label: 'Pay off faster', icon: 'timer' },
    ],
  },
  {
    id: 'cash_out_amount',
    question: 'Approximately how much cash do you need?',
    type: 'currency',
    placeholder: 'Amount needed',
    hint: 'This helps us determine if you have enough equity.',
    showIf: { field: 'refi_goal', values: ['cash_out'] },
  },
  {
    id: 'cash_out_purpose',
    question: 'What will you use the cash for?',
    type: 'choice',
    options: [
      { value: 'home_improvement', label: 'Home improvement', icon: 'home' },
      { value: 'debt_consolidation', label: 'Debt consolidation', icon: 'creditCard' },
      { value: 'investment', label: 'Investment', icon: 'trendUp' },
      { value: 'other', label: 'Other expenses', icon: 'dollarSign' },
    ],
    hint: 'This helps us recommend the best loan structure.',
    showIf: { field: 'refi_goal', values: ['cash_out'] },
  },
  {
    id: 'marital_status',
    question: 'Are you married?',
    type: 'choice',
    options: [
      { value: 'married', label: 'Yes, married', icon: 'couple' },
      { value: 'single', label: 'Single', icon: 'user' },
      { value: 'divorced', label: 'Divorced', icon: 'document' },
      { value: 'separated', label: 'Separated', icon: 'users' },
      { value: 'widowed', label: 'Widowed', icon: 'couple' },
    ],
    unlocks: ['spouse_section'],
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
      { value: 'yes', label: 'Yes, finalized', icon: 'checkCircle' },
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
      { value: 'spouse', label: 'My spouse served', icon: 'couple' },
      { value: 'no', label: 'No military service', icon: 'arrowRight' },
    ],
    hint: 'VA streamline refinance options available!',
  },
  {
    id: 'va_loan_before',
    question: 'Have you used a VA loan before?',
    type: 'choice',
    options: [
      { value: 'yes_current', label: 'Yes, current loan is VA', icon: 'checkCircle' },
      { value: 'yes_previous', label: 'Yes, had one before', icon: 'home' },
      { value: 'no', label: 'No, first VA loan', icon: 'star' },
    ],
    hint: 'VA IRRRL streamline requires a current VA loan.',
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
      { value: 'more_than_2_years', label: 'More than 2 years', icon: 'checkCircle' },
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
      { value: 'yes', label: 'Yes, I owe the IRS', icon: 'warning' },
      { value: 'payment_plan', label: 'Yes, but on a payment plan', icon: 'clipboard' },
      { value: 'no', label: 'No outstanding balance', icon: 'checkCircle' },
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
      { value: 'yes', label: 'Yes, fully current', icon: 'checkCircle' },
      { value: 'behind', label: 'Behind on payments', icon: 'warning' },
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
      { value: 'no', label: 'No recent applications', icon: 'checkCircle' },
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
      { value: 'yes', label: 'Yes, approved', icon: 'checkCircle' },
      { value: 'pending', label: 'Still pending', icon: 'clock' },
      { value: 'no', label: 'No, denied', icon: 'x' },
    ],
    hint: 'If approved, we\'ll need to factor in the new payment.',
    showIf: { field: 'recent_credit_applications', values: ['yes'] },
  },
  {
    id: 'current_loan_type',
    question: 'What type of loan do you currently have?',
    type: 'choice',
    options: [
      { value: 'conventional', label: 'Conventional', icon: 'bank' },
      { value: 'fha', label: 'FHA', icon: 'government' },
      { value: 'va', label: 'VA', icon: 'medal' },
      { value: 'usda', label: 'USDA', icon: 'wheat' },
      { value: 'not_sure', label: 'Not sure', icon: 'helpCircle' },
    ],
  },
  {
    id: 'fha_streamline',
    question: 'Would you like to explore FHA Streamline refinance?',
    type: 'choice',
    options: [
      { value: 'yes', label: 'Yes, tell me more', icon: 'checkCircle' },
      { value: 'no', label: 'No, prefer full refinance', icon: 'arrowRight' },
    ],
    hint: 'FHA Streamline requires less documentation and no appraisal in most cases.',
    showIf: { field: 'current_loan_type', values: ['fha'] },
  },
  {
    id: 'property_type',
    question: 'What type of property is it?',
    type: 'choice',
    options: [
      { value: 'single_family', label: 'Single Family', icon: 'home' },
      { value: 'condo', label: 'Condo', icon: 'condo' },
      { value: 'townhouse', label: 'Townhouse', icon: 'townhouse' },
      { value: 'multi_family', label: 'Multi-Family (2-4 units)', icon: 'multiFamily' },
    ],
  },
  {
    id: 'rental_units',
    question: 'Do you rent out any of the units?',
    type: 'choice',
    options: [
      { value: 'yes_all', label: 'Yes, all units', icon: 'dollarSign' },
      { value: 'yes_some', label: 'Yes, some units', icon: 'home' },
      { value: 'no', label: 'No, I live in all', icon: 'user' },
    ],
    hint: 'Rental income can help you qualify for a larger loan.',
    showIf: { field: 'property_type', values: ['multi_family'] },
  },
  {
    id: 'credit_estimate',
    question: 'What\'s your estimated credit score?',
    type: 'choice',
    options: [
      { value: 'excellent', label: '740+', icon: 'starFilled', description: 'Excellent' },
      { value: 'good', label: '700-739', icon: 'thumbsUp', description: 'Good' },
      { value: 'fair', label: '640-699', icon: 'chart', description: 'Fair' },
      { value: 'building', label: 'Below 640', icon: 'trendUp', description: 'Building' },
    ],
    hint: 'Better credit often means better rates!',
  },
  {
    id: 'credit_issues',
    question: 'Have you had any credit challenges in the past 2 years?',
    type: 'choice',
    options: [
      { value: 'none', label: 'No issues', icon: 'checkCircle' },
      { value: 'late_payments', label: 'Late payments', icon: 'clock' },
      { value: 'collections', label: 'Collections/charge-offs', icon: 'warning' },
      { value: 'bankruptcy', label: 'Bankruptcy', icon: 'document' },
    ],
    hint: 'Being upfront helps us find the right program for you.',
    showIf: { field: 'credit_estimate', values: ['fair', 'building'] },
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
      { value: 'more_than_4_years', label: 'More than 4 years ago', icon: 'checkCircle' },
    ],
    hint: 'FHA allows financing 2 years after Chapter 7 discharge.',
    showIf: { field: 'credit_issues', values: ['bankruptcy'] },
  },
  {
    id: 'late_mortgage_payments',
    question: 'Have you had any late mortgage payments in the past 12 months?',
    type: 'choice',
    options: [
      { value: 'none', label: 'No late payments', icon: 'checkCircle' },
      { value: 'one', label: 'One late payment', icon: 'clock' },
      { value: 'multiple', label: 'Multiple late payments', icon: 'warning' },
    ],
    hint: 'Recent mortgage lates can affect refinance options.',
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
];

// Planning questions - mortgage priorities and goals (excludes questions already asked in declarations)
const PLANNING_QUESTIONS = {
  mortgagePriorities: {
    question: 'What matters most to you in your new mortgage?',
    hint: 'Select all that apply - this helps us find the best loan structure for you.',
    options: [
      { value: 'lowest_payment', label: 'Lowest Monthly Payment', icon: 'dollarSign' },
      { value: 'lowest_rate', label: 'Lowest Interest Rate', icon: 'trendDown' },
      { value: 'fastest_payoff', label: 'Pay Off Fastest', icon: 'flash' },
      { value: 'lowest_total', label: 'Lowest Total Cost', icon: 'target' },
      { value: 'flexibility', label: 'Maximum Flexibility', icon: 'refresh' },
      { value: 'tax_benefits', label: 'Tax Benefits', icon: 'clipboard' },
      { value: 'build_equity', label: 'Build Equity Faster', icon: 'trendUp' },
      { value: 'predictable', label: 'Predictable Payments', icon: 'chart' },
    ],
  },
  personalGoals: {
    question: 'What are your personal financial goals?',
    hint: 'Select all that apply - helps us align your refinance with your life plans.',
    options: [
      { value: 'net_worth', label: 'Building Net Worth', icon: 'money' },
      { value: 'larger_home', label: 'Moving to Larger Home', icon: 'homeHeart' },
      { value: 'financial_freedom', label: 'Financial Freedom', icon: 'eagle' },
      { value: 'pay_debt', label: 'Paying Off Debt', icon: 'scissors' },
      { value: 'retirement', label: 'Saving for Retirement', icon: 'beach' },
      { value: 'education', label: 'Children\'s Education', icon: 'graduation' },
      { value: 'investments', label: 'Investment Portfolio', icon: 'chart' },
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
      { value: 'estate_planner', label: 'Estate Planner', icon: 'scroll' },
    ],
  },
  taxDeferredRetirement: {
    question: 'Are you currently contributing to a tax-deferred retirement account?',
    hint: '401(k), IRA, or similar retirement savings',
    options: [
      { value: 'yes', label: 'Yes, I contribute regularly', icon: 'checkCircle' },
      { value: 'some', label: 'Sometimes / Not maxing out', icon: 'refresh' },
      { value: 'no', label: 'Not currently', icon: 'x' },
      { value: 'not_sure', label: 'Not sure', icon: 'thinking' },
    ],
  },
};

export default function RefinanceApplication() {
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
  const [propertyData, setPropertyData] = useState({});
  const [goalsData, setGoalsData] = useState({});
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

    if (declarations.veteran && declarations.veteran !== 'no') {
      newNeeds.push({ id: 'dd214', label: 'DD-214 or Certificate of Eligibility', category: 'military' });
    }

    // IRS payment plan documentation
    if (declarations.irs_balance_owed === 'yes' || declarations.irs_balance_owed === 'payment_plan') {
      newNeeds.push({ id: 'irs_docs', label: 'IRS payment arrangement documentation', category: 'legal' });
    }

    newNeeds.push({ id: 'mortgage_statement', label: 'Current mortgage statement', category: 'property' });
    newNeeds.push({ id: 'hoi', label: 'Homeowners insurance declaration', category: 'property' });
    newNeeds.push({ id: 'bank_statements', label: 'Bank statements (2 months)', category: 'assets' });

    if (declarations.refi_goal === 'cash_out') {
      newNeeds.push({ id: 'home_value', label: 'Recent appraisal or home value estimate', category: 'property' });
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

  // Handle input-based answers (currency, address)
  const handleInputAnswer = (questionId, value) => {
    setDeclarations(prev => ({ ...prev, [questionId]: value }));
  };

  // Submit input answer and advance to next question
  const submitInputAnswer = (questionId) => {
    if (declarations[questionId]) {
      setIsAnimating(true);
      setTimeout(() => {
        setIsAnimating(false);
        let nextIndex = currentQuestionIndex + 1;
        while (nextIndex < DECLARATION_QUESTIONS.length) {
          const nextQuestion = DECLARATION_QUESTIONS[nextIndex];
          if (shouldShowQuestion(nextQuestion, declarations)) {
            setCurrentQuestionIndex(nextIndex);
            return;
          }
          nextIndex++;
        }
        showMicroWinAnimation('Great! Your checklist is ready!');
        setTimeout(() => setCurrentStage('profile'), 1500);
      }, 300);
    }
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
      property: 'Property details saved!',
      goals: 'Almost done!',
    };
    return wins[stageId] || 'Section complete!';
  };

  // Render declarations
  const renderDeclarationsStage = () => {
    const question = DECLARATION_QUESTIONS[currentQuestionIndex];
    const visibleQuestions = getVisibleQuestions();
    const visibleQuestionNum = getVisibleQuestionNumber();

    const renderQuestionInput = () => {
      if (question.type === 'currency') {
        return (
          <div className="declaration-input-container">
            <div className="currency-input-wrapper">
              <span className="currency-prefix">$</span>
              <input
                type="number"
                className="declaration-currency-input fun-input"
                placeholder={question.placeholder || 'Enter amount'}
                value={declarations[question.id] || ''}
                onChange={(e) => handleInputAnswer(question.id, e.target.value)}
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
                placeholder={question.placeholder || 'Enter address'}
                value={declarations[question.id] || ''}
                onChange={(e) => handleInputAnswer(question.id, e.target.value)}
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
        {declarations.marital_status === 'married' && (
          <div className="spouse-section">
            <h3><Icon name="users" size={18} /> Spouse Information</h3>
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

    // Step 1: Income type selection
    if (incomeStep === 1) {
      return (
        <div className="stage-content">
          <div className="stage-header">
            <h2>Tell us about your income</h2>
            <p>This helps determine your refinance options</p>
          </div>
          <div className="income-type-selector">
            <h3>How do you earn income?</h3>
            <div className="income-cards">
              <div
                className={`income-card ${incomeData.primaryType === 'employed' ? 'selected' : ''}`}
                onClick={() => setIncomeData(prev => ({ ...prev, primaryType: 'employed' }))}
              >
                <span className="card-icon"><Icon name="tie" size={28} /></span>
                <span className="card-label">Employed</span>
                <span className="card-desc">W-2 employee</span>
              </div>
              <div
                className={`income-card ${incomeData.primaryType === 'self_employed' ? 'selected' : ''}`}
                onClick={() => setIncomeData(prev => ({ ...prev, primaryType: 'self_employed' }))}
              >
                <span className="card-icon"><Icon name="building" size={28} /></span>
                <span className="card-label">Self-Employed</span>
                <span className="card-desc">Business owner</span>
              </div>
              <div
                className={`income-card ${incomeData.primaryType === 'retired' ? 'selected' : ''}`}
                onClick={() => setIncomeData(prev => ({ ...prev, primaryType: 'retired' }))}
              >
                <span className="card-icon"><Icon name="beach" size={28} /></span>
                <span className="card-label">Retired</span>
                <span className="card-desc">Pension/SS</span>
              </div>
              <div
                className={`income-card ${incomeData.primaryType === 'other' ? 'selected' : ''}`}
                onClick={() => setIncomeData(prev => ({ ...prev, primaryType: 'other' }))}
              >
                <span className="card-icon"><Icon name="dollarSign" size={28} /></span>
                <span className="card-label">Other</span>
                <span className="card-desc">Rental, investments</span>
              </div>
            </div>
          </div>

          <div className="stage-navigation">
            <button className="btn-back" onClick={goToPrevStage}>← Back</button>
            <button
              className="btn-continue"
              onClick={() => incomeData.primaryType && setIncomeStep(2)}
              disabled={!incomeData.primaryType}
            >
              Continue →
            </button>
          </div>
        </div>
      );
    }

    // Step 2: Income details based on type
    return (
      <div className="stage-content">
        <div className="stage-header">
          <h2>
            {incomeData.primaryType === 'employed' && 'Employment Details'}
            {incomeData.primaryType === 'self_employed' && 'Business Details'}
            {incomeData.primaryType === 'retired' && 'Retirement Income'}
            {incomeData.primaryType === 'other' && 'Other Income'}
          </h2>
          <p>Tell us more about your income</p>
        </div>

        {incomeData.primaryType === 'employed' && (
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

        {(incomeData.primaryType === 'self_employed' || isSelfEmployed) && (
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

        {incomeData.primaryType === 'retired' && (
          <div className="form-card">
            <div className="form-group">
              <label>Monthly Social Security</label>
              <div className="input-with-prefix">
                <span className="input-prefix">$</span>
                <input
                  type="number"
                  value={incomeData.socialSecurity || ''}
                  onChange={(e) => setIncomeData(prev => ({ ...prev, socialSecurity: e.target.value }))}
                  className="fun-input"
                  placeholder="0"
                />
              </div>
            </div>
            <div className="form-group">
              <label>Monthly Pension</label>
              <div className="input-with-prefix">
                <span className="input-prefix">$</span>
                <input
                  type="number"
                  value={incomeData.pension || ''}
                  onChange={(e) => setIncomeData(prev => ({ ...prev, pension: e.target.value }))}
                  className="fun-input"
                  placeholder="0"
                />
              </div>
            </div>
            <div className="form-group">
              <label>Monthly Retirement Distributions (401k, IRA)</label>
              <div className="input-with-prefix">
                <span className="input-prefix">$</span>
                <input
                  type="number"
                  value={incomeData.retirementDistributions || ''}
                  onChange={(e) => setIncomeData(prev => ({ ...prev, retirementDistributions: e.target.value }))}
                  className="fun-input"
                  placeholder="0"
                />
              </div>
            </div>
          </div>
        )}

        {incomeData.primaryType === 'other' && (
          <div className="form-card">
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
              <label>Monthly Investment Income</label>
              <div className="input-with-prefix">
                <span className="input-prefix">$</span>
                <input
                  type="number"
                  value={incomeData.investmentIncome || ''}
                  onChange={(e) => setIncomeData(prev => ({ ...prev, investmentIncome: e.target.value }))}
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
        )}

        <div className="stage-navigation">
          <button className="btn-back" onClick={() => setIncomeStep(1)}>← Back</button>
          <button className="btn-continue" onClick={goToNextStage}>Continue →</button>
        </div>
      </div>
    );
  };

  // Render property (refinance-specific - current home)
  const renderPropertyStage = () => (
    <div className="stage-content">
      <div className="stage-header">
        <h2>Your Current Home</h2>
        <p>Tell us about the property you want to refinance</p>
      </div>

      <div className="form-card">
        <div className="form-group">
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
            placeholder="Enter your home address..."
            className="fun-input-wrapper"
          />
        </div>

        <div className="form-row">
          <div className="form-group">
            <label>Estimated Home Value</label>
            <div className="input-with-prefix">
              <span className="input-prefix">$</span>
              <input
                type="number"
                value={propertyData.homeValue || ''}
                onChange={(e) => setPropertyData(prev => ({ ...prev, homeValue: e.target.value }))}
                className="fun-input"
                placeholder="0"
              />
            </div>
            <span className="input-hint"><Icon name="home" size={14} /> Based on recent comparable sales</span>
          </div>
          <div className="form-group">
            <label>Current Mortgage Balance</label>
            <div className="input-with-prefix">
              <span className="input-prefix">$</span>
              <input
                type="number"
                value={propertyData.mortgageBalance || ''}
                onChange={(e) => setPropertyData(prev => ({ ...prev, mortgageBalance: e.target.value }))}
                className="fun-input"
                placeholder="0"
              />
            </div>
          </div>
        </div>

        {/* Equity Calculator */}
        {propertyData.homeValue && propertyData.mortgageBalance && (
          <div className="equity-display">
            <div className="equity-item">
              <span className="equity-label">Your Equity</span>
              <strong className="equity-value">
                ${(parseFloat(propertyData.homeValue) - parseFloat(propertyData.mortgageBalance)).toLocaleString()}
              </strong>
            </div>
            <div className="equity-item">
              <span className="equity-label">Loan-to-Value (LTV)</span>
              <strong className="equity-value">
                {((parseFloat(propertyData.mortgageBalance) / parseFloat(propertyData.homeValue)) * 100).toFixed(1)}%
              </strong>
            </div>
          </div>
        )}

        <div className="form-row">
          <div className="form-group">
            <label>Current Monthly Payment</label>
            <div className="input-with-prefix">
              <span className="input-prefix">$</span>
              <input
                type="number"
                value={propertyData.monthlyPayment || ''}
                onChange={(e) => setPropertyData(prev => ({ ...prev, monthlyPayment: e.target.value }))}
                className="fun-input"
                placeholder="0"
              />
            </div>
          </div>
          <div className="form-group">
            <label>Current Interest Rate</label>
            <div className="input-with-prefix">
              <input
                type="number"
                step="0.125"
                value={propertyData.currentRate || ''}
                onChange={(e) => setPropertyData(prev => ({ ...prev, currentRate: e.target.value }))}
                className="fun-input"
                placeholder="0.000"
              />
              <span className="input-suffix">%</span>
            </div>
          </div>
        </div>

        <div className="form-row">
          <div className="form-group">
            <label>Original Loan Date</label>
            <input
              type="month"
              value={propertyData.loanDate || ''}
              onChange={(e) => setPropertyData(prev => ({ ...prev, loanDate: e.target.value }))}
              className="fun-input"
            />
          </div>
          <div className="form-group">
            <label>Current Loan Term</label>
            <select
              value={propertyData.currentTerm || ''}
              onChange={(e) => setPropertyData(prev => ({ ...prev, currentTerm: e.target.value }))}
              className="fun-input"
            >
              <option value="">Select...</option>
              <option value="30">30 Year</option>
              <option value="25">25 Year</option>
              <option value="20">20 Year</option>
              <option value="15">15 Year</option>
              <option value="10">10 Year</option>
            </select>
          </div>
        </div>

        <div className="form-group">
          <label>Is there a second mortgage or HELOC?</label>
          <div className="income-cards" style={{ gridTemplateColumns: '1fr 1fr' }}>
            <div
              className={`income-card ${propertyData.hasSecondLien === 'yes' ? 'selected' : ''}`}
              onClick={() => setPropertyData(prev => ({ ...prev, hasSecondLien: 'yes' }))}
            >
              <span className="card-icon"><Icon name="clipboard" size={24} /></span>
              <span className="card-label">Yes</span>
            </div>
            <div
              className={`income-card ${propertyData.hasSecondLien === 'no' ? 'selected' : ''}`}
              onClick={() => setPropertyData(prev => ({ ...prev, hasSecondLien: 'no' }))}
            >
              <span className="card-icon"><Icon name="check" size={24} /></span>
              <span className="card-label">No</span>
            </div>
          </div>
        </div>

        {propertyData.hasSecondLien === 'yes' && (
          <div className="form-group">
            <label>Second Mortgage/HELOC Balance</label>
            <div className="input-with-prefix">
              <span className="input-prefix">$</span>
              <input
                type="number"
                value={propertyData.secondLienBalance || ''}
                onChange={(e) => setPropertyData(prev => ({ ...prev, secondLienBalance: e.target.value }))}
                className="fun-input"
                placeholder="0"
              />
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

  // Render goals (refinance-specific)
  const renderGoalsStage = () => {
    const isVeteran = declarations.veteran === 'yes' || declarations.veteran === 'active';
    const currentLoanIsVA = declarations.current_loan_type === 'va';
    const currentLoanIsFHA = declarations.current_loan_type === 'fha';
    const wantsCashOut = declarations.refi_goal === 'cash_out';

    // Calculate potential cash out
    const equity = (parseFloat(propertyData.homeValue) || 0) - (parseFloat(propertyData.mortgageBalance) || 0);
    const maxCashOut = Math.max(0, equity * 0.8); // Assume 80% LTV max

    return (
      <div className="stage-content">
        <div className="stage-header">
          <h2>Your Refinance Goals</h2>
          <p>Let's find the best option for you</p>
        </div>

        {/* Refinance Type Selection */}
        <div className="form-card">
          <h3>What type of refinance?</h3>
          <div className="income-cards">
            <div
              className={`income-card ${goalsData.refiType === 'rate_term' ? 'selected' : ''}`}
              onClick={() => setGoalsData(prev => ({ ...prev, refiType: 'rate_term' }))}
            >
              <span className="card-icon"><Icon name="trendDown" size={28} /></span>
              <span className="card-label">Rate & Term</span>
              <span className="card-desc">Lower rate or change term</span>
            </div>
            <div
              className={`income-card ${goalsData.refiType === 'cash_out' ? 'selected' : ''}`}
              onClick={() => setGoalsData(prev => ({ ...prev, refiType: 'cash_out' }))}
            >
              <span className="card-icon"><Icon name="money" size={28} /></span>
              <span className="card-label">Cash-Out</span>
              <span className="card-desc">Get cash from equity</span>
            </div>
            {(isVeteran || currentLoanIsVA) && (
              <div
                className={`income-card ${goalsData.refiType === 'va_irrrl' ? 'selected' : ''}`}
                onClick={() => setGoalsData(prev => ({ ...prev, refiType: 'va_irrrl' }))}
              >
                <span className="card-icon"><Icon name="medal" size={28} /></span>
                <span className="card-label">VA Streamline</span>
                <span className="card-desc">Fast, limited docs</span>
              </div>
            )}
            {currentLoanIsFHA && (
              <div
                className={`income-card ${goalsData.refiType === 'fha_streamline' ? 'selected' : ''}`}
                onClick={() => setGoalsData(prev => ({ ...prev, refiType: 'fha_streamline' }))}
              >
                <span className="card-icon"><Icon name="government" size={28} /></span>
                <span className="card-label">FHA Streamline</span>
                <span className="card-desc">No appraisal needed</span>
              </div>
            )}
          </div>
        </div>

        {/* Cash-Out Amount */}
        {goalsData.refiType === 'cash_out' && (
          <div className="form-card">
            <h3><Icon name="dollarSign" size={20} /> Cash-Out Amount</h3>
            <p className="section-hint">
              Based on your equity, you may be able to access up to <strong>${maxCashOut.toLocaleString()}</strong>
            </p>
            <div className="form-group">
              <label>How much cash do you need?</label>
              <div className="input-with-prefix">
                <span className="input-prefix">$</span>
                <input
                  type="number"
                  value={goalsData.cashOutAmount || ''}
                  onChange={(e) => setGoalsData(prev => ({ ...prev, cashOutAmount: e.target.value }))}
                  className="fun-input"
                  placeholder="0"
                  max={maxCashOut}
                />
              </div>
            </div>
            <div className="form-group">
              <label>What will you use the cash for?</label>
              <select
                value={goalsData.cashOutPurpose || ''}
                onChange={(e) => setGoalsData(prev => ({ ...prev, cashOutPurpose: e.target.value }))}
                className="fun-input"
              >
                <option value="">Select...</option>
                <option value="home_improvement">Home Improvements</option>
                <option value="debt_consolidation">Debt Consolidation</option>
                <option value="education">Education</option>
                <option value="investment">Investment</option>
                <option value="emergency_fund">Emergency Fund</option>
                <option value="other">Other</option>
              </select>
            </div>
          </div>
        )}

        {/* New Loan Term */}
        <div className="form-card">
          <h3>New Loan Term</h3>
          <div className="income-cards">
            <div
              className={`income-card ${goalsData.newTerm === '30' ? 'selected' : ''}`}
              onClick={() => setGoalsData(prev => ({ ...prev, newTerm: '30' }))}
            >
              <span className="card-icon"><Icon name="calendar" size={28} /></span>
              <span className="card-label">30 Year</span>
              <span className="card-desc">Lowest payment</span>
            </div>
            <div
              className={`income-card ${goalsData.newTerm === '20' ? 'selected' : ''}`}
              onClick={() => setGoalsData(prev => ({ ...prev, newTerm: '20' }))}
            >
              <span className="card-icon"><Icon name="timer" size={28} /></span>
              <span className="card-label">20 Year</span>
              <span className="card-desc">Balance</span>
            </div>
            <div
              className={`income-card ${goalsData.newTerm === '15' ? 'selected' : ''}`}
              onClick={() => setGoalsData(prev => ({ ...prev, newTerm: '15' }))}
            >
              <span className="card-icon"><Icon name="rocket" size={28} /></span>
              <span className="card-label">15 Year</span>
              <span className="card-desc">Pay off faster</span>
            </div>
          </div>
        </div>

        {/* Loan Program Selection */}
        <div className="form-card">
          <h3>Recommended Programs</h3>
          <div className="program-cards">
            {isVeteran && (
              <div
                className={`program-card va ${goalsData.program === 'va' ? 'selected' : ''}`}
                onClick={() => setGoalsData(prev => ({ ...prev, program: 'va' }))}
              >
                <span className="program-badge"><Icon name="medal" size={14} /> FOR YOU</span>
                <span className="program-name">VA</span>
                <span className="program-rate">~6.0% APR</span>
                <span className="program-note">No PMI, great rates</span>
              </div>
            )}
            <div
              className={`program-card ${goalsData.program === 'conventional' ? 'selected' : ''}`}
              onClick={() => setGoalsData(prev => ({ ...prev, program: 'conventional' }))}
            >
              <span className="program-name">Conventional</span>
              <span className="program-rate">~6.5% APR</span>
              <span className="program-note">Best for good credit</span>
            </div>
            <div
              className={`program-card ${goalsData.program === 'fha' ? 'selected' : ''}`}
              onClick={() => setGoalsData(prev => ({ ...prev, program: 'fha' }))}
            >
              <span className="program-name">FHA</span>
              <span className="program-rate">~6.25% APR</span>
              <span className="program-note">Flexible requirements</span>
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

  // Render review
  const renderReviewStage = () => {
    const newLoanAmount = goalsData.refiType === 'cash_out'
      ? (parseFloat(propertyData.mortgageBalance) || 0) + (parseFloat(goalsData.cashOutAmount) || 0)
      : (parseFloat(propertyData.mortgageBalance) || 0);

    return (
      <div className="stage-content">
        <div className="stage-header">
          <h2>Review Your Application</h2>
          <p>Let's make sure everything looks good!</p>
        </div>

        <div className="review-sections">
          <div className="review-section">
            <div className="section-header">
              <h3><Icon name="profile" size={18} /> Your Profile</h3>
              <button className="edit-link" onClick={() => setCurrentStage('profile')}>Edit</button>
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
              <button className="edit-link" onClick={() => setCurrentStage('income')}>Edit</button>
            </div>
            <div className="section-content">
              <p><strong>Type:</strong> {incomeData.primaryType}</p>
              {incomeData.employerName && <p><strong>Employer:</strong> {incomeData.employerName}</p>}
              {incomeData.annualSalary && <p><strong>Annual Income:</strong> ${parseFloat(incomeData.annualSalary).toLocaleString()}</p>}
            </div>
          </div>

          <div className="review-section">
            <div className="section-header">
              <h3><Icon name="home" size={18} /> Current Home</h3>
              <button className="edit-link" onClick={() => setCurrentStage('property')}>Edit</button>
            </div>
            <div className="section-content">
              <p><strong>Address:</strong> {propertyData.address}</p>
              <p><strong>Home Value:</strong> ${parseFloat(propertyData.homeValue || 0).toLocaleString()}</p>
              <p><strong>Current Balance:</strong> ${parseFloat(propertyData.mortgageBalance || 0).toLocaleString()}</p>
              <p><strong>Current Rate:</strong> {propertyData.currentRate}%</p>
            </div>
          </div>

          <div className="review-section">
            <div className="section-header">
              <h3><Icon name="target" size={18} /> Refinance Details</h3>
              <button className="edit-link" onClick={() => setCurrentStage('goals')}>Edit</button>
            </div>
            <div className="section-content">
              <p><strong>Type:</strong> {goalsData.refiType === 'cash_out' ? 'Cash-Out Refinance' : 'Rate & Term'}</p>
              <p><strong>New Loan Amount:</strong> ${newLoanAmount.toLocaleString()}</p>
              {goalsData.cashOutAmount && <p><strong>Cash Out:</strong> ${parseFloat(goalsData.cashOutAmount).toLocaleString()}</p>}
              <p><strong>New Term:</strong> {goalsData.newTerm} Years</p>
              <p><strong>Program:</strong> {goalsData.program?.toUpperCase()}</p>
            </div>
          </div>
        </div>

        <div className="needs-list-section">
          <h3><Icon name="clipboard" size={18} /> Your Document Checklist</h3>
          <p>We'll need these documents to process your refinance:</p>
          <ul className="needs-list">
            {needsList.map(item => (
              <li key={item.id} className="needs-item">
                <span className="needs-icon"><Icon name="document" size={16} /></span>
                <span className="needs-label">{item.label}</span>
                <span className={`needs-category ${item.category}`}>{item.category}</span>
              </li>
            ))}
          </ul>
        </div>

        <div className="stage-navigation">
          <button className="btn-back" onClick={goToPrevStage}>← Back</button>
          <button className="btn-continue" onClick={goToNextStage}>Continue →</button>
        </div>
      </div>
    );
  };

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

  // Render planning stage with mortgage questionnaire
  const renderPlanningStage = () => (
    <div className="stage-content planning-stage">
      <div className="stage-header">
        <h2>Let's Plan Your Refinance</h2>
        <p>A few quick questions to help us find the perfect loan for your situation</p>
      </div>

      {/* Mortgage Priorities - Multi-select */}
      <div className="form-card planning-section">
        <h3>{PLANNING_QUESTIONS.mortgagePriorities.question}</h3>
        <p className="section-hint">{PLANNING_QUESTIONS.mortgagePriorities.hint}</p>
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

      {/* Personal Goals - Multi-select */}
      <div className="form-card planning-section">
        <h3>{PLANNING_QUESTIONS.personalGoals.question}</h3>
        <p className="section-hint">{PLANNING_QUESTIONS.personalGoals.hint}</p>
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

      {/* Financial Philosophy - Single select */}
      <div className="form-card planning-section">
        <h3>{PLANNING_QUESTIONS.financialPhilosophy.question}</h3>
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

      {/* Tax-Deferred Retirement - Single select */}
      <div className="form-card planning-section">
        <h3>{PLANNING_QUESTIONS.taxDeferredRetirement.question}</h3>
        <p className="section-hint">{PLANNING_QUESTIONS.taxDeferredRetirement.hint}</p>
        <div className="single-select-options">
          {PLANNING_QUESTIONS.taxDeferredRetirement.options.map(option => (
            <button
              key={option.value}
              className={`single-select-option ${planningData.taxDeferredRetirement === option.value ? 'selected' : ''}`}
              onClick={() => setPlanningData(prev => ({ ...prev, taxDeferredRetirement: option.value }))}
            >
              <span className="option-icon"><Icon name={option.icon} size={22} /></span>
              <span className="option-label">{option.label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Professional Network - Multi-select */}
      <div className="form-card planning-section">
        <h3>{PLANNING_QUESTIONS.professionalNetwork.question}</h3>
        <p className="section-hint">{PLANNING_QUESTIONS.professionalNetwork.hint}</p>
        <div className="multi-select-grid compact">
          {PLANNING_QUESTIONS.professionalNetwork.options.map(option => (
            <button
              key={option.value}
              className={`multi-select-option ${planningData.professionalNetwork.includes(option.value) ? 'selected' : ''}`}
              onClick={() => togglePlanningOption('professionalNetwork', option.value)}
            >
              <span className="option-icon"><Icon name={option.icon} size={22} /></span>
              <span className="option-label">{option.label}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="stage-navigation">
        <button className="btn-back" onClick={goToPrevStage}>← Back</button>
        <button className="btn-continue" onClick={goToNextStage}>Continue →</button>
      </div>
    </div>
  );

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
    return slots.slice(0, 12);
  };

  // Render schedule stage with video and calendar
  const renderScheduleStage = () => {
    const timeSlots = generateTimeSlots();

    return (
      <div className="stage-content scheduling-page">
        <div className="scheduling-header">
          <h2>You're Almost Done!</h2>
          <p>Watch this quick video to learn what happens next, then schedule your consultation.</p>
        </div>

        <div className="video-section">
          <div className="video-container">
            <div className="video-placeholder">
              <span className="play-icon"><Icon name="play" size={32} /></span>
              <p>What to Expect: Your Refinance Journey</p>
            </div>
          </div>

          <div className="next-steps-list">
            <h3><Icon name="clipboard" size={18} /> What Happens Next</h3>
            <ol>
              <li><strong>Consultation Call</strong> - We'll review your refinance goals and answer questions</li>
              <li><strong>Rate Lock</strong> - Lock in your new rate once you're ready</li>
              <li><strong>Document Collection</strong> - Upload your documents through our secure portal</li>
              <li><strong>Appraisal</strong> - We'll order and coordinate your home appraisal</li>
              <li><strong>Closing</strong> - Sign your new loan docs and start saving!</li>
            </ol>
          </div>
        </div>

        <div className="calendar-section">
          <h3>Schedule Your Consultation</h3>

          <div className="calendar-placeholder">
            <span className="cal-icon"><Icon name="calendar" size={32} /></span>
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
              onClick={() => showMicroWinAnimation('Consultation Scheduled! 🎉 Check your email for confirmation.')}
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
  };

  // Render current stage
  const renderStage = () => {
    switch (currentStage) {
      case 'declarations': return renderDeclarationsStage();
      case 'profile': return renderProfileStage();
      case 'income': return renderIncomeStage();
      case 'property': return renderPropertyStage();
      case 'goals': return renderGoalsStage();
      case 'review': return renderReviewStage();
      case 'planning': return renderPlanningStage();
      case 'schedule': return renderScheduleStage();
      default: return renderDeclarationsStage();
    }
  };

  return (
    <div className="adaptive-urla">
      {isDemoMode && (
        <div className="demo-banner" style={{ background: 'linear-gradient(135deg, #218D8D 0%, #1a7070 100%)' }}>
          <span className="demo-badge">DEMO</span>
          Refinance Application
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
                className={`progress-chapter ${isComplete ? 'complete' : ''} ${isCurrent ? 'current' : ''}`}
                onClick={() => isComplete && setCurrentStage(stage.id)}
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
          <span className="micro-win-icon"><Icon name="checkCircle" size={24} /></span>
          <span className="micro-win-message">{microWinMessage}</span>
        </div>
      )}

      <main className="urla-content">
        {renderStage()}
      </main>

      {currentStage !== 'declarations' && needsList.length > 0 && (
        <aside className="needs-sidebar">
          <h4><Icon name="clipboard" size={16} /> Your Checklist</h4>
          <ul>
            {needsList.slice(0, 5).map(item => (
              <li key={item.id}>{item.label}</li>
            ))}
          </ul>
          {needsList.length > 5 && (
            <span className="more-items">+{needsList.length - 5} more</span>
          )}
        </aside>
      )}
    </div>
  );
}
