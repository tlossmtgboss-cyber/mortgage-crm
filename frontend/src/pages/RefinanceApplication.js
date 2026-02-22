import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import AddressAutocomplete from '../components/AddressAutocomplete';
import EmployerAutocomplete from '../components/EmployerAutocomplete';
import MortgageStatementUpload from '../components/MortgageStatementUpload';
import './AdaptiveURLA.css';
import { toast } from '../utils/toast';

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
    globe: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
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
    email: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/>
      </svg>
    ),
    phone: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/>
      </svg>
    ),
    save: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17,21 17,13 7,13 7,21"/><polyline points="7,3 7,8 15,8"/>
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
  { id: 'account', label: 'Get Started', icon: 'user', description: 'Create your account', hideFromProgress: true },
  { id: 'declarations', label: 'Your Story', icon: 'story', description: 'Quick questions' },
  { id: 'planning', label: 'Planning', icon: 'goals', description: 'Your preferences' },
  { id: 'profile', label: 'About You', icon: 'profile', description: 'The basics' },
  { id: 'income', label: 'Your Income', icon: 'income', description: 'How you earn' },
  { id: 'property', label: 'Current Home', icon: 'home', description: 'Property details' },
  { id: 'goals', label: 'Refi Goals', icon: 'target', description: 'Refinance options' },
  { id: 'review', label: 'Review', icon: 'review', description: 'Review your info' },
  { id: 'schedule', label: 'Submit', icon: 'check', description: 'Complete application' },
];

// Stages visible in progress bar (excludes account)
const VISIBLE_STAGES = STAGES.filter(s => !s.hideFromProgress);

// Generate documents needed based on user's declarations (refinance-specific) - DYNAMIC based on answers
const getRequiredDocuments = (
  declarations = {},
  assetData = {},
  profileData = {},
  incomeData = {},
  coBorrowerData = {},
  coBorrowerIncomeData = {}
) => {
  const docs = [];
  const isSelfEmployed = declarations.self_employed === 'yes' || declarations.self_employed === 'side_business';
  const hasCoBorrower = ['2', '3', '4+'].includes(declarations.borrower_count);
  const isCashOut = declarations.refi_goal === 'cash_out';
  const maximizesDeductions = declarations.write_off_expenses === 'yes';

  // Parse asset values (for refinance, may come from income stage)
  const hasCheckingOrSavings = (parseFloat(assetData.checking) || 0) > 0 || (parseFloat(assetData.savings) || 0) > 0;
  const hasInvestmentOrRetirement = (parseFloat(assetData.investments) || 0) > 0 || (parseFloat(assetData.retirement) || 0) > 0;

  // Get borrower names for personalization
  const borrowerFirstName = profileData?.firstName?.trim() || 'Primary Borrower';
  const coBorrowerFirstName = coBorrowerData?.firstName?.trim() || 'Co-Borrower';

  // Get employer names from income data
  const primaryEmployer = incomeData?.employerName?.trim() || null;
  const coBorrowerEmployer = coBorrowerIncomeData?.employerName?.trim() || null;

  // Current year for document labels
  const currentYear = new Date().getFullYear();
  const priorYear = currentYear - 1;
  const twoYearsAgo = currentYear - 2;

  // === IDENTITY DOCUMENTS ===
  // Always require government ID (driver's license or passport)
  docs.push({ id: 'id', name: `${borrowerFirstName}'s Government ID`, description: "Driver's license or passport", category: 'identity', stage: 'declarations' });

  // Citizenship-based documents
  if (declarations.citizenship_status === 'permanent_resident') {
    docs.push({ id: 'green_card', name: 'Green Card', description: 'Unexpired Permanent Resident Card', category: 'identity', stage: 'declarations' });
  }
  if (declarations.citizenship_status === 'non_permanent_resident' || declarations.citizenship_status === 'non_resident') {
    docs.push({ id: 'visa_docs', name: 'Visa Documents', description: 'Current visa and work authorization', category: 'identity', stage: 'declarations' });
  }

  // === INCOME DOCUMENTS ===
  if (isSelfEmployed) {
    // Date-based logic for self-employment documents
    const today = new Date();
    const currentYear = today.getFullYear();
    const priorYear = currentYear - 1;
    const jan28 = new Date(currentYear, 0, 28); // January 28th
    const apr15 = new Date(currentYear, 3, 15); // April 15th
    const isBeforeJan28 = today < jan28;

    if (maximizesDeductions) {
      // Heavy deductions - use bank statement program instead of tax returns
      docs.push({ id: 'business_bank_statements', name: 'Business Bank Statements', description: '12 months of business bank statements', category: 'income', stage: 'income' });
    } else {
      // Standard self-employed documentation
      if (isBeforeJan28) {
        // Before Jan 28 - prior year taxes can't be filed yet, need P&L
        docs.push({ id: 'tax_returns', name: 'Tax Returns', description: `Personal returns (${priorYear - 1})`, category: 'income', stage: 'income' });
        docs.push({ id: 'business_tax_returns', name: 'Business Tax Returns', description: `Business returns (${priorYear - 1})`, category: 'income', stage: 'income' });
        docs.push({ id: 'profit_loss', name: 'Profit & Loss Statement', description: `${priorYear} P&L (signed by applicant)`, category: 'income', stage: 'income' });
      } else if (declarations.prior_year_taxes_filed === 'yes') {
        // After Jan 28 and taxes filed - request full tax returns
        docs.push({ id: 'tax_returns', name: 'Tax Returns', description: 'Personal returns (last 2 years)', category: 'income', stage: 'income' });
        docs.push({ id: 'business_tax_returns', name: 'Business Tax Returns', description: 'Business returns (last 2 years)', category: 'income', stage: 'income' });
      } else {
        // After Jan 28 but taxes not filed - need prior year P&L
        docs.push({ id: 'tax_returns', name: 'Tax Returns', description: `Personal returns (${priorYear - 1})`, category: 'income', stage: 'income' });
        docs.push({ id: 'business_tax_returns', name: 'Business Tax Returns', description: `Business returns (${priorYear - 1})`, category: 'income', stage: 'income' });
        docs.push({ id: 'profit_loss', name: 'Profit & Loss Statement', description: `${priorYear} P&L (signed by applicant)`, category: 'income', stage: 'income' });
      }
    }

    // Articles of Incorporation for S-Corp or C-Corp
    if (declarations.business_type === 's_corp' || declarations.business_type === 'c_corp') {
      docs.push({ id: 'articles_incorporation', name: 'Articles of Incorporation', description: 'Corporate formation documents', category: 'income', stage: 'income' });
    }
  } else {
    // W-2 employee - Personalized with borrower name and employer
    const employerLabel = primaryEmployer ? ` from ${primaryEmployer}` : '';
    docs.push({ id: 'paystubs', name: `${borrowerFirstName}'s Pay Stubs${employerLabel}`, description: 'Last 30 days (most recent)', category: 'income', stage: 'income' });
    docs.push({ id: 'w2_current', name: `${borrowerFirstName}'s ${priorYear} W-2${employerLabel}`, description: `${priorYear} W-2 from employer`, category: 'income', stage: 'income' });
    docs.push({ id: 'w2_prior', name: `${borrowerFirstName}'s ${twoYearsAgo} W-2${employerLabel}`, description: `${twoYearsAgo} W-2 from employer`, category: 'income', stage: 'income' });
  }

  // === DIVORCE / CHILD SUPPORT DOCUMENTS ===
  if ((declarations.marital_status === 'divorced' || declarations.marital_status === 'separated') &&
      declarations.child_support_alimony && declarations.child_support_alimony !== 'neither') {
    docs.push({ id: 'divorce_decree', name: 'Divorce Decree', description: 'Final divorce decree', category: 'income', stage: 'declarations' });
    docs.push({ id: 'property_settlement', name: 'Property Settlement Agreement', description: 'Marital settlement agreement', category: 'income', stage: 'declarations' });
  }

  // === VETERAN DOCUMENTS ===
  if (declarations.veteran === 'yes' || declarations.veteran === 'active' || declarations.veteran === 'spouse') {
    docs.push({ id: 'va_coe', name: 'Certificate of Eligibility', description: 'VA Certificate of Eligibility (COE)', category: 'identity', stage: 'declarations' });
  }
  if (declarations.va_disability === 'pending') {
    docs.push({ id: 'va_pending_claim', name: 'VA Pending Claim', description: 'Pending VA disability claim paperwork', category: 'identity', stage: 'declarations' });
  }

  // === IRS DOCUMENTS ===
  if (declarations.irs_balance_owed === 'payment_plan') {
    docs.push({ id: 'irs_payment_arrangement', name: 'IRS Payment Arrangement', description: 'IRS installment agreement letter', category: 'income', stage: 'declarations' });
  } else if (declarations.irs_balance_owed === 'yes') {
    docs.push({ id: 'irs_payoff', name: 'IRS Payoff Statement', description: 'Current IRS balance and payoff amount', category: 'income', stage: 'declarations' });
  }

  // === RENTAL PROPERTY DOCUMENTS (for investment properties being refinanced) ===
  if (declarations.property_use === 'investment' || declarations.has_rental_income === 'yes') {
    docs.push({ id: 'rental_tax_returns', name: 'Tax Returns with Schedule E', description: 'Most recent tax returns showing rental income', category: 'income', stage: 'declarations' });
    docs.push({ id: 'lease_agreement', name: 'Lease Agreement', description: 'Current signed lease agreement', category: 'assets', stage: 'declarations' });
  }

  // === CREDIT APPLICATION DOCUMENTS ===
  if (declarations.recent_credit_applications === 'yes' && declarations.credit_application_approved === 'yes') {
    const creditType = declarations.credit_application_type;
    const creditLabels = {
      'auto_loan': 'Auto Loan Statement',
      'credit_card': 'Credit Card Statement',
      'personal_loan': 'Personal Loan Statement',
      'other': 'New Account Statement'
    };
    const label = creditLabels[creditType] || 'New Account Statement';
    docs.push({ id: 'new_credit_statement', name: label, description: 'Statement for recently opened account', category: 'assets', stage: 'declarations' });
  }

  // === BANKRUPTCY DOCUMENTS ===
  if (declarations.credit_issues === 'bankruptcy') {
    if (declarations.bankruptcy_type === 'chapter_7') {
      // Chapter 7 - only need docs if within 7 years
      if (declarations.bankruptcy_discharge_ch7 !== '8_years_or_more') {
        docs.push({ id: 'bankruptcy_docs', name: 'Bankruptcy Documents', description: 'Chapter 7 discharge papers', category: 'identity', stage: 'declarations' });
      }
    } else if (declarations.bankruptcy_type === 'chapter_13') {
      if (declarations.chapter_13_status === 'active_paying') {
        docs.push({ id: 'ch13_payment_history', name: 'Payment History', description: 'Chapter 13 trustee payment history', category: 'identity', stage: 'declarations' });
        docs.push({ id: 'ch13_court_approval', name: 'Court Approval Letter', description: 'Court approval for new mortgage', category: 'identity', stage: 'declarations' });
      } else {
        docs.push({ id: 'bankruptcy_discharge', name: 'Discharge Paperwork', description: 'Chapter 13 discharge documents', category: 'identity', stage: 'declarations' });
      }
    } else if (declarations.bankruptcy_type === 'chapter_12') {
      docs.push({ id: 'ch12_payment_history', name: '12-Month Payment History', description: 'Chapter 12 payment history', category: 'identity', stage: 'declarations' });
      docs.push({ id: 'ch12_court_approval', name: 'Court Approval Letter', description: 'Court approval letter for financing', category: 'identity', stage: 'declarations' });
    }
  }

  // === ASSET DOCUMENTS ===
  // For cash-out refinances or if user has entered asset values
  if (isCashOut || hasCheckingOrSavings) {
    docs.push({ id: 'bank_statements', name: 'Bank Statements', description: 'Last 2 months (checking/savings)', category: 'assets', stage: 'income' });
  }
  if (hasInvestmentOrRetirement) {
    docs.push({ id: 'investment_statements', name: 'Investment Statements', description: 'Retirement/brokerage accounts', category: 'assets', stage: 'income' });
  }

  // === CO-BORROWER DOCUMENTS ===
  if (hasCoBorrower) {
    docs.push({ id: 'coborrower_id', name: `${coBorrowerFirstName}'s Government ID`, description: "Driver's license or passport", category: 'identity', stage: 'profile' });
    // Co-borrower income documents with personalized labels
    const coBorrowerEmployerLabel = coBorrowerEmployer ? ` from ${coBorrowerEmployer}` : '';
    docs.push({ id: 'coborrower_paystubs', name: `${coBorrowerFirstName}'s Pay Stubs${coBorrowerEmployerLabel}`, description: 'Last 30 days (most recent)', category: 'income', stage: 'income' });
    docs.push({ id: 'coborrower_w2_current', name: `${coBorrowerFirstName}'s ${priorYear} W-2${coBorrowerEmployerLabel}`, description: `${priorYear} W-2 from employer`, category: 'income', stage: 'income' });
    docs.push({ id: 'coborrower_w2_prior', name: `${coBorrowerFirstName}'s ${twoYearsAgo} W-2${coBorrowerEmployerLabel}`, description: `${twoYearsAgo} W-2 from employer`, category: 'income', stage: 'income' });
  }

  return docs;
};

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
    id: 'citizenship_status',
    question: 'What is your citizenship status?',
    type: 'choice',
    options: [
      { value: 'us_citizen', label: 'U.S. Citizen', icon: 'check' },
      { value: 'permanent_resident', label: 'Permanent Resident (Green Card)', icon: 'document' },
      { value: 'non_permanent_resident', label: 'Non-Permanent Resident (Visa)', icon: 'globe' },
      { value: 'non_resident', label: 'Non-Resident Alien', icon: 'globe' },
    ],
    hint: 'This helps determine which loan programs you qualify for.',
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
      { value: 'c_corp', label: 'C-Corp', icon: 'building' },
      { value: 'partnership', label: 'Partnership', icon: 'users' },
    ],
    hint: 'This determines what tax documents we\'ll need.',
    showIf: { field: 'self_employed', values: ['yes', 'side_business'] },
  },
  {
    id: 'prior_year_taxes_filed',
    question: 'Have you filed your prior year tax returns?',
    type: 'choice',
    options: [
      { value: 'yes', label: 'Yes, taxes are filed', icon: 'check' },
      { value: 'no', label: 'No, not filed yet', icon: 'clock' },
      { value: 'extension', label: 'Filed an extension', icon: 'calendar' },
    ],
    hint: 'If taxes are not yet filed, we\'ll need a year-to-date Profit & Loss statement.',
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
    question: "What's the monthly payment?",
    type: 'currency',
    placeholder: '0',
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
      { value: 'chapter_12', label: 'Chapter 12 (Farm/Fisherman)', icon: 'document' },
    ],
    hint: 'Different waiting periods apply for each type.',
    showIf: { field: 'credit_issues', values: ['bankruptcy'] },
  },
  {
    id: 'bankruptcy_discharge_ch7',
    question: 'When was your Chapter 7 bankruptcy discharged?',
    type: 'choice',
    options: [
      { value: 'less_than_2_years', label: 'Less than 2 years ago', icon: 'clock' },
      { value: '2_to_4_years', label: '2-4 years ago', icon: 'calendar' },
      { value: '4_to_7_years', label: '4-7 years ago', icon: 'calendar' },
      { value: '8_years_or_more', label: '8 years ago or more', icon: 'check' },
    ],
    hint: 'Chapter 7 typically has a 2-4 year waiting period depending on loan type.',
    showIf: { field: 'bankruptcy_type', values: ['chapter_7'] },
  },
  {
    id: 'chapter_13_status',
    question: 'What is the status of your Chapter 13 bankruptcy?',
    type: 'choice',
    options: [
      { value: 'active_paying', label: 'Actively paying to trustee', icon: 'clock' },
      { value: 'completed', label: 'Completed/Discharged', icon: 'check' },
    ],
    hint: 'Active Chapter 13 plans may still qualify with court approval.',
    showIf: { field: 'bankruptcy_type', values: ['chapter_13'] },
  },
  {
    id: 'bankruptcy_discharge_ch13',
    question: 'When was your Chapter 13 bankruptcy discharged?',
    type: 'choice',
    options: [
      { value: 'less_than_2_years', label: 'Less than 2 years ago', icon: 'clock' },
      { value: '2_to_4_years', label: '2-4 years ago', icon: 'calendar' },
      { value: 'more_than_4_years', label: 'More than 4 years ago', icon: 'calendar' },
    ],
    hint: 'Chapter 13 discharge typically requires 2-4 year waiting period.',
    showIf: { field: 'chapter_13_status', values: ['completed'] },
  },
  {
    id: 'chapter_12_status',
    question: 'What is the status of your Chapter 12 bankruptcy?',
    type: 'choice',
    options: [
      { value: 'active_paying', label: 'Actively in repayment plan', icon: 'clock' },
      { value: 'completed', label: 'Completed/Discharged', icon: 'check' },
    ],
    hint: 'Chapter 12 bankruptcies require payment history and court documentation.',
    showIf: { field: 'bankruptcy_type', values: ['chapter_12'] },
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
  // Only show demo mode for explicit /apply/start - /apply/refinance is a real application entry point
  const isDemoMode = token === 'start';

  // API Configuration
  const isProduction = window.location.hostname !== 'localhost';
  const API_URL = isProduction
    ? 'https://api.perenniaai.com'
    : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

  // State
  const [currentStage, setCurrentStage] = useState('account');
  const [currentQuestionIndex, setCurrentQuestionIndex] = useState(0);
  const [declarations, setDeclarations] = useState({});
  const [profileData, setProfileData] = useState({});
  const [incomeData, setIncomeData] = useState({});
  const [incomeStep, setIncomeStep] = useState(1); // 1 = type selection, 2 = details
  const [propertyData, setPropertyData] = useState({});
  const [statementParsed, setStatementParsed] = useState(false);
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
  const [eConsentAgreed, setEConsentAgreed] = useState(false);
  const [creditAuthAgreed, setCreditAuthAgreed] = useState(false);
  const [scheduleStep, setScheduleStep] = useState(1);
  const [calendarAssignment, setCalendarAssignment] = useState(null); // Calendar assignment for scheduling
  const [bookingSlots, setBookingSlots] = useState([]);
  const [bookingSelectedDate, setBookingSelectedDate] = useState(null);
  const [bookingSelectedTime, setBookingSelectedTime] = useState('');
  const [bookingWeekStart, setBookingWeekStart] = useState(() => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    return today;
  });
  const [bookingLoading, setBookingLoading] = useState(false);
  const [bookingConfirmed, setBookingConfirmed] = useState(false);
  const [bookingError, setBookingError] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState(null);
  const [showSubmissionSuccess, setShowSubmissionSuccess] = useState(false);
  const [portalUrlForRedirect, setPortalUrlForRedirect] = useState(null);
  const portalUrlRef = useRef(null); // Ref to avoid closure issues in setTimeout

  // Account and Save Progress state
  const [userAccount, setUserAccount] = useState({
    email: '',
    authMethod: null, // 'email', 'google', 'facebook', 'linkedin', 'apple'
    isLoggedIn: false,
  });
  const [showSaveModal, setShowSaveModal] = useState(false);
  const [saveEmail, setSaveEmail] = useState('');
  const [lastSavedAt, setLastSavedAt] = useState(null);

  // Co-borrower income collection
  const [coBorrowerData, setCoBorrowerData] = useState({});
  const [coBorrowerIncomeData, setCoBorrowerIncomeData] = useState({});
  const [currentIncomeBorrower, setCurrentIncomeBorrower] = useState(1); // 1 = primary, 2 = co-borrower
  const [emailSending, setEmailSending] = useState(false);
  const [emailSent, setEmailSent] = useState(false);

  // Application slides configuration (loaded from backend)
  const [applicationConfig, setApplicationConfig] = useState(null);
  const [configLoaded, setConfigLoaded] = useState(false);

  // Keep ref in sync with state to avoid closure issues
  useEffect(() => {
    portalUrlRef.current = portalUrlForRedirect;
  }, [portalUrlForRedirect]);

  // Load application configuration from backend
  useEffect(() => {
    const loadApplicationConfig = async () => {
      try {
        const response = await fetch(`${API_URL}/api/v1/settings/application-slides`);
        if (response.ok) {
          const config = await response.json();
          setApplicationConfig(config);
        }
      } catch (error) {
        console.log('Using default application configuration');
      } finally {
        setConfigLoaded(true);
      }
    };
    loadApplicationConfig();
  }, [API_URL]);

  // Get enabled stages based on configuration
  const getEnabledStages = useCallback(() => {
    if (!applicationConfig?.stages) return STAGES;

    // Build a map of config settings by stage id
    const configMap = new Map(applicationConfig.stages.map(s => [s.id, s]));

    // Filter and order stages based on config
    return applicationConfig.stages
      .filter(configStage => configStage.enabled)
      .map(configStage => {
        const originalStage = STAGES.find(s => s.id === configStage.id);
        return originalStage ? { ...originalStage, ...configStage } : configStage;
      });
  }, [applicationConfig]);

  // Get enabled declaration questions based on configuration
  const getEnabledQuestions = useCallback(() => {
    if (!applicationConfig?.declarationQuestions) return DECLARATION_QUESTIONS;

    const enabledIds = new Set(
      applicationConfig.declarationQuestions
        .filter(q => q.enabled)
        .map(q => q.id)
    );

    return DECLARATION_QUESTIONS.filter(q => enabledIds.has(q.id));
  }, [applicationConfig]);

  // Derived values for enabled stages and questions
  const enabledStages = getEnabledStages();
  const enabledQuestions = getEnabledQuestions();
  const visibleStages = enabledStages.filter(s => !s.hideFromProgress);

  // Auto-redirect to client portal after successful submission
  useEffect(() => {
    if (showSubmissionSuccess) {
      const redirectTimer = setTimeout(() => {
        // Use ref to get latest portal URL (avoids closure capturing stale state)
        let redirectUrl = portalUrlRef.current;

        console.log('[RefinanceApplication] Redirect check - portalUrlRef:', portalUrlRef.current);

        // If no portal URL provided, construct one from current location
        if (!redirectUrl) {
          // Use perenniaai.com for production, current host for dev
          const isProduction = window.location.hostname === 'perenniaai.com' ||
                               window.location.hostname === 'www.perenniaai.com';
          const baseHost = isProduction ? 'www.perenniaai.com' : window.location.host;
          const protocol = isProduction ? 'https' : window.location.protocol.replace(':', '');

          // Try to get the LO slug from the current URL (e.g., /lo/tim-loss or /apply/tim-loss)
          const pathMatch = window.location.pathname.match(/\/(?:lo|apply)\/([^/]+)/);
          const potentialSlug = pathMatch ? pathMatch[1] : null;
          // Exclude reserved route names that aren't LO slugs
          const reservedSlugs = ['purchase', 'refinance', 'login', 'start', 'oauth', 'verify'];
          const loSlug = potentialSlug && !reservedSlugs.includes(potentialSlug.toLowerCase()) ? potentialSlug : null;

          if (loSlug) {
            // Redirect to the LO's microsite (which has client portal features)
            redirectUrl = `${protocol}://${baseHost}/lo/${loSlug}`;
          } else {
            // Check if borrower email is available for magic link
            const borrowerEmail = localStorage.getItem('borrower_email');
            if (borrowerEmail) {
              // Redirect to borrower portal with email for magic link
              redirectUrl = `${protocol}://${baseHost}/borrower-portal?email=${encodeURIComponent(borrowerEmail)}&submitted=true`;
            } else {
              // Final fallback: redirect to thank you page
              redirectUrl = `${protocol}://${baseHost}/application-submitted`;
            }
          }
          console.log('[RefinanceApplication] Fallback redirect to:', redirectUrl);
        }

        // Signal to parent iframe that submission is complete (if embedded)
        if (window.parent !== window) {
          window.parent.postMessage({ type: 'APPLICATION_SUBMITTED', portalUrl: redirectUrl }, '*');
        }

        // Redirect to the client portal
        window.location.href = redirectUrl;
      }, 3000); // 3 second delay to show success message

      return () => clearTimeout(redirectTimer);
    }
  }, [showSubmissionSuccess]);

  // Fetch calendar assignment for scheduling
  useEffect(() => {
    const fetchCalendarAssignment = async () => {
      try {
        const response = await fetch(`${API_URL}/api/v1/calendar-assignments/refinance_application`);
        if (response.ok) {
          const data = await response.json();
          setCalendarAssignment(data);
        }
      } catch (err) {
        console.error('Error fetching calendar assignment:', err);
      }
    };
    fetchCalendarAssignment();
  }, [API_URL]);

  // localStorage storage key for saving progress
  const STORAGE_KEY = `refinance_application_${token || 'anonymous'}`;

  // Auto-save to localStorage whenever data changes
  useEffect(() => {
    if (currentStage === 'account') return; // Don't save until account is set up

    const dataToSave = {
      declarations,
      profileData,
      incomeData,
      propertyData,
      goalsData,
      planningData,
      coBorrowerData,
      coBorrowerIncomeData,
      currentStage,
      userAccount,
      savedAt: new Date().toISOString(),
    };

    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(dataToSave));
      setLastSavedAt(new Date());
    } catch (err) {
      console.error('Error saving to localStorage:', err);
    }
  }, [declarations, profileData, incomeData, propertyData, goalsData, planningData, coBorrowerData, coBorrowerIncomeData, currentStage, userAccount, STORAGE_KEY]);

  // Load saved progress on mount
  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const data = JSON.parse(saved);
        if (data.userAccount?.isLoggedIn) {
          setDeclarations(data.declarations || {});
          setProfileData(data.profileData || {});
          setIncomeData(data.incomeData || {});
          setPropertyData(data.propertyData || {});
          setGoalsData(data.goalsData || {});
          setPlanningData(data.planningData || {});
          setCoBorrowerData(data.coBorrowerData || {});
          setCoBorrowerIncomeData(data.coBorrowerIncomeData || {});
          setUserAccount(data.userAccount || {});
          setCurrentStage(data.currentStage || 'declarations');
        }
      }
    } catch (err) {
      console.error('Error loading saved progress:', err);
    }
  }, [STORAGE_KEY]);

  // Handle Save Progress via email
  const handleSaveProgressEmail = async () => {
    if (!saveEmail || !saveEmail.includes('@')) return;

    try {
      // In a real implementation, this would send an email with a magic link
      console.log('Saving progress for email:', saveEmail);

      // Store the email in userAccount
      setUserAccount(prev => ({ ...prev, email: saveEmail }));
      setShowSaveModal(false);
      setSaveEmail('');

      // Show confirmation
      setMicroWinMessage('Progress saved! Check your email for a link to continue later.');
      setShowMicroWin(true);
      setTimeout(() => setShowMicroWin(false), 4000);
    } catch (err) {
      console.error('Error saving progress:', err);
    }
  };

  // AI Follow-up questions state (disabled - inline followups removed)
  const [followupAnswers, setFollowupAnswers] = useState({});
  const [activeFollowup, setActiveFollowup] = useState(null);
  const clearFollowup = () => {}; // Stub - followup feature disabled
  const checkForFollowup = async () => null; // Stub - followup feature disabled

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

  // Handle mortgage statement data extraction
  const handleMortgageStatementData = useCallback((formData) => {
    setPropertyData(prev => ({
      ...prev,
      // Property address
      address: formData.address || prev.address,
      street: formData.street || prev.street,
      city: formData.city || prev.city,
      state: formData.state || prev.state,
      zip: formData.zip || prev.zip,
      // Loan details
      mortgageBalance: formData.mortgageBalance || prev.mortgageBalance,
      monthlyPayment: formData.monthlyPayment || prev.monthlyPayment,
      currentRate: formData.currentRate || prev.currentRate,
      loanDate: formData.loanDate || prev.loanDate,
      currentTerm: formData.currentTerm ? String(formData.currentTerm) : prev.currentTerm,
      // Lender info
      lenderName: formData.lenderName || prev.lenderName,
      loanNumber: formData.loanNumber || prev.loanNumber,
      // Payment breakdown (from statement)
      principalAndInterest: formData.principalAndInterest || prev.principalAndInterest,
      propertyTaxes: formData.propertyTaxes || prev.propertyTaxes,
      insurance: formData.insurance || prev.insurance,
      pmi: formData.pmi || prev.pmi,
      hoa: formData.hoa || prev.hoa,
      escrowPayment: formData.escrowPayment || prev.escrowPayment,
    }));
    setStatementParsed(true);
  }, []);

  // Handle application submission
  const handleSubmitApplication = async () => {
    setIsSubmitting(true);
    setSubmitError(null);

    try {
      // Get loan officer ID from token if available
      let loId = null;
      if (token && token !== 'start') {
        const storedLoId = localStorage.getItem('lo_id');
        if (storedLoId) {
          loId = storedLoId;
        }
      }

      const submissionData = {
        profileData,
        incomeData,
        assetData: {}, // Refinance doesn't have asset data like purchase
        propertyData,
        declarations,
        goalsData, // Include refinance goals
        eConsentAgreed,
        creditAuthAgreed,
        loId,
        applicationType: 'refinance',
      };

      const response = await fetch(`${API_URL}/api/v1/borrower-auth/submit-application`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(submissionData),
      });

      const result = await response.json();

      if (!response.ok) {
        throw new Error(result.detail || 'Submission failed');
      }

      console.log('[RefinanceApplication] Submit response:', result);
      console.log('[RefinanceApplication] Portal URL from response:', result.data?.portal_url);

      // Store borrower email for fallback magic link
      if (profileData?.email) {
        localStorage.setItem('borrower_email', profileData.email);
      }

      // Success - show the submission success lightbox
      if (result.data?.portal_url) {
        console.log('[RefinanceApplication] Setting portal URL:', result.data.portal_url);
        setPortalUrlForRedirect(result.data.portal_url);
        portalUrlRef.current = result.data.portal_url; // Set ref immediately to avoid timing issues
      } else {
        console.warn('[RefinanceApplication] No portal_url in response, will use fallback');
      }
      setShowSubmissionSuccess(true);
    } catch (error) {
      console.error('Application submission error:', error);
      setSubmitError(error.message || 'Failed to submit application. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  // Calculate progress
  const getProgress = useCallback(() => {
    // Account stage doesn't count toward progress
    if (currentStage === 'account') return 0;

    const stageIndex = visibleStages.findIndex(s => s.id === currentStage);
    const stageProgress = (stageIndex / visibleStages.length) * 100;
    if (currentStage === 'declarations') {
      const questionProgress = (currentQuestionIndex / enabledQuestions.length) * (100 / visibleStages.length);
      return Math.round(stageProgress + questionProgress);
    }
    return Math.round(stageProgress);
  }, [currentStage, currentQuestionIndex, visibleStages, enabledQuestions]);

  // Helper to check if a question should be shown based on conditions
  const shouldShowQuestion = useCallback((question, currentDeclarations) => {
    if (!question.showIf) return true;
    const { field, values } = question.showIf;
    return values.includes(currentDeclarations[field]);
  }, []);

  // Get filtered questions based on current declarations
  const getVisibleQuestions = useCallback(() => {
    return enabledQuestions.filter(q => shouldShowQuestion(q, declarations));
  }, [declarations, shouldShowQuestion, enabledQuestions]);

  // Update needs list
  useEffect(() => {
    const newNeeds = [];

    // Government ID is always required
    newNeeds.push({ id: 'id', label: "Driver's license or passport", category: 'identity' });

    // Green Card required for non-US citizens
    if (declarations.citizenship_status && declarations.citizenship_status !== 'us_citizen') {
      newNeeds.push({ id: 'green_card', label: 'Unexpired Green Card (front & back)', category: 'identity' });

      // For visa holders, also need work authorization
      if (declarations.citizenship_status === 'non_permanent_resident') {
        newNeeds.push({ id: 'visa_docs', label: 'Visa documentation (I-94, EAD, etc.)', category: 'identity' });
      }
    }

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

    // New credit account statement (if approved)
    if (declarations.credit_application_approved === 'yes') {
      newNeeds.push({ id: 'new_account_statement', label: 'New account statement (loan/credit card)', category: 'assets' });
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

  // Handle follow-up answers submission
  const handleFollowupSubmit = (answers, trigger) => {
    // Store follow-up answers
    setFollowupAnswers(prev => ({
      ...prev,
      [trigger]: answers
    }));
    // Also merge into declarations for form submission
    setDeclarations(prev => ({
      ...prev,
      ...Object.entries(answers).reduce((acc, [key, val]) => {
        acc[`${trigger}_${key}`] = val;
        return acc;
      }, {})
    }));
    setActiveFollowup(null);
    clearFollowup();
    proceedToNextQuestion();
  };

  // Handle skipping follow-up
  const handleFollowupSkip = () => {
    setActiveFollowup(null);
    clearFollowup();
    proceedToNextQuestion();
  };

  // Handle follow-up for income/asset stages (doesn't navigate to next question)
  const handleStageFollowupSubmit = (answers, trigger) => {
    setFollowupAnswers(prev => ({
      ...prev,
      [trigger]: answers
    }));
    setActiveFollowup(null);
    clearFollowup();
  };

  const handleStageFollowupSkip = () => {
    setActiveFollowup(null);
    clearFollowup();
  };

  // Check for follow-ups when income data changes
  const handleIncomeFieldChange = async (fieldName, value, setter) => {
    setter(prev => ({ ...prev, [fieldName]: value }));

    // Trigger follow-up check for specific fields
    const triggerFields = ['businessType', 'ownershipPercent', 'rentalIncome', 'otherIncome'];
    if (triggerFields.includes(fieldName) && value) {
      const result = await checkForFollowup(
        `income_${fieldName}`,
        value,
        'refinance',
        { ...declarations, ...incomeData, [fieldName]: value }
      );
      if (result && result.needs_followup) {
        setActiveFollowup(result);
      }
    }
  };

  // Check for follow-ups when asset data changes
  const handleAssetFieldChange = async (fieldName, value, setter) => {
    setter(prev => ({ ...prev, [fieldName]: value }));

    // Trigger follow-up check for large deposits or cash-out related fields
    const triggerFields = ['largeDeposits', 'cashOutAmount', 'cashOutPurpose', 'otherAssets'];
    if (triggerFields.includes(fieldName) && value) {
      const result = await checkForFollowup(
        `asset_${fieldName}`,
        value,
        'refinance',
        { ...declarations, [fieldName]: value }
      );
      if (result && result.needs_followup) {
        setActiveFollowup(result);
      }
    }
  };

  // Check for follow-ups when goals data changes (cash-out amount/purpose)
  const handleGoalsFieldChange = async (fieldName, value, setter) => {
    setter(prev => ({ ...prev, [fieldName]: value }));

    // Trigger follow-up check for cash-out related fields
    const triggerFields = ['cashOutAmount', 'cashOutPurpose'];
    if (triggerFields.includes(fieldName) && value) {
      const result = await checkForFollowup(
        `goals_${fieldName}`,
        value,
        'refinance',
        { ...declarations, ...goalsData, [fieldName]: value }
      );
      if (result && result.needs_followup) {
        setActiveFollowup(result);
      }
    }
  };

  // Proceed to next question
  const proceedToNextQuestion = () => {
    let nextIndex = currentQuestionIndex + 1;
    while (nextIndex < enabledQuestions.length) {
      const nextQuestion = enabledQuestions[nextIndex];
      if (shouldShowQuestion(nextQuestion, declarations)) {
        setCurrentQuestionIndex(nextIndex);
        return;
      }
      nextIndex++;
    }
    // If no more questions, go to next stage
    showMicroWinAnimation('Great! Your checklist is ready!');
    setTimeout(() => setCurrentStage('profile'), 1500);
  };

  // Handle declaration answer
  const handleDeclarationAnswer = async (questionId, value) => {
    setIsAnimating(true);
    const newDeclarations = { ...declarations, [questionId]: value };
    setDeclarations(newDeclarations);

    // Check for AI follow-up questions on complex situations
    const triggerFields = ['self_employed', 'gift_funds', 'bankruptcy', 'credit_issues', 'investment_property', 'coborrower'];
    if (triggerFields.some(f => questionId.includes(f))) {
      const result = await checkForFollowup(questionId, value, 'refinance', newDeclarations);
      if (result && result.needs_followup) {
        setActiveFollowup(result);
        setIsAnimating(false);
        return; // Don't proceed to next question yet
      }
    }

    setTimeout(() => {
      setIsAnimating(false);

      // Find next visible question
      let nextIndex = currentQuestionIndex + 1;
      while (nextIndex < enabledQuestions.length) {
        const nextQuestion = enabledQuestions[nextIndex];
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
        while (nextIndex < enabledQuestions.length) {
          const nextQuestion = enabledQuestions[nextIndex];
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
      const prevQuestion = enabledQuestions[prevIndex];
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
    const currentQuestion = enabledQuestions[currentQuestionIndex];
    return visibleQuestions.findIndex(q => q.id === currentQuestion.id) + 1;
  };

  // Navigation
  const goToNextStage = () => {
    const currentIndex = enabledStages.findIndex(s => s.id === currentStage);
    if (currentIndex < enabledStages.length - 1) {
      setCurrentStage(enabledStages[currentIndex + 1].id);
      showMicroWinAnimation(getStageMicroWin(enabledStages[currentIndex].id));
    }
  };

  const goToPrevStage = () => {
    const currentIndex = enabledStages.findIndex(s => s.id === currentStage);
    if (currentIndex > 0) {
      setCurrentStage(enabledStages[currentIndex - 1].id);
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
    const question = enabledQuestions[currentQuestionIndex];
    const visibleQuestions = getVisibleQuestions();
    const visibleQuestionNum = getVisibleQuestionNumber();

    const renderQuestionInput = () => {
      if (question.type === 'currency') {
        return (
          <div className="declaration-input-container">
            <div className="currency-input-wrapper" style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '8px',
              maxWidth: '300px',
              margin: '0 auto'
            }}>
              <span style={{
                fontSize: '24px',
                fontWeight: '500',
                color: '#374151'
              }}>$</span>
              <input
                type="number"
                className="declaration-currency-input fun-input"
                placeholder={question.placeholder || '0'}
                value={declarations[question.id] || ''}
                onChange={(e) => handleInputAnswer(question.id, e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && submitInputAnswer(question.id)}
                style={{
                  textAlign: 'center',
                  fontSize: '20px',
                  fontWeight: '500',
                  flex: 1
                }}
              />
              <span style={{
                fontSize: '16px',
                fontWeight: '500',
                color: '#6b7280'
              }}>/month</span>
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
  // Check if there are multiple borrowers
  const hasMultipleBorrowers = ['2', '3', '4+'].includes(declarations.borrower_count);

  const renderProfileStage = () => (
    <div className="stage-content">
      <div className="stage-header">
        <h2>Let's get to know you</h2>
        <p>This should take about 2 minutes</p>
      </div>

      {/* Multiple Borrower Disclaimer */}
      {hasMultipleBorrowers && (
        <div className="multiple-borrower-disclaimer" style={{
          background: 'linear-gradient(135deg, #e0f2fe 0%, #bae6fd 100%)',
          border: '1px solid #0ea5e9',
          borderRadius: '12px',
          padding: '16px 20px',
          marginBottom: '24px',
          display: 'flex',
          alignItems: 'flex-start',
          gap: '12px',
        }}>
          <div style={{ color: '#0284c7', marginTop: '2px' }}>
            <Icon name="users" size={20} />
          </div>
          <div>
            <p style={{ fontWeight: '600', color: '#0369a1', margin: '0 0 4px 0', fontSize: '15px' }}>
              Multiple Borrowers Detected
            </p>
            <p style={{ color: '#0369a1', margin: 0, fontSize: '14px', lineHeight: '1.5' }}>
              Since there are multiple people on this loan application, we'll collect information for each borrower separately.
              We'll start with your information first, then move on to the next borrower.
            </p>
          </div>
        </div>
      )}

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
            <div className="form-group">
              <label>Employer Address</label>
              <input
                type="text"
                value={incomeData.employerAddress || ''}
                onChange={(e) => setIncomeData(prev => ({ ...prev, employerAddress: e.target.value }))}
                className="fun-input"
                placeholder="Auto-filled from employer selection"
              />
            </div>
            <div className="form-group">
              <label>Employer Phone</label>
              <input
                type="tel"
                value={incomeData.employerPhone || ''}
                onChange={(e) => setIncomeData(prev => ({ ...prev, employerPhone: e.target.value }))}
                className="fun-input"
                placeholder="Auto-filled from employer selection"
              />
            </div>
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
                  onChange={(e) => handleIncomeFieldChange('businessType', e.target.value, setIncomeData)}
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
                  onChange={(e) => handleIncomeFieldChange('ownershipPercent', e.target.value, setIncomeData)}
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
                  onChange={(e) => handleIncomeFieldChange('rentalIncome', e.target.value, setIncomeData)}
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
                  onChange={(e) => handleIncomeFieldChange('otherIncome', e.target.value, setIncomeData)}
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

      {/* Mortgage Statement Upload - only show if form not already filled */}
      {!statementParsed && !propertyData.mortgageBalance && (
        <MortgageStatementUpload
          onDataExtracted={handleMortgageStatementData}
          apiUrl={API_URL}
        />
      )}

      {/* Show success message if statement was parsed */}
      {statementParsed && (
        <div className="statement-parsed-notice">
          <span className="notice-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
              <polyline points="22 4 12 14.01 9 11.01" />
            </svg>
          </span>
          <span>Information imported from your mortgage statement. Please review and update if needed.</span>
        </div>
      )}

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
          <label>Current Lender</label>
          <input
            type="text"
            value={propertyData.lenderName || ''}
            onChange={(e) => setPropertyData(prev => ({ ...prev, lenderName: e.target.value }))}
            className="fun-input"
            placeholder="e.g., Wells Fargo, Chase, Rocket Mortgage"
          />
        </div>

        {/* Payment Breakdown - show if we have parsed data or user wants to enter */}
        {(statementParsed && (propertyData.principalAndInterest || propertyData.propertyTaxes || propertyData.insurance)) && (
          <div className="payment-breakdown-section">
            <h4><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg> Payment Breakdown</h4>
            <p className="section-hint">Imported from your mortgage statement</p>
            <div className="form-row">
              <div className="form-group">
                <label>Principal & Interest</label>
                <div className="input-with-prefix">
                  <span className="input-prefix">$</span>
                  <input
                    type="number"
                    value={propertyData.principalAndInterest || ''}
                    onChange={(e) => setPropertyData(prev => ({ ...prev, principalAndInterest: e.target.value }))}
                    className="fun-input"
                    placeholder="0"
                  />
                </div>
              </div>
              <div className="form-group">
                <label>Property Taxes</label>
                <div className="input-with-prefix">
                  <span className="input-prefix">$</span>
                  <input
                    type="number"
                    value={propertyData.propertyTaxes || ''}
                    onChange={(e) => setPropertyData(prev => ({ ...prev, propertyTaxes: e.target.value }))}
                    className="fun-input"
                    placeholder="0"
                  />
                </div>
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label>Homeowner's Insurance</label>
                <div className="input-with-prefix">
                  <span className="input-prefix">$</span>
                  <input
                    type="number"
                    value={propertyData.insurance || ''}
                    onChange={(e) => setPropertyData(prev => ({ ...prev, insurance: e.target.value }))}
                    className="fun-input"
                    placeholder="0"
                  />
                </div>
              </div>
              <div className="form-group">
                <label>PMI / HOA</label>
                <div className="input-with-prefix">
                  <span className="input-prefix">$</span>
                  <input
                    type="number"
                    value={(parseFloat(propertyData.pmi || 0) + parseFloat(propertyData.hoa || 0)) || ''}
                    onChange={(e) => setPropertyData(prev => ({ ...prev, pmi: e.target.value, hoa: '' }))}
                    className="fun-input"
                    placeholder="0"
                  />
                </div>
              </div>
            </div>
          </div>
        )}

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

        {/* Preliminary Disclaimer */}
        <div className="preliminary-disclaimer" style={{
          background: 'linear-gradient(135deg, #fef3c7 0%, #fde68a 100%)',
          border: '1px solid #f59e0b',
          borderRadius: '12px',
          padding: '16px 20px',
          marginBottom: '24px',
          display: 'flex',
          alignItems: 'flex-start',
          gap: '12px',
        }}>
          <div style={{ color: '#d97706', marginTop: '2px' }}>
            <Icon name="info" size={20} />
          </div>
          <div>
            <p style={{ fontWeight: '600', color: '#92400e', margin: '0 0 4px 0', fontSize: '15px' }}>
              Preliminary Estimates
            </p>
            <p style={{ color: '#92400e', margin: 0, fontSize: '14px', lineHeight: '1.5' }}>
              The numbers shown below are estimates based on current market conditions and the information you've provided.
              Your loan officer will review these details with you and provide personalized, accurate figures based on your specific situation.
            </p>
          </div>
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
                  onChange={(e) => handleGoalsFieldChange('cashOutAmount', e.target.value, setGoalsData)}
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
                onChange={(e) => handleGoalsFieldChange('cashOutPurpose', e.target.value, setGoalsData)}
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

        <div className="stage-navigation">
          <button className="btn-back" onClick={goToPrevStage}>← Back</button>
          <button className="btn-continue" onClick={goToNextStage}>Continue →</button>
        </div>
      </div>
    );
  };

  // Render review
  const renderReviewStage = () => {
    const homeValue = parseFloat(propertyData.homeValue) || 0;
    const currentBalance = parseFloat(propertyData.mortgageBalance) || 0;
    const equity = homeValue - currentBalance;
    const newLoanAmount = goalsData.refiType === 'cash_out'
      ? currentBalance + (parseFloat(goalsData.cashOutAmount) || 0)
      : currentBalance;

    return (
      <div className="stage-content review-stage">
        <div className="stage-header">
          <h2>Review Your Application</h2>
          <p>Almost there! Review your information below and make any edits needed.</p>
        </div>

        {/* Summary Hero Card */}
        <div className="review-hero-card">
          <div className="hero-icon-wrapper">
            <Icon name="check" size={32} />
          </div>
          <div className="hero-content">
            <h3>Your Refinance Summary</h3>
            <div className="hero-stats">
              <div className="hero-stat">
                <span className="stat-label">Home Value</span>
                <span className="stat-value">${homeValue.toLocaleString()}</span>
              </div>
              <div className="hero-stat-divider"></div>
              <div className="hero-stat">
                <span className="stat-label">Current Balance</span>
                <span className="stat-value">${currentBalance.toLocaleString()}</span>
              </div>
              <div className="hero-stat-divider"></div>
              <div className="hero-stat">
                <span className="stat-label">Your Equity</span>
                <span className="stat-value highlight">${equity.toLocaleString()}</span>
              </div>
            </div>
          </div>
        </div>

        <div className="review-grid">
          {/* Profile Card */}
          <div className="review-card">
            <div className="card-header">
              <div className="card-icon profile-icon">
                <Icon name="profile" size={24} />
              </div>
              <div className="card-title">
                <h4>Personal Information</h4>
                <span className="card-subtitle">Your contact details</span>
              </div>
              <button className="edit-btn-modern" onClick={() => setCurrentStage('profile')}>
                <Icon name="edit" size={16} />
                <span>Edit</span>
              </button>
            </div>
            <div className="card-body">
              <div className="info-row">
                <Icon name="profile" size={16} />
                <span className="info-label">Full Name</span>
                <span className="info-value">{profileData.firstName} {profileData.lastName}</span>
              </div>
              <div className="info-row">
                <Icon name="email" size={16} />
                <span className="info-label">Email</span>
                <span className="info-value">{profileData.email}</span>
              </div>
              <div className="info-row">
                <Icon name="phone" size={16} />
                <span className="info-label">Phone</span>
                <span className="info-value">{profileData.phone}</span>
              </div>
            </div>
          </div>

          {/* Income Card */}
          <div className="review-card">
            <div className="card-header">
              <div className="card-icon income-icon">
                <Icon name="briefcase" size={24} />
              </div>
              <div className="card-title">
                <h4>Employment & Income</h4>
                <span className="card-subtitle">Your income sources</span>
              </div>
              <button className="edit-btn-modern" onClick={() => setCurrentStage('income')}>
                <Icon name="edit" size={16} />
                <span>Edit</span>
              </button>
            </div>
            <div className="card-body">
              <div className="info-row">
                <Icon name="briefcase" size={16} />
                <span className="info-label">Employment Type</span>
                <span className="info-value capitalize">{incomeData.primaryType?.replace('_', ' ') || 'Not specified'}</span>
              </div>
              {incomeData.employerName && (
                <div className="info-row">
                  <Icon name="building" size={16} />
                  <span className="info-label">Employer</span>
                  <span className="info-value">{incomeData.employerName}</span>
                </div>
              )}
              {incomeData.annualSalary && (
                <div className="info-row highlight-row">
                  <Icon name="dollarSign" size={16} />
                  <span className="info-label">Annual Income</span>
                  <span className="info-value">${parseFloat(incomeData.annualSalary).toLocaleString()}</span>
                </div>
              )}
            </div>
          </div>

          {/* Property Card */}
          <div className="review-card">
            <div className="card-header">
              <div className="card-icon property-icon">
                <Icon name="home" size={24} />
              </div>
              <div className="card-title">
                <h4>Current Property</h4>
                <span className="card-subtitle">Property being refinanced</span>
              </div>
              <button className="edit-btn-modern" onClick={() => setCurrentStage('property')}>
                <Icon name="edit" size={16} />
                <span>Edit</span>
              </button>
            </div>
            <div className="card-body">
              <div className="info-row">
                <Icon name="mapPin" size={16} />
                <span className="info-label">Address</span>
                <span className="info-value">{propertyData.address || 'Not specified'}</span>
              </div>
              <div className="info-row">
                <Icon name="home" size={16} />
                <span className="info-label">Home Value</span>
                <span className="info-value">${homeValue.toLocaleString()}</span>
              </div>
              <div className="info-row">
                <Icon name="dollarSign" size={16} />
                <span className="info-label">Current Balance</span>
                <span className="info-value">${currentBalance.toLocaleString()}</span>
              </div>
              <div className="info-row">
                <Icon name="trendDown" size={16} />
                <span className="info-label">Current Rate</span>
                <span className="info-value">{propertyData.currentRate || '0'}%</span>
              </div>
              {propertyData.lenderName && (
                <div className="info-row">
                  <Icon name="building" size={16} />
                  <span className="info-label">Current Lender</span>
                  <span className="info-value">{propertyData.lenderName}</span>
                </div>
              )}
            </div>
          </div>

          {/* Refinance Goals Card */}
          <div className="review-card">
            <div className="card-header">
              <div className="card-icon goals-icon">
                <Icon name="target" size={24} />
              </div>
              <div className="card-title">
                <h4>Refinance Goals</h4>
                <span className="card-subtitle">Your refinance objectives</span>
              </div>
              <button className="edit-btn-modern" onClick={() => setCurrentStage('goals')}>
                <Icon name="edit" size={16} />
                <span>Edit</span>
              </button>
            </div>
            <div className="card-body">
              <div className="info-row">
                <Icon name="document" size={16} />
                <span className="info-label">Refinance Type</span>
                <span className="info-value capitalize">{goalsData.refiType === 'cash_out' ? 'Cash-Out Refinance' : goalsData.refiType?.replace('_', ' ') || 'Rate & Term'}</span>
              </div>
              {goalsData.refiType === 'cash_out' && goalsData.cashOutAmount && (
                <div className="info-row highlight-row">
                  <Icon name="money" size={16} />
                  <span className="info-label">Cash Out Amount</span>
                  <span className="info-value">${parseFloat(goalsData.cashOutAmount).toLocaleString()}</span>
                </div>
              )}
              <div className="info-row">
                <Icon name="dollarSign" size={16} />
                <span className="info-label">New Loan Amount</span>
                <span className="info-value">${newLoanAmount.toLocaleString()}</span>
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

  // Render schedule stage with calendar, e-consent and credit authorization
  const renderScheduleStage = () => {
    const timeSlots = generateTimeSlots();

    // Step 1: Calendar Selection
    if (scheduleStep === 1) {
      const bookingSlug = calendarAssignment?.booking_link_slug;
      const calendlyUrl = calendarAssignment?.calendly_url;

      // Booking link helpers
      const getWeekDates = () => {
        const dates = [];
        const start = new Date(bookingWeekStart);
        start.setHours(0, 0, 0, 0);
        for (let i = 0; i < 7; i++) {
          const d = new Date(start);
          d.setDate(start.getDate() + i);
          dates.push(d);
        }
        return dates;
      };

      const isPastDate = (d) => {
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        return d < today;
      };

      const isTodayDate = (d) => d.toDateString() === new Date().toDateString();

      const formatDayName = (d) => d.toLocaleDateString('en-US', { weekday: 'short' }).toUpperCase();
      const formatDayNumber = (d) => d.getDate();
      const formatMonth = (d) => d.toLocaleDateString('en-US', { month: 'short' }).toUpperCase();
      const formatSlotTime = (timeStr) => {
        const dt = new Date(timeStr);
        return dt.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
      };

      const prevWeek = () => {
        const newStart = new Date(bookingWeekStart);
        newStart.setDate(bookingWeekStart.getDate() - 7);
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        if (newStart >= today) setBookingWeekStart(newStart);
      };

      const nextWeek = () => {
        const newStart = new Date(bookingWeekStart);
        newStart.setDate(bookingWeekStart.getDate() + 7);
        setBookingWeekStart(newStart);
      };

      const fetchBookingSlots = async (date) => {
        setBookingLoading(true);
        setBookingError(null);
        try {
          const dateStr = date.toISOString().split('T')[0];
          const response = await fetch(
            `${API_URL}/api/v1/scheduler/public/book/${bookingSlug}/slots?date=${dateStr}`
          );
          if (response.ok) {
            const data = await response.json();
            const slots = (data.available_slots || []).map(slot => ({
              ...slot,
              start_time: slot.start,
              display: formatSlotTime(slot.start)
            }));
            setBookingSlots(slots);
            if (slots.length > 0) setBookingSelectedTime(slots[0].start_time);
            else setBookingSelectedTime('');
          }
        } catch (err) {
          console.error('Error fetching booking slots:', err);
          setBookingError('Failed to load available times');
        } finally {
          setBookingLoading(false);
        }
      };

      const handleDateSelect = (date) => {
        setBookingSelectedDate(date);
        setBookingSelectedTime('');
        setBookingSlots([]);
        fetchBookingSlots(date);
      };

      const handleConfirmBooking = async () => {
        if (!bookingSelectedTime) return;
        setBookingLoading(true);
        setBookingError(null);
        try {
          const response = await fetch(`${API_URL}/api/v1/scheduler/public/book/${bookingSlug}/confirm`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              start_time: bookingSelectedTime,
              duration_minutes: 30,
              attendee_name: `${profileData?.firstName || ''} ${profileData?.lastName || ''}`.trim() || 'Applicant',
              attendee_email: profileData?.email || '',
              attendee_phone: profileData?.phone || '',
              notes: 'Booked from Refinance Application',
              meeting_mode: 'video'
            })
          });

          if (!response.ok) {
            const data = await response.json();
            throw new Error(data.detail || 'Failed to book appointment');
          }

          setBookingConfirmed(true);
          showMicroWinAnimation('Consultation Scheduled!');
          setScheduleStep(2);
        } catch (err) {
          console.error('Error confirming booking:', err);
          setBookingError(err.message || 'Failed to book appointment');
        } finally {
          setBookingLoading(false);
        }
      };

      const weekDates = bookingSlug ? getWeekDates() : [];

      return (
        <div className="stage-content scheduling-page">
          <div className="scheduling-header">
            <h2>Schedule Your Consultation</h2>
            <p>Let's find a time that works for you to discuss your refinance options.</p>
          </div>

          <div className="calendar-section">
            {bookingSlug ? (
              // Native booking link slot picker
              <div className="booking-slot-picker">
                <h4>Pick a Date</h4>
                <div className="booking-week-picker">
                  <button className="week-nav-btn" onClick={prevWeek} disabled={isPastDate(weekDates[0])}>
                    &#8249;
                  </button>
                  <div className="booking-week-dates">
                    {weekDates.map((date, idx) => {
                      const disabled = isPastDate(date);
                      const selected = bookingSelectedDate && date.toDateString() === bookingSelectedDate.toDateString();
                      return (
                        <button
                          key={idx}
                          className={`booking-date-card ${selected ? 'selected' : ''} ${disabled ? 'disabled' : ''} ${isTodayDate(date) ? 'today' : ''}`}
                          onClick={() => !disabled && handleDateSelect(date)}
                          disabled={disabled}
                        >
                          <span className="booking-day-name">{formatDayName(date)}</span>
                          <span className="booking-day-number">{formatDayNumber(date)}</span>
                          <span className="booking-month">{formatMonth(date)}</span>
                        </button>
                      );
                    })}
                  </div>
                  <button className="week-nav-btn" onClick={nextWeek}>
                    &#8250;
                  </button>
                </div>

                {bookingSelectedDate && (
                  <div className="booking-time-section">
                    <h4>Pick a Time</h4>
                    {bookingLoading ? (
                      <div className="booking-loading">Loading available times...</div>
                    ) : bookingError ? (
                      <div className="booking-error">{bookingError}</div>
                    ) : bookingSlots.length === 0 ? (
                      <div className="booking-no-slots">No times available for this date. Try another day.</div>
                    ) : (
                      <>
                        <div className="booking-time-grid">
                          {bookingSlots.map((slot, idx) => (
                            <button
                              key={idx}
                              className={`booking-time-btn ${bookingSelectedTime === slot.start_time ? 'selected' : ''}`}
                              onClick={() => setBookingSelectedTime(slot.start_time)}
                            >
                              {slot.display}
                            </button>
                          ))}
                        </div>

                        <button
                          className="btn-schedule"
                          disabled={!bookingSelectedTime || bookingLoading}
                          onClick={handleConfirmBooking}
                        >
                          {bookingLoading ? 'Booking...' : 'Confirm Appointment'}
                        </button>
                      </>
                    )}
                  </div>
                )}
              </div>
            ) : calendlyUrl ? (
              // Show Calendly embed when configured
              <div className="calendly-embed-container">
                <iframe
                  src={`${calendlyUrl}?hide_gdpr_banner=1&hide_event_type_details=1`}
                  width="100%"
                  height="630"
                  frameBorder="0"
                  title="Schedule Consultation"
                  style={{ minWidth: '320px', borderRadius: '8px' }}
                ></iframe>
                <div className="calendly-skip-option">
                  <p>After scheduling, click Continue to proceed with your application.</p>
                  <button
                    className="btn-schedule"
                    onClick={() => {
                      showMicroWinAnimation('Moving to next step!');
                      setScheduleStep(2);
                    }}
                  >
                    Continue →
                  </button>
                </div>
              </div>
            ) : (
              // Fallback to mock time slots when nothing configured
              <div className="calendar-placeholder">
                <span className="cal-icon"><Icon name="calendar" size={48} /></span>
                <h4>Pick a Time That Works For You</h4>
                <p>We want to coordinate a time to review your refinance options. Choose a time that is most convenient for you.</p>

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
            )}
          </div>

          <div className="stage-navigation">
            <button className="btn-back" onClick={goToPrevStage}>← Back</button>
          </div>
        </div>
      );
    }

    // Step 2: E-Consent Page
    if (scheduleStep === 2) {
      return (
        <div className="stage-content scheduling-page">
          <div className="scheduling-header">
            <h2>E-Consent Documentation</h2>
            <p>Please review and consent to receive documents electronically.</p>
          </div>

          <div className="econsent-section econsent-full-page">
            <div className="econsent-content">
              <p className="econsent-intro">
                To use electronic signatures and receive documents electronically in connection with your use of this
                platform, you must read and consent to the terms outlined in this document, which require your ability to
                access and retain electronic documents.
              </p>

              <div className="econsent-scrollbox">
                <p>
                  This eConsent, if you provide it, applies to your use of this Platform on any Access Device, including a
                  desktop, laptop, tablet, mobile, or any other electronic device, and to any Document, including loan
                  documents, disclosures (initial disclosures, pre-close disclosures, closing disclosures), records, and servicing
                  notices, and any other loan documents that we provide to you in electronic form.
                </p>

                <p>
                  If you provide eConsent, we will be able to provide electronic Documents to you within this platform, in
                  other portals, and/or through other methods we may use for delivery of electronic Documents. With Your
                  eConsent, You will also be able to sign and authorize these Documents electronically, rather than on paper.
                  Anytime you are signing using a platform contracted with nCino Mortgage, you will be prompted to provide
                  eConsent again.
                </p>

                <p>
                  Before We can engage in this transaction electronically, it is important that You understand Your rights and
                  responsibilities. Please read the following and affirm Your consent to conduct business with Us electronically.
                  For purposes of this eConsent Agreement, 'You' and 'Your' mean the borrower(s) under the applicable loan to
                  which such Documents apply, and 'We', 'Our' and 'Us' mean the applicable mortgage broker(s), loan
                  processor(s), or mortgage banker(s) with whom You are transacting business for such loan(s).
                </p>

                <h4>Your Consent</h4>
                <p>
                  Your consent to participate in this transaction electronically will apply to all Loan Documents for the
                  applicable loans for which You are applying. If You provide Your consent by clicking the 'I agree'
                  button at the bottom of the page, We will conduct this transaction electronically, instead of providing
                  You with the Loan Documents in paper form.
                </p>
                <p>
                  If a document related to Your loan is not available in electronic form, a paper copy will be provided to
                  You free of charge.
                </p>
                <p>
                  Conducting this transaction electronically is an option. If You choose not to receive Documents
                  electronically, paper Documents will be mailed to You. Additionally: You will not be required to pay a
                  fee for receiving paper copies of the Documents.
                </p>

                <h4>Withdrawal of Consent</h4>
                <p>
                  You have the right to withdraw Your consent at any time. By declining or revoking Your consent to
                  receive Documents electronically, We will provide You with the Documents in paper form.
                </p>
                <p>
                  If You originally consent to receive Documents electronically, but later decide to withdraw Your
                  consent, You can do so by clicking on the 'I do not agree' button, or by contacting Us by phone.
                </p>
                <p>
                  If You originally consent to receive Documents electronically, but later withdraw Your consent, You
                  will not be required to pay a fee for withdrawing consent and receiving paper copies of the Documents.
                </p>

                <h4>Obtaining Paper Copies</h4>
                <p>
                  After Your consent is given, You may request from Us paper copies of Your Loan Documents by contacting Us.
                  If You request paper copies of the Loan Documents, You will not be required to pay a fee for receiving
                  paper copies of the Loan Documents.
                </p>

                <h4>System Requirements</h4>
                <p>
                  In order to receive Documents electronically, You must have a computer with Internet access and an
                  Internet email account and address; an Internet browser using 128-bit encryption or higher, Adobe
                  Acrobat 7.0 or higher, SSL encryption and access to a printer or the ability to download information in
                  order to keep copies of Your Documents electronically for Your records.
                </p>
                <p>
                  If the software or hardware requirements change in the future, and You are unable to continue receiving
                  Documents electronically, paper copies of such Loan Documents will be mailed to You once You
                  notify Us that You are no longer able to access the Documents electronically because of the changed
                  requirements. We will use commercially reasonable efforts to notify You before such requirements
                  change. If You choose to withdraw Your consent upon notification of the change, You will be able to
                  do so without penalty.
                </p>

                <h4>How Can We Reach You</h4>
                <p>
                  You must promptly notify Us if there is a change in Your email address or in other information needed
                  to contact You electronically.
                </p>
                <p>
                  We will not assume liability for non-receipt of notification of the availability of Documents
                  electronically in the event Your email address on file is invalid; Your email or Internet service provider
                  filters the notification as 'spam' or 'junk mail'; there is a malfunction in Your computer, browser, Internet
                  service and/or software; or for other reasons beyond Our control.
                </p>
              </div>

              <div className="econsent-actions">
                <button
                  className={`econsent-btn agree ${eConsentAgreed ? 'selected' : ''}`}
                  onClick={() => setEConsentAgreed(true)}
                >
                  <Icon name="check" size={18} />
                  I Agree
                </button>
                <button
                  className="econsent-btn disagree"
                  onClick={() => {
                    setEConsentAgreed(false);
                    toast.success('You have chosen not to consent to electronic documents. Paper documents will be mailed to you. You can still proceed with your application.');
                  }}
                >
                  I Do Not Agree
                </button>
              </div>
            </div>
          </div>

          <div className="stage-navigation">
            <button className="btn-back" onClick={() => setScheduleStep(1)}>← Back</button>
            <button
              className="btn-continue"
              disabled={!eConsentAgreed}
              onClick={() => setScheduleStep(3)}
            >
              {eConsentAgreed ? 'Continue →' : 'Please Accept E-Consent to Continue'}
            </button>
          </div>
        </div>
      );
    }

    // Step 3: Credit Authorization Page
    if (scheduleStep === 3) {
      return (
        <div className="stage-content scheduling-page">
          <div className="scheduling-header">
            <h2>Credit Authorization</h2>
            <p>Please authorize us to check your credit to provide accurate refinance options.</p>
          </div>

          <div className="econsent-section credit-auth-section econsent-full-page">
            <div className="econsent-content">
              <p className="econsent-intro">
                Your credit information will help us understand more about your personal and financial background and
                ensure we give you the most accurate refinance options. To help us, we need the following authorization:
              </p>

              <div className="credit-auth-box">
                <p>
                  I authorize my Lender to perform a credit check, via either a soft or hard pull of my credit; I understand this
                  may affect my credit score. I acknowledge that any owner of a completed loan, its servicers, successors and
                  assigns, may verify or re-verify any information contained in this form or obtain any information or data
                  relating to a completed loan, for any legitimate purpose, through any source, including a source named in this
                  form or a consumer reporting agency.
                </p>
              </div>

              <div className="econsent-actions">
                <button
                  className={`econsent-btn agree ${creditAuthAgreed ? 'selected' : ''}`}
                  onClick={() => setCreditAuthAgreed(true)}
                >
                  <Icon name="check" size={18} />
                  I Authorize
                </button>
                <button
                  className="econsent-btn disagree"
                  onClick={() => {
                    setCreditAuthAgreed(false);
                    toast.error('Credit authorization is required to process your refinance application. Without it, we cannot verify your creditworthiness.');
                  }}
                >
                  I Do Not Authorize
                </button>
              </div>
            </div>
          </div>

          {submitError && (
            <div className="error-message" style={{
              color: '#dc3545',
              backgroundColor: '#f8d7da',
              padding: '12px 16px',
              borderRadius: '8px',
              marginBottom: '16px',
              textAlign: 'center'
            }}>
              {submitError}
            </div>
          )}

          <div className="submit-section">
            <button
              className="btn-submit"
              disabled={!creditAuthAgreed || isSubmitting}
              onClick={handleSubmitApplication}
            >
              {isSubmitting
                ? 'Submitting...'
                : creditAuthAgreed
                  ? 'Submit Application'
                  : 'Please Authorize Credit Check to Submit'}
            </button>
          </div>

          <div className="stage-navigation">
            <button className="btn-back" onClick={() => setScheduleStep(2)} disabled={isSubmitting}>← Back</button>
          </div>
        </div>
      );
    }

    // Default: Confirmation (shouldn't typically reach here as we redirect after submit)
    return (
      <div className="stage-content scheduling-page confirmation-page">
        <div className="scheduling-header">
          <div className="success-icon">
            <Icon name="check" size={48} />
          </div>
          <h2>Application Submitted!</h2>
          <p>Congratulations! Your refinance application has been successfully submitted.</p>
        </div>

        <div className="next-steps-list" style={{ maxWidth: '600px', margin: '0 auto' }}>
          <h3><Icon name="clipboard" size={18} /> What Happens Next</h3>
          <ol>
            <li><strong>Consultation Call</strong> - We'll review your refinance goals and answer questions</li>
            <li><strong>Rate Lock</strong> - Lock in your new rate once you're ready</li>
            <li><strong>Document Collection</strong> - Upload your documents through our secure portal</li>
            <li><strong>Appraisal</strong> - We'll order and coordinate your home appraisal</li>
            <li><strong>Closing</strong> - Sign your new loan docs and start saving!</li>
          </ol>
        </div>

        <p style={{ textAlign: 'center', marginTop: '24px', color: '#666' }}>
          Redirecting you to your client portal...
        </p>
      </div>
    );
  };

  // Render Account Stage (Get Started)
  const renderAccountStage = () => {
    const handleSocialAuth = (provider) => {
      // Redirect to OAuth connect endpoint
      const returnUrl = encodeURIComponent(window.location.href);
      window.location.href = `${API_URL}/api/v1/borrower-auth/${provider}/connect?return_url=${returnUrl}`;
    };

    const handleEmailContinue = async () => {
      if (!userAccount.email || !userAccount.email.includes('@')) {
        toast.error('Please enter a valid email address');
        return;
      }

      setEmailSending(true);
      try {
        const response = await fetch(`${API_URL}/api/v1/borrower-auth/email/request`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            email: userAccount.email,
            first_name: '',
            last_name: ''
          })
        });

        if (response.ok) {
          setEmailSent(true);
        } else {
          const data = await response.json();
          toast.error(data.detail || 'Failed to send login link. Please try again.');
        }
      } catch (error) {
        console.error('Email login error:', error);
        toast.error('Failed to send login link. Please try again.');
      } finally {
        setEmailSending(false);
      }
    };

    return (
      <div className="stage-content" style={{ maxWidth: '500px', margin: '0 auto', padding: '40px 20px' }}>
        <div style={{ textAlign: 'center', marginBottom: '40px' }}>
          <h2 style={{ fontSize: '28px', fontWeight: '600', color: '#1a365d', marginBottom: '8px' }}>
            Let's Get Started
          </h2>
          <p style={{ color: '#64748b', fontSize: '16px' }}>
            Create an account to save your progress and continue anytime
          </p>
        </div>

        {/* Social Login Buttons */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginBottom: '24px' }}>
          <button
            onClick={() => handleSocialAuth('google')}
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '12px',
              padding: '14px 20px', borderRadius: '12px', border: '1px solid #e2e8f0',
              background: 'white', cursor: 'pointer', fontSize: '15px', fontWeight: '500',
              transition: 'all 0.2s', color: '#374151',
            }}
            onMouseOver={(e) => e.target.style.background = '#f8fafc'}
            onMouseOut={(e) => e.target.style.background = 'white'}
          >
            <svg width="20" height="20" viewBox="0 0 24 24">
              <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
              <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
              <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
              <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
            </svg>
            Continue with Google
          </button>

          <button
            onClick={() => handleSocialAuth('facebook')}
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '12px',
              padding: '14px 20px', borderRadius: '12px', border: 'none',
              background: '#1877F2', cursor: 'pointer', fontSize: '15px', fontWeight: '500',
              color: 'white', transition: 'all 0.2s',
            }}
            onMouseOver={(e) => e.target.style.background = '#1565D8'}
            onMouseOut={(e) => e.target.style.background = '#1877F2'}
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="white">
              <path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"/>
            </svg>
            Continue with Facebook
          </button>

          <button
            onClick={() => handleSocialAuth('linkedin')}
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '12px',
              padding: '14px 20px', borderRadius: '12px', border: 'none',
              background: '#0A66C2', cursor: 'pointer', fontSize: '15px', fontWeight: '500',
              color: 'white', transition: 'all 0.2s',
            }}
            onMouseOver={(e) => e.target.style.background = '#004182'}
            onMouseOut={(e) => e.target.style.background = '#0A66C2'}
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="white">
              <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/>
            </svg>
            Continue with LinkedIn
          </button>

          <button
            onClick={() => handleSocialAuth('apple')}
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '12px',
              padding: '14px 20px', borderRadius: '12px', border: 'none',
              background: '#000000', cursor: 'pointer', fontSize: '15px', fontWeight: '500',
              color: 'white', transition: 'all 0.2s',
            }}
            onMouseOver={(e) => e.target.style.background = '#333333'}
            onMouseOut={(e) => e.target.style.background = '#000000'}
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="white">
              <path d="M18.71 19.5c-.83 1.24-1.71 2.45-3.05 2.47-1.34.03-1.77-.79-3.29-.79-1.53 0-2 .77-3.27.82-1.31.05-2.3-1.32-3.14-2.53C4.25 17 2.94 12.45 4.7 9.39c.87-1.52 2.43-2.48 4.12-2.51 1.28-.02 2.5.87 3.29.87.78 0 2.26-1.07 3.81-.91.65.03 2.47.26 3.64 1.98-.09.06-2.17 1.28-2.15 3.81.03 3.02 2.65 4.03 2.68 4.04-.03.07-.42 1.44-1.38 2.83M13 3.5c.73-.83 1.94-1.46 2.94-1.5.13 1.17-.34 2.35-1.04 3.19-.69.85-1.83 1.51-2.95 1.42-.15-1.15.41-2.35 1.05-3.11z"/>
            </svg>
            Continue with Apple
          </button>
        </div>

        {/* Divider */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px', margin: '24px 0' }}>
          <div style={{ flex: 1, height: '1px', background: '#e2e8f0' }}></div>
          <span style={{ color: '#94a3b8', fontSize: '14px' }}>or</span>
          <div style={{ flex: 1, height: '1px', background: '#e2e8f0' }}></div>
        </div>

        {/* Email Input */}
        {emailSent ? (
          <div style={{
            textAlign: 'center',
            padding: '24px',
            background: '#f0fdf4',
            borderRadius: '12px',
            border: '1px solid #bbf7d0'
          }}>
            <div style={{ fontSize: '48px', marginBottom: '16px' }}>✉️</div>
            <h3 style={{ margin: '0 0 8px', color: '#166534', fontSize: '18px' }}>Check Your Email</h3>
            <p style={{ margin: '0 0 16px', color: '#15803d', fontSize: '14px' }}>
              We sent a login link to <strong>{userAccount.email}</strong>
            </p>
            <p style={{ margin: 0, color: '#6b7280', fontSize: '13px' }}>
              Click the link in the email to continue your application.
            </p>
            <button
              onClick={() => setEmailSent(false)}
              style={{
                marginTop: '16px',
                background: 'transparent',
                border: 'none',
                color: '#0ea5e9',
                cursor: 'pointer',
                fontSize: '14px',
                textDecoration: 'underline'
              }}
            >
              Use a different email
            </button>
          </div>
        ) : (
          <>
            <div style={{ marginBottom: '24px' }}>
              <input
                type="email"
                placeholder="Enter your email"
                value={userAccount.email || ''}
                onChange={(e) => setUserAccount(prev => ({ ...prev, email: e.target.value }))}
                disabled={emailSending}
                style={{
                  width: '100%', padding: '14px 16px', borderRadius: '12px',
                  border: '1px solid #e2e8f0', fontSize: '15px',
                  outline: 'none', transition: 'border-color 0.2s',
                }}
                onFocus={(e) => e.target.style.borderColor = '#218D8D'}
                onBlur={(e) => e.target.style.borderColor = '#e2e8f0'}
              />
            </div>

            <button
              onClick={handleEmailContinue}
              disabled={emailSending || !userAccount.email || !userAccount.email.includes('@')}
              style={{
                width: '100%', padding: '16px', borderRadius: '12px', border: 'none',
                background: userAccount.email?.includes('@') && !emailSending ? 'linear-gradient(135deg, #218D8D 0%, #1a7070 100%)' : '#e2e8f0',
                color: userAccount.email?.includes('@') && !emailSending ? 'white' : '#94a3b8',
                fontSize: '16px', fontWeight: '600', cursor: userAccount.email?.includes('@') && !emailSending ? 'pointer' : 'not-allowed',
                transition: 'all 0.2s',
              }}
            >
              {emailSending ? 'Sending...' : 'Continue with Email'}
            </button>
          </>
        )}

        <p style={{ textAlign: 'center', marginTop: '24px', color: '#94a3b8', fontSize: '13px', lineHeight: '1.5' }}>
          By continuing, you agree to our Terms of Service and Privacy Policy.
          Your progress will be saved automatically.
        </p>
      </div>
    );
  };

  // Render current stage
  const renderStage = () => {
    switch (currentStage) {
      case 'account': return renderAccountStage();
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

      {/* Hide progress bar on account stage */}
      {currentStage !== 'account' && (
        <div className="progress-header">
          <div className="progress-chapters">
            {visibleStages.map((stage, index) => {
              const currentIndex = visibleStages.findIndex(s => s.id === currentStage);
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
            {/* Save Progress Button */}
            <button
              onClick={() => setShowSaveModal(true)}
              style={{
                display: 'flex', alignItems: 'center', gap: '6px',
                padding: '8px 12px', marginLeft: '16px', borderRadius: '8px',
                border: '1px solid #e2e8f0', background: 'white',
                color: '#64748b', fontSize: '13px', fontWeight: '500',
                cursor: 'pointer', transition: 'all 0.2s',
              }}
              onMouseOver={(e) => { e.currentTarget.style.borderColor = '#218D8D'; e.currentTarget.style.color = '#218D8D'; }}
              onMouseOut={(e) => { e.currentTarget.style.borderColor = '#e2e8f0'; e.currentTarget.style.color = '#64748b'; }}
            >
              <Icon name="save" size={16} />
              Save
            </button>
          </div>
        </div>
      )}

      {showMicroWin && (
        <div className="micro-win-toast">
          <span className="micro-win-icon"><Icon name="checkCircle" size={24} /></span>
          <span className="micro-win-message">{microWinMessage}</span>
        </div>
      )}

      <div className="urla-main-layout">
        <main className="urla-content">
          {renderStage()}
        </main>

        {/* Documents Sidebar - Reveals progressively as application is completed */}
        {currentStage !== 'account' && (
        <aside className="documents-sidebar">
        <div className="sidebar-header">
          <Icon name="document" size={20} />
          <h3>Documents Needed</h3>
        </div>
        <p className="sidebar-subtitle">Gather these documents to speed up your application</p>

        <div className="documents-list">
          {(() => {
            const currentIndex = enabledStages.findIndex(s => s.id === currentStage);
            // Get dynamic document list based on user's declarations, profile, and income for personalized labels
            const requiredDocs = getRequiredDocuments(declarations, {}, profileData, incomeData, coBorrowerData, coBorrowerIncomeData);

            // Map category to the stage that unlocks it
            const categoryUnlockStage = {
              identity: 'declarations',
              income: 'income',
              assets: 'income',  // Assets unlock with income stage for refinance
              property: 'property'
            };

            const categoryLabels = {
              identity: 'Identity Verification',
              income: 'Income Documents',
              assets: 'Asset Documents',
              property: 'Property Documents'
            };

            // Filter categories to only show those that have been unlocked AND have documents
            const visibleCategories = ['identity', 'income', 'assets', 'property'].filter(category => {
              const unlockStage = categoryUnlockStage[category];
              const unlockIndex = enabledStages.findIndex(s => s.id === unlockStage);
              const categoryDocs = requiredDocs.filter(d => d.category === category);
              // Show category if user has reached or passed its unlock stage AND has documents
              return currentIndex >= unlockIndex && categoryDocs.length > 0;
            });

            return visibleCategories.map(category => {
              const categoryDocs = requiredDocs.filter(d => d.category === category);
              const isCurrent = categoryDocs.some(d => d.stage === currentStage);

              return (
                <div key={category} className={`doc-category ${isCurrent ? 'current' : ''}`}>
                  <h4 className="doc-category-title">{categoryLabels[category]}</h4>
                  <ul className="doc-items">
                    {categoryDocs.map(doc => (
                      <li key={doc.id} className="doc-item">
                        <span className="doc-checkbox">
                          <Icon name="document" size={14} />
                        </span>
                        <div className="doc-info">
                          <span className="doc-name">{doc.name}</span>
                          <span className="doc-desc">{doc.description}</span>
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
              );
            });
          })()}
        </div>

        <div className="sidebar-tip">
          <Icon name="info" size={16} />
          <span>Documents can be uploaded after you submit your application</span>
        </div>
      </aside>
        )}
      </div>

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

      {/* Submission Success Lightbox */}
      {showSubmissionSuccess && (
        <div className="submission-success-overlay">
          <div className="submission-success-lightbox">
            <div className="success-checkmark">
              <svg viewBox="0 0 52 52" className="checkmark-svg">
                <circle className="checkmark-circle" cx="26" cy="26" r="25" fill="none"/>
                <path className="checkmark-check" fill="none" d="M14.1 27.2l7.1 7.2 16.7-16.8"/>
              </svg>
            </div>
            <h2>Application Submitted!</h2>
            <p>Your refinance application has been successfully submitted.</p>
            <p className="redirect-message">You will be redirected to your client portal...</p>
          </div>
        </div>
      )}

      {/* Save Progress Modal */}
      {showSaveModal && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center',
          zIndex: 1000,
        }}>
          <div style={{
            background: 'white', borderRadius: '16px', padding: '32px',
            maxWidth: '420px', width: '90%', boxShadow: '0 25px 50px -12px rgba(0,0,0,0.25)',
          }}>
            <h3 style={{ fontSize: '20px', fontWeight: '600', color: '#1a365d', marginBottom: '8px' }}>
              Save Your Progress
            </h3>
            <p style={{ color: '#64748b', fontSize: '14px', marginBottom: '24px' }}>
              Your progress is automatically saved to this device. Enter your email to get a link to continue from any device.
            </p>

            <div style={{ marginBottom: '16px' }}>
              <input
                type="email"
                placeholder="Enter your email"
                value={saveEmail}
                onChange={(e) => setSaveEmail(e.target.value)}
                style={{
                  width: '100%', padding: '12px 16px', borderRadius: '8px',
                  border: '1px solid #e2e8f0', fontSize: '15px',
                }}
              />
            </div>

            <div style={{ display: 'flex', gap: '12px' }}>
              <button
                onClick={() => setShowSaveModal(false)}
                style={{
                  flex: 1, padding: '12px', borderRadius: '8px',
                  border: '1px solid #e2e8f0', background: 'white',
                  color: '#64748b', fontSize: '14px', fontWeight: '500', cursor: 'pointer',
                }}
              >
                Cancel
              </button>
              <button
                onClick={handleSaveProgressEmail}
                disabled={!saveEmail || !saveEmail.includes('@')}
                style={{
                  flex: 1, padding: '12px', borderRadius: '8px', border: 'none',
                  background: saveEmail?.includes('@') ? 'linear-gradient(135deg, #218D8D 0%, #1a7070 100%)' : '#e2e8f0',
                  color: saveEmail?.includes('@') ? 'white' : '#94a3b8',
                  fontSize: '14px', fontWeight: '500',
                  cursor: saveEmail?.includes('@') ? 'pointer' : 'not-allowed',
                }}
              >
                Send Link
              </button>
            </div>

            {lastSavedAt && (
              <p style={{ textAlign: 'center', marginTop: '16px', color: '#94a3b8', fontSize: '12px' }}>
                Last auto-saved: {lastSavedAt.toLocaleTimeString()}
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
