import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import './BuyerIntake.css';

export default function BuyerIntake() {
  const navigate = useNavigate();
  const [submitting, setSubmitting] = useState(false);
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

    // Co‑borrower (optional)
    hasCoborrower: "No",
    coFirstName: "",
    coLastName: "",
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

  const onSubmit = async (e) => {
    e.preventDefault();

    // Basic validation
    const errors = [];
    if (!form.firstName || !form.lastName) errors.push("Name is required");
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(form.email)) errors.push("Valid email required");
    if (!/^[0-9\-()+\s]{7,}$/.test(form.phone)) errors.push("Valid phone required");
    if (!form.priceTarget) errors.push("Price target required");

    if (errors.length) {
      alert("Please fix:\n" + errors.join("\n"));
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
      },
      coborrower: form.hasCoborrower === "Yes" ? {
        first_name: form.coFirstName.trim(),
        last_name: form.coLastName.trim(),
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
      alert('Thank you! Your information has been submitted successfully. We\'ll be in touch soon.');

      // Redirect to a thank you page or home
      window.location.href = '/';

    } catch (error) {
      console.error('Submission error:', error);
      alert('There was an error submitting your application. Please try again or contact us directly.');
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
            <div className="form-grid grid-4">
              <div className="form-field">
                <label>Add a co‑borrower?</label>
                <select name="hasCoborrower" value={form.hasCoborrower} onChange={handleChange}>
                  <option>No</option>
                  <option>Yes</option>
                </select>
              </div>
              {form.hasCoborrower === "Yes" && (
                <>
                  <div className="form-field">
                    <label>First name</label>
                    <input name="coFirstName" value={form.coFirstName} onChange={handleChange} placeholder="John" />
                  </div>
                  <div className="form-field">
                    <label>Last name</label>
                    <input name="coLastName" value={form.coLastName} onChange={handleChange} placeholder="Smith" />
                  </div>
                  <div className="form-field">
                    <label>Annual income</label>
                    <input name="coIncome" value={form.coIncome} onChange={handleChange} placeholder="$75,000" />
                  </div>
                </>
              )}
            </div>
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
