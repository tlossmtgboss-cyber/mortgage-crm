import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import './BuyerIntake.css';
import { toast } from '../utils/toast';

export default function BuyerIntake() {
  const navigate = useNavigate();
  const [submitting, setSubmitting] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [voiceTranscript, setVoiceTranscript] = useState('');
  const [lastCommand, setLastCommand] = useState('');
  const recognitionRef = useRef(null);
  const [form, setForm] = useState({
    // Contact
    firstName: "",
    lastName: "",
    email: "",
    phone: "",
    preferredContact: "Text",

    // Scenario
    occupancy: "Primary Residence",
    timeframe: "0–30 days",
    location: "",

    // Budget
    priceTarget: "",
    downPayment: "",
    downType: "%",
    monthlyComfort: "",

    // Profile
    creditRange: "700–739",
    firstTimeBuyer: "Yes",
    vaEligible: "No",
    employmentType: "W2",
    householdIncome: "",
    liquidAssets: "",
    selfEmployed: "No",
    dateOfBirth: "",
    ssn: "",
    employer: "",
    yearsWithEmployer: "",

    // Co‑borrower (optional)
    hasCoborrower: "No",
    coFirstName: "",
    coLastName: "",
    coEmail: "",
    coPhone: "",
    coPreferredContact: "Text",
    coDateOfBirth: "",
    coSSN: "",
    coCreditRange: "700–739",
    coEmploymentType: "W2",
    coEmployer: "",
    coYearsWithEmployer: "",
    coIncome: "",

    // Partners & preferences
    hasAgent: "Yes",
    agentName: "",
    agentEmail: "",
    letterType: "Full Pre‑Approval",
    communicationPrefs: ["Text", "Email"],

    // Consents
    softCreditOk: false,
    contactConsent: false,
    notes: "",
  });

  const creditRanges = [
    "760+",
    "740–759",
    "700–739",
    "660–699",
    "620–659",
    "<620",
    "Unsure",
  ];

  const timeframes = ["0–30 days", "31–60 days", "61–90 days", "90+ days", "Just researching"];

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    if (type === "checkbox" && name === "softCreditOk") {
      setForm((f) => ({ ...f, softCreditOk: checked }));
    } else if (type === "checkbox" && name === "contactConsent") {
      setForm((f) => ({ ...f, contactConsent: checked }));
    } else if (name === "ssn" || name === "coSSN") {
      // Format SSN as XXX-XX-XXXX
      const digits = value.replace(/\D/g, "");
      let formatted = digits;
      if (digits.length > 3) {
        formatted = digits.slice(0, 3) + "-" + digits.slice(3);
      }
      if (digits.length > 5) {
        formatted = digits.slice(0, 3) + "-" + digits.slice(3, 5) + "-" + digits.slice(5, 9);
      }
      setForm((f) => ({ ...f, [name]: formatted }));
    } else {
      setForm((f) => ({ ...f, [name]: value }));
    }
  };

  const toggleComm = (opt) => {
    setForm((f) => {
      const set = new Set(f.communicationPrefs);
      set.has(opt) ? set.delete(opt) : set.add(opt);
      return { ...f, communicationPrefs: Array.from(set) };
    });
  };

  // Initialize voice recognition
  useEffect(() => {
    if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      recognitionRef.current = new SpeechRecognition();
      recognitionRef.current.continuous = true;
      recognitionRef.current.interimResults = true;
      recognitionRef.current.lang = 'en-US';

      recognitionRef.current.onresult = (event) => {
        let interimTranscript = '';
        let finalTranscript = '';

        for (let i = event.resultIndex; i < event.results.length; i++) {
          const transcript = event.results[i][0].transcript;
          if (event.results[i].isFinal) {
            finalTranscript += transcript + ' ';
          } else {
            interimTranscript += transcript;
          }
        }

        if (finalTranscript) {
          processVoiceCommand(finalTranscript.trim());
          setVoiceTranscript(finalTranscript.trim());
        }
      };

      recognitionRef.current.onerror = (event) => {
        console.error('Speech recognition error:', event.error);
        if (event.error === 'no-speech' || event.error === 'aborted') {
          // Silently handle these common errors
        } else {
          setIsListening(false);
        }
      };

      recognitionRef.current.onend = () => {
        if (isListening) {
          // Restart if it stopped but we're still in listening mode
          try {
            recognitionRef.current.start();
          } catch (e) {
            console.error('Error restarting recognition:', e);
          }
        }
      };
    }

    return () => {
      if (recognitionRef.current) {
        recognitionRef.current.stop();
      }
    };
  }, [isListening]);

  const processVoiceCommand = (transcript) => {
    const lower = transcript.toLowerCase();
    setLastCommand(transcript);

    // Contact fields
    if (lower.includes('first name') || lower.includes('my name is') || lower.includes("i'm ")) {
      const match = transcript.match(/(?:first name|my name is|i'm)\s+([a-z]+)/i);
      if (match) {
        setForm(f => ({ ...f, firstName: match[1].charAt(0).toUpperCase() + match[1].slice(1) }));
      }
    }

    if (lower.includes('last name') || lower.includes('surname')) {
      const match = transcript.match(/(?:last name|surname)\s+([a-z]+)/i);
      if (match) {
        setForm(f => ({ ...f, lastName: match[1].charAt(0).toUpperCase() + match[1].slice(1) }));
      }
    }

    if (lower.includes('email')) {
      const emailMatch = transcript.match(/([a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,})/i);
      if (emailMatch) {
        setForm(f => ({ ...f, email: emailMatch[1].toLowerCase() }));
      }
    }

    if (lower.includes('phone') || lower.includes('mobile') || lower.includes('number')) {
      const phoneMatch = transcript.match(/(\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}|\d{10})/);
      if (phoneMatch) {
        setForm(f => ({ ...f, phone: phoneMatch[1] }));
      }
    }

    if (lower.includes('preferred contact')) {
      if (lower.includes('text')) setForm(f => ({ ...f, preferredContact: 'Text' }));
      else if (lower.includes('email')) setForm(f => ({ ...f, preferredContact: 'Email' }));
      else if (lower.includes('phone')) setForm(f => ({ ...f, preferredContact: 'Phone' }));
    }

    // Scenario fields
    if (lower.includes('occupancy') || lower.includes('property type')) {
      if (lower.includes('primary residence') || lower.includes('primary home')) {
        setForm(f => ({ ...f, occupancy: 'Primary Residence' }));
      } else if (lower.includes('second home')) {
        setForm(f => ({ ...f, occupancy: 'Second Home' }));
      } else if (lower.includes('investment')) {
        setForm(f => ({ ...f, occupancy: 'Investment' }));
      }
    }

    if (lower.includes('timeline') || lower.includes('timeframe')) {
      if (lower.includes('30 days') || lower.includes('0 to 30') || lower.includes('zero to thirty')) {
        setForm(f => ({ ...f, timeframe: '0–30 days' }));
      } else if (lower.includes('60 days') || lower.includes('31 to 60')) {
        setForm(f => ({ ...f, timeframe: '31–60 days' }));
      } else if (lower.includes('90 days') || lower.includes('61 to 90')) {
        setForm(f => ({ ...f, timeframe: '61–90 days' }));
      } else if (lower.includes('90 plus') || lower.includes('more than 90')) {
        setForm(f => ({ ...f, timeframe: '90+ days' }));
      } else if (lower.includes('research')) {
        setForm(f => ({ ...f, timeframe: 'Just researching' }));
      }
    }

    if (lower.includes('location') || lower.includes('target area') || lower.includes('city')) {
      const locMatch = transcript.match(/(?:location|target area|city)\s+(.+?)(?:\s|$)/i);
      if (locMatch) {
        setForm(f => ({ ...f, location: locMatch[1] }));
      }
    }

    // Budget fields
    if (lower.includes('price target') || lower.includes('purchase price') || lower.includes('home price')) {
      const priceMatch = transcript.match(/(\$?[\d,]+,?\d*)/);
      if (priceMatch) {
        setForm(f => ({ ...f, priceTarget: priceMatch[1] }));
      }
    }

    if (lower.includes('down payment')) {
      const downMatch = transcript.match(/(\$?[\d,]+%?)/);
      if (downMatch) {
        const value = downMatch[1];
        setForm(f => ({
          ...f,
          downPayment: value.replace(/[^0-9]/g, ''),
          downType: value.includes('%') ? '%' : '$'
        }));
      }
    }

    if (lower.includes('monthly') || lower.includes('piti')) {
      const monthlyMatch = transcript.match(/(\$?[\d,]+)/);
      if (monthlyMatch) {
        setForm(f => ({ ...f, monthlyComfort: monthlyMatch[1] }));
      }
    }

    // Profile fields
    if (lower.includes('date of birth') || lower.includes('birthday') || lower.includes('born')) {
      const dateMatch = transcript.match(/(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})/);
      if (dateMatch) {
        // Convert to YYYY-MM-DD format
        const parts = dateMatch[1].split(/[/-]/);
        if (parts.length === 3) {
          const year = parts[2].length === 2 ? '19' + parts[2] : parts[2];
          const formatted = `${year}-${parts[0].padStart(2, '0')}-${parts[1].padStart(2, '0')}`;
          setForm(f => ({ ...f, dateOfBirth: formatted }));
        }
      }
    }

    if (lower.includes('social security') || lower.includes('ssn')) {
      const ssnMatch = transcript.match(/(\d{3}[-\s]?\d{2}[-\s]?\d{4})/);
      if (ssnMatch) {
        const digits = ssnMatch[1].replace(/\D/g, '');
        const formatted = `${digits.slice(0, 3)}-${digits.slice(3, 5)}-${digits.slice(5, 9)}`;
        setForm(f => ({ ...f, ssn: formatted }));
      }
    }

    if (lower.includes('credit score') || lower.includes('credit range')) {
      if (lower.includes('760') || lower.includes('excellent')) {
        setForm(f => ({ ...f, creditRange: '760+' }));
      } else if (lower.includes('740')) {
        setForm(f => ({ ...f, creditRange: '740–759' }));
      } else if (lower.includes('700')) {
        setForm(f => ({ ...f, creditRange: '700–739' }));
      } else if (lower.includes('660')) {
        setForm(f => ({ ...f, creditRange: '660–699' }));
      } else if (lower.includes('620')) {
        setForm(f => ({ ...f, creditRange: '620–659' }));
      } else if (lower.includes('below 620') || lower.includes('under 620')) {
        setForm(f => ({ ...f, creditRange: '<620' }));
      } else if (lower.includes('unsure') || lower.includes("don't know")) {
        setForm(f => ({ ...f, creditRange: 'Unsure' }));
      }
    }

    if (lower.includes('first time buyer') || lower.includes('first-time buyer')) {
      if (lower.includes('yes') || lower.includes('i am')) {
        setForm(f => ({ ...f, firstTimeBuyer: 'Yes' }));
      } else if (lower.includes('no') || lower.includes("i'm not")) {
        setForm(f => ({ ...f, firstTimeBuyer: 'No' }));
      }
    }

    if (lower.includes('va eligible') || lower.includes('veteran')) {
      if (lower.includes('yes') || lower.includes('i am')) {
        setForm(f => ({ ...f, vaEligible: 'Yes' }));
      } else {
        setForm(f => ({ ...f, vaEligible: 'No' }));
      }
    }

    if (lower.includes('employment type') || lower.includes('how are you employed')) {
      if (lower.includes('w2') || lower.includes('w-2') || lower.includes('employee')) {
        setForm(f => ({ ...f, employmentType: 'W2' }));
      } else if (lower.includes('self-employed') || lower.includes('self employed')) {
        setForm(f => ({ ...f, employmentType: 'Self‑Employed' }));
      } else if (lower.includes('contractor') || lower.includes('1099')) {
        setForm(f => ({ ...f, employmentType: '1099/Contractor' }));
      } else if (lower.includes('retired')) {
        setForm(f => ({ ...f, employmentType: 'Retired' }));
      }
    }

    if (lower.includes('employer')) {
      const empMatch = transcript.match(/employer\s+(?:is\s+)?(.+?)(?:\s|$)/i);
      if (empMatch) {
        setForm(f => ({ ...f, employer: empMatch[1] }));
      }
    }

    if (lower.includes('years with employer') || lower.includes('years at')) {
      const yearsMatch = transcript.match(/(\d+\.?\d*)\s*years?/i);
      if (yearsMatch) {
        setForm(f => ({ ...f, yearsWithEmployer: yearsMatch[1] }));
      }
    }

    if (lower.includes('income') || lower.includes('salary')) {
      const incomeMatch = transcript.match(/(\$?[\d,]+)/);
      if (incomeMatch) {
        setForm(f => ({ ...f, householdIncome: incomeMatch[1] }));
      }
    }

    if (lower.includes('liquid assets') || lower.includes('assets for closing')) {
      const assetsMatch = transcript.match(/(\$?[\d,]+)/);
      if (assetsMatch) {
        setForm(f => ({ ...f, liquidAssets: assetsMatch[1] }));
      }
    }

    // Co-borrower
    if (lower.includes('co-borrower') || lower.includes('coborrower')) {
      if (lower.includes('yes') || lower.includes('have')) {
        setForm(f => ({ ...f, hasCoborrower: 'Yes' }));
      } else if (lower.includes('no')) {
        setForm(f => ({ ...f, hasCoborrower: 'No' }));
      }
    }

    // Realtor
    if (lower.includes('realtor') || lower.includes('agent')) {
      if (lower.includes('yes') || lower.includes('working with')) {
        setForm(f => ({ ...f, hasAgent: 'Yes' }));
      } else if (lower.includes('no') || lower.includes("don't have")) {
        setForm(f => ({ ...f, hasAgent: 'No' }));
      }
    }

    // Consents
    if (lower.includes('credit pull') || lower.includes('soft credit')) {
      if (lower.includes('yes') || lower.includes('authorize') || lower.includes('agree')) {
        setForm(f => ({ ...f, softCreditOk: true }));
      }
    }

    if (lower.includes('contact consent') || lower.includes('agree to be contacted')) {
      if (lower.includes('yes') || lower.includes('agree')) {
        setForm(f => ({ ...f, contactConsent: true }));
      }
    }
  };

  const toggleVoiceInput = () => {
    if (!recognitionRef.current) {
      toast.error('Voice recognition is not supported in this browser. Please use Chrome, Safari, or Edge.');
      return;
    }

    if (isListening) {
      recognitionRef.current.stop();
      setIsListening(false);
    } else {
      try {
        recognitionRef.current.start();
        setIsListening(true);
        setVoiceTranscript('');
      } catch (error) {
        console.error('Error starting voice recognition:', error);
      }
    }
  };

  const onSubmit = async (e) => {
    e.preventDefault();

    // Basic validation
    const errors = [];
    if (!form.firstName || !form.lastName) errors.push("Name is required");
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(form.email)) errors.push("Valid email required");
    if (!/^[0-9\-()+\s]{7,}$/.test(form.phone)) errors.push("Valid phone required");
    if (!form.priceTarget) errors.push("Price target required");

    if (errors.length) {
      toast.error("Please fix:\n" + errors.join("\n"));
      return;
    }

    setSubmitting(true);

    // Normalize numbers for backend
    const payload = {
      contact: {
        first_name: form.firstName.trim(),
        last_name: form.lastName.trim(),
        email: form.email.trim(),
        phone: form.phone.trim(),
        preferred_contact: form.preferredContact,
      },
      scenario: {
        occupancy: form.occupancy,
        timeframe: form.timeframe,
        location: form.location.trim(),
      },
      budget: {
        price_target: Number(String(form.priceTarget).replace(/[^0-9.]/g, "")),
        down_payment_value: Number(String(form.downPayment).replace(/[^0-9.]/g, "")),
        down_payment_type: form.downType,
        monthly_comfort: Number(String(form.monthlyComfort).replace(/[^0-9.]/g, "")) || null,
      },
      profile: {
        credit_range: form.creditRange,
        first_time_buyer: form.firstTimeBuyer === "Yes",
        va_eligible: form.vaEligible === "Yes",
        employment_type: form.employmentType,
        household_income: Number(String(form.householdIncome).replace(/[^0-9.]/g, "")) || null,
        liquid_assets: Number(String(form.liquidAssets).replace(/[^0-9.]/g, "")) || null,
        self_employed: form.selfEmployed === "Yes",
        date_of_birth: form.dateOfBirth || null,
        ssn: form.ssn.replace(/[^0-9]/g, "") || null,
        employer: form.employer.trim() || null,
        years_with_employer: Number(form.yearsWithEmployer) || null,
      },
      coborrower: form.hasCoborrower === "Yes" ? {
        first_name: form.coFirstName.trim(),
        last_name: form.coLastName.trim(),
        email: form.coEmail.trim() || null,
        phone: form.coPhone.trim() || null,
        preferred_contact: form.coPreferredContact,
        date_of_birth: form.coDateOfBirth || null,
        ssn: form.coSSN.replace(/[^0-9]/g, "") || null,
        credit_range: form.coCreditRange,
        employment_type: form.coEmploymentType,
        employer: form.coEmployer.trim() || null,
        years_with_employer: Number(form.coYearsWithEmployer) || null,
        income: Number(String(form.coIncome).replace(/[^0-9.]/g, "")) || null,
      } : null,
      partners: form.hasAgent === "Yes" ? {
        agent_name: form.agentName.trim(),
        agent_email: form.agentEmail.trim(),
      } : null,
      preferences: {
        letter_type: form.letterType,
        communication: form.communicationPrefs,
      },
      consents: {
        soft_credit_ok: form.softCreditOk,
        contact_consent: form.contactConsent,
      },
      notes: form.notes.trim() || null,
    };

    try {
      const response = await fetch(`${process.env.REACT_APP_API_URL}/api/v1/buyer-intake`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        throw new Error('Submission failed');
      }

      const data = await response.json();

      // Show success message
      toast.success('Thank you! Your information has been submitted successfully. We\'ll be in touch soon.');

      // Redirect to a thank you page or home
      window.location.href = '/';

    } catch (error) {
      console.error('Submission error:', error);
      toast.error('There was an error submitting your application. Please try again or contact us directly.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="buyer-intake-page">
      <div className="buyer-intake-container">
        <div className="intake-header">
          <h1>Buyer's Quick Start</h1>
          <p>A short intake to kick off your pre‑approval. Takes ~2 minutes.</p>

          {/* Voice Control Button */}
          <div className="voice-control-container">
            <button
              type="button"
              onClick={toggleVoiceInput}
              className={`voice-btn ${isListening ? 'listening' : ''}`}
              title={isListening ? 'Stop voice input' : 'Start voice input'}
            >
              {isListening ? (
                <>
                  <span className="mic-icon pulsing">🎤</span>
                  <span>Listening...</span>
                </>
              ) : (
                <>
                  <span className="mic-icon">🎤</span>
                  <span>Voice Input</span>
                </>
              )}
            </button>
            {isListening && (
              <div className="voice-indicator">
                <div className="sound-wave">
                  <span></span>
                  <span></span>
                  <span></span>
                  <span></span>
                  <span></span>
                </div>
              </div>
            )}
          </div>

          {lastCommand && (
            <div className="last-command">
              <strong>Last heard:</strong> "{lastCommand}"
            </div>
          )}
        </div>

        <form onSubmit={onSubmit} className="intake-form">
          {/* Contact */}
          <section className="intake-section">
            <h2>Contact</h2>
            <div className="form-grid grid-2">
              <div className="form-field">
                <label>First name</label>
                <input name="firstName" value={form.firstName} onChange={handleChange} placeholder="Jane" required />
              </div>
              <div className="form-field">
                <label>Last name</label>
                <input name="lastName" value={form.lastName} onChange={handleChange} placeholder="Doe" required />
              </div>
              <div className="form-field">
                <label>Email</label>
                <input type="email" name="email" value={form.email} onChange={handleChange} placeholder="jane@example.com" required />
              </div>
              <div className="form-field">
                <label>Mobile</label>
                <input name="phone" value={form.phone} onChange={handleChange} placeholder="(555) 555-5555" required />
              </div>
              <div className="form-field">
                <label>Preferred contact</label>
                <select name="preferredContact" value={form.preferredContact} onChange={handleChange}>
                  <option>Text</option>
                  <option>Email</option>
                  <option>Phone</option>
                </select>
              </div>
            </div>
          </section>

          {/* Scenario */}
          <section className="intake-section">
            <h2>Scenario</h2>
            <div className="form-grid grid-3">
              <div className="form-field">
                <label>Occupancy</label>
                <select name="occupancy" value={form.occupancy} onChange={handleChange}>
                  <option>Primary Residence</option>
                  <option>Second Home</option>
                  <option>Investment</option>
                </select>
              </div>
              <div className="form-field">
                <label>Timeline</label>
                <select name="timeframe" value={form.timeframe} onChange={handleChange}>
                  {timeframes.map((t) => (<option key={t}>{t}</option>))}
                </select>
              </div>
              <div className="form-field">
                <label>Target area (city or ZIP)</label>
                <input name="location" value={form.location} onChange={handleChange} placeholder="Charleston or 29407" />
              </div>
            </div>
          </section>

          {/* Budget */}
          <section className="intake-section">
            <h2>Budget</h2>
            <div className="form-grid grid-4">
              <div className="form-field span-2">
                <label>Price target</label>
                <input name="priceTarget" value={form.priceTarget} onChange={handleChange} placeholder="$450,000" required />
              </div>
              <div className="form-field">
                <label>Down payment</label>
                <div className="input-group">
                  <input name="downPayment" value={form.downPayment} onChange={handleChange} placeholder="5 or 25000" />
                  <select name="downType" value={form.downType} onChange={handleChange} className="input-addon">
                    <option>%</option>
                    <option>$</option>
                  </select>
                </div>
              </div>
              <div className="form-field">
                <label>Comfortable monthly (PITI)</label>
                <input name="monthlyComfort" value={form.monthlyComfort} onChange={handleChange} placeholder="$3,000" />
              </div>
            </div>
          </section>

          {/* Profile */}
          <section className="intake-section">
            <h2>Profile</h2>
            <div className="form-grid grid-3">
              <div className="form-field">
                <label>Date of Birth</label>
                <input type="date" name="dateOfBirth" value={form.dateOfBirth} onChange={handleChange} />
              </div>
              <div className="form-field">
                <label>Social Security Number</label>
                <input
                  type="text"
                  name="ssn"
                  value={form.ssn}
                  onChange={handleChange}
                  placeholder="XXX-XX-XXXX"
                  maxLength="11"
                />
                <small style={{ fontSize: '11px', color: '#6b7280', marginTop: '4px' }}>
                  🔒 Encrypted and secure
                </small>
              </div>
              <div className="form-field">
                <label>Estimated credit</label>
                <select name="creditRange" value={form.creditRange} onChange={handleChange}>
                  {creditRanges.map((c) => (<option key={c}>{c}</option>))}
                </select>
              </div>
              <div className="form-field">
                <label>First‑time buyer?</label>
                <select name="firstTimeBuyer" value={form.firstTimeBuyer} onChange={handleChange}>
                  <option>Yes</option>
                  <option>No</option>
                </select>
              </div>
              <div className="form-field">
                <label>VA eligible?</label>
                <select name="vaEligible" value={form.vaEligible} onChange={handleChange}>
                  <option>No</option>
                  <option>Yes</option>
                </select>
              </div>
              <div className="form-field">
                <label>Employment type</label>
                <select name="employmentType" value={form.employmentType} onChange={handleChange}>
                  <option>W2</option>
                  <option>Self‑Employed</option>
                  <option>1099/Contractor</option>
                  <option>Retired</option>
                </select>
              </div>
              <div className="form-field">
                <label>Employer name</label>
                <input name="employer" value={form.employer} onChange={handleChange} placeholder="ABC Company Inc." />
              </div>
              <div className="form-field">
                <label>Years with employer</label>
                <input
                  type="number"
                  name="yearsWithEmployer"
                  value={form.yearsWithEmployer}
                  onChange={handleChange}
                  placeholder="5"
                  min="0"
                  step="0.5"
                />
              </div>
              <div className="form-field">
                <label>Annual household income (pre‑tax)</label>
                <input name="householdIncome" value={form.householdIncome} onChange={handleChange} placeholder="$180,000" />
              </div>
              <div className="form-field">
                <label>Liquid assets for closing</label>
                <input name="liquidAssets" value={form.liquidAssets} onChange={handleChange} placeholder="$55,000" />
              </div>
            </div>
          </section>

          {/* Co‑borrower */}
          <section className="intake-section">
            <h2>Co‑Borrower (optional)</h2>
            <div className="form-grid grid-1">
              <div className="form-field">
                <label>Add a co‑borrower?</label>
                <select name="hasCoborrower" value={form.hasCoborrower} onChange={handleChange}>
                  <option>No</option>
                  <option>Yes</option>
                </select>
              </div>
            </div>

            {form.hasCoborrower === "Yes" && (
              <>
                <h3 style={{ marginTop: '24px', marginBottom: '16px', fontSize: '16px', fontWeight: 600 }}>Contact Info</h3>
                <div className="form-grid grid-2">
                  <div className="form-field">
                    <label>First name</label>
                    <input name="coFirstName" value={form.coFirstName} onChange={handleChange} placeholder="John" />
                  </div>
                  <div className="form-field">
                    <label>Last name</label>
                    <input name="coLastName" value={form.coLastName} onChange={handleChange} placeholder="Smith" />
                  </div>
                  <div className="form-field">
                    <label>Email</label>
                    <input type="email" name="coEmail" value={form.coEmail} onChange={handleChange} placeholder="john@example.com" />
                  </div>
                  <div className="form-field">
                    <label>Mobile</label>
                    <input name="coPhone" value={form.coPhone} onChange={handleChange} placeholder="(555) 555-5555" />
                  </div>
                  <div className="form-field">
                    <label>Preferred contact</label>
                    <select name="coPreferredContact" value={form.coPreferredContact} onChange={handleChange}>
                      <option>Text</option>
                      <option>Email</option>
                      <option>Phone</option>
                    </select>
                  </div>
                </div>

                <h3 style={{ marginTop: '24px', marginBottom: '16px', fontSize: '16px', fontWeight: 600 }}>Profile</h3>
                <div className="form-grid grid-3">
                  <div className="form-field">
                    <label>Date of Birth</label>
                    <input type="date" name="coDateOfBirth" value={form.coDateOfBirth} onChange={handleChange} />
                  </div>
                  <div className="form-field">
                    <label>Social Security Number</label>
                    <input
                      type="text"
                      name="coSSN"
                      value={form.coSSN}
                      onChange={handleChange}
                      placeholder="XXX-XX-XXXX"
                      maxLength="11"
                    />
                    <small style={{ fontSize: '11px', color: '#6b7280', marginTop: '4px' }}>
                      🔒 Encrypted and secure
                    </small>
                  </div>
                  <div className="form-field">
                    <label>Estimated credit</label>
                    <select name="coCreditRange" value={form.coCreditRange} onChange={handleChange}>
                      {creditRanges.map((c) => (<option key={c}>{c}</option>))}
                    </select>
                  </div>
                  <div className="form-field">
                    <label>Employment type</label>
                    <select name="coEmploymentType" value={form.coEmploymentType} onChange={handleChange}>
                      <option>W2</option>
                      <option>Self‑Employed</option>
                      <option>1099/Contractor</option>
                      <option>Retired</option>
                    </select>
                  </div>
                  <div className="form-field">
                    <label>Employer name</label>
                    <input name="coEmployer" value={form.coEmployer} onChange={handleChange} placeholder="XYZ Corp" />
                  </div>
                  <div className="form-field">
                    <label>Years with employer</label>
                    <input
                      type="number"
                      name="coYearsWithEmployer"
                      value={form.coYearsWithEmployer}
                      onChange={handleChange}
                      placeholder="3"
                      min="0"
                      step="0.5"
                    />
                  </div>
                  <div className="form-field">
                    <label>Annual income</label>
                    <input name="coIncome" value={form.coIncome} onChange={handleChange} placeholder="$75,000" />
                  </div>
                </div>
              </>
            )}
          </section>

          {/* Partners & preferences */}
          <section className="intake-section">
            <h2>Partners & Preferences</h2>
            <div className="form-grid grid-3">
              <div className="form-field">
                <label>Working with a Realtor?</label>
                <select name="hasAgent" value={form.hasAgent} onChange={handleChange}>
                  <option>Yes</option>
                  <option>No</option>
                </select>
              </div>
              {form.hasAgent === "Yes" && (
                <>
                  <div className="form-field">
                    <label>Agent name</label>
                    <input name="agentName" value={form.agentName} onChange={handleChange} placeholder="Casey Agent" />
                  </div>
                  <div className="form-field">
                    <label>Agent email</label>
                    <input type="email" name="agentEmail" value={form.agentEmail} onChange={handleChange} placeholder="casey@agency.com" />
                  </div>
                </>
              )}
              <div className="form-field">
                <label>Letter type</label>
                <select name="letterType" value={form.letterType} onChange={handleChange}>
                  <option>Full Pre‑Approval</option>
                  <option>Pre‑Qualification</option>
                </select>
              </div>
            </div>

            <div className="comm-prefs">
              <label>How should we keep you posted?</label>
              <div className="comm-buttons">
                {["Text", "Email", "Phone"].map((opt) => (
                  <button type="button" key={opt}
                    onClick={() => toggleComm(opt)}
                    className={`comm-btn ${form.communicationPrefs.includes(opt) ? 'active' : ''}`}>
                    {opt}
                  </button>
                ))}
              </div>
            </div>
          </section>

          {/* Consents & Notes */}
          <section className="intake-section">
            <h2>Consents & Notes</h2>
            <div className="consents">
              <label className="checkbox-label">
                <input type="checkbox" name="softCreditOk" checked={form.softCreditOk} onChange={handleChange} />
                <span>I authorize a soft credit pull to help determine loan options (no impact to score).</span>
              </label>
              <label className="checkbox-label">
                <input type="checkbox" name="contactConsent" checked={form.contactConsent} onChange={handleChange} required />
                <span>I agree to be contacted by SMS/Email/Phone regarding my mortgage inquiry.</span>
              </label>
              <div className="form-field">
                <label>Anything else we should know?</label>
                <textarea name="notes" value={form.notes} onChange={handleChange} rows={3} placeholder="e.g., bonus structure, gifts, contingencies" />
              </div>
            </div>
          </section>

          {/* Submit */}
          <div className="form-footer">
            <p className="disclaimer">This is a short intake, not a loan application. We'll follow up to complete your file.</p>
            <button type="submit" className="submit-btn" disabled={submitting}>
              {submitting ? 'Submitting...' : 'Submit'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
