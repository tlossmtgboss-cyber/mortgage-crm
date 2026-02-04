import { useState, useEffect, useRef } from 'react';
import './ListAndLockLandingPage.css';

function ListAndLockLandingPage() {
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    brokerage: '',
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitSuccess, setSubmitSuccess] = useState(false);
  const [visibleSections, setVisibleSections] = useState({});

  // Intersection Observer for scroll animations
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            setVisibleSections((prev) => ({
              ...prev,
              [entry.target.id]: true,
            }));
          }
        });
      },
      { threshold: 0.1, rootMargin: '0px 0px -50px 0px' }
    );

    const sections = document.querySelectorAll('.lal-animate');
    sections.forEach((section) => observer.observe(section));

    return () => {
      sections.forEach((section) => observer.unobserve(section));
    };
  }, []);

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setIsSubmitting(true);

    // Simulate API call
    await new Promise((resolve) => setTimeout(resolve, 1500));

    setIsSubmitting(false);
    setSubmitSuccess(true);
    setFormData({ name: '', email: '', brokerage: '' });
  };

  const scrollToSection = (id) => {
    const element = document.getElementById(id);
    if (element) {
      element.scrollIntoView({ behavior: 'smooth' });
    }
  };

  return (
    <div className="lal-page">
      {/* Noise Texture Overlay */}
      <div className="lal-noise-overlay" />

      {/* Fixed Navigation */}
      <nav className="lal-nav">
        <div className="lal-nav-container">
          <div className="lal-logo">
            <span className="lal-logo-icon">🔒</span>
            <span className="lal-logo-text">List & Lock<sup>®</sup></span>
          </div>
          <div className="lal-nav-links">
            <button onClick={() => scrollToSection('how-it-works')}>How It Works</button>
            <button onClick={() => scrollToSection('why-it-works')}>Why It Works</button>
            <button onClick={() => scrollToSection('who-its-for')}>Who It's For</button>
          </div>
          <button
            className="lal-nav-cta"
            onClick={() => scrollToSection('lead-capture')}
          >
            Get the Guide
          </button>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="lal-hero">
        <div className="lal-hero-content">
          <p className="lal-hero-eyebrow">For Real Estate Agents Who Refuse to Race to the Bottom</p>
          <h1 className="lal-hero-title">
            The Agents Who <span className="lal-gold">Saw It First</span><br />
            Are Already Using This
          </h1>
          <p className="lal-hero-subtitle">
            While everyone else cuts commissions and chases the bottom,
            a quiet revolution is happening. List & Lock® isn't just a strategy—it's
            the contrarian playbook that protects your listings, your sellers, and your income.
          </p>
          <div className="lal-hero-ctas">
            <button
              className="lal-btn-primary"
              onClick={() => scrollToSection('lead-capture')}
            >
              Download the Free Guide
            </button>
            <button
              className="lal-btn-secondary"
              onClick={() => scrollToSection('strategy-call')}
            >
              Book Strategy Walkthrough
            </button>
          </div>
        </div>
        <div className="lal-hero-scroll-indicator">
          <span>Scroll to discover the truth</span>
          <div className="lal-scroll-arrow">↓</div>
        </div>
      </section>

      {/* Hard Truth Section */}
      <section
        id="hard-truth"
        className={`lal-section lal-animate ${visibleSections['hard-truth'] ? 'lal-visible' : ''}`}
      >
        <div className="lal-section-content">
          <h2 className="lal-section-title">The Hard Truth Nobody's Telling You</h2>
          <div className="lal-truth-grid">
            <div className="lal-truth-card">
              <div className="lal-truth-stat">73%</div>
              <p className="lal-truth-text">
                of listings that sit more than 21 days end up with a price reduction
              </p>
            </div>
            <div className="lal-truth-card">
              <div className="lal-truth-stat">$16,200</div>
              <p className="lal-truth-text">
                average seller loss from price reductions on a $400K home
              </p>
            </div>
            <div className="lal-truth-card">
              <div className="lal-truth-stat">2.3x</div>
              <p className="lal-truth-text">
                longer time on market after the first price drop
              </p>
            </div>
          </div>
          <p className="lal-section-emphasis">
            Price reductions don't just cost money—they <span className="lal-gold">signal desperation</span> to every buyer in the market.
          </p>
        </div>
      </section>

      {/* The Math Section */}
      <section
        id="the-math"
        className={`lal-section lal-section-dark lal-animate ${visibleSections['the-math'] ? 'lal-visible' : ''}`}
      >
        <div className="lal-section-content">
          <h2 className="lal-section-title">The $16,000 Problem</h2>
          <div className="lal-math-breakdown">
            <div className="lal-math-row">
              <span className="lal-math-label">Listed Price</span>
              <span className="lal-math-value">$425,000</span>
            </div>
            <div className="lal-math-row lal-math-negative">
              <span className="lal-math-label">First Price Reduction (3%)</span>
              <span className="lal-math-value">-$12,750</span>
            </div>
            <div className="lal-math-row lal-math-negative">
              <span className="lal-math-label">Buyer "Reduction Psychology" Offer</span>
              <span className="lal-math-value">-$8,500</span>
            </div>
            <div className="lal-math-row lal-math-negative">
              <span className="lal-math-label">Extended Carrying Costs (2 months)</span>
              <span className="lal-math-value">-$4,200</span>
            </div>
            <div className="lal-math-divider" />
            <div className="lal-math-row lal-math-total">
              <span className="lal-math-label">Total Seller Loss</span>
              <span className="lal-math-value lal-red">-$25,450</span>
            </div>
          </div>
          <p className="lal-math-note">
            This happens every day. And it's completely preventable.
          </p>
        </div>
      </section>

      {/* Psychology Shift Section */}
      <section
        id="psychology"
        className={`lal-section lal-animate ${visibleSections['psychology'] ? 'lal-visible' : ''}`}
      >
        <div className="lal-section-content">
          <h2 className="lal-section-title">The Psychology of Price Reductions</h2>
          <div className="lal-psychology-comparison">
            <div className="lal-psychology-card lal-psychology-bad">
              <h3>What Sellers Think</h3>
              <p>"We just need to adjust to meet the market"</p>
            </div>
            <div className="lal-psychology-vs">VS</div>
            <div className="lal-psychology-card lal-psychology-reality">
              <h3>What Buyers Think</h3>
              <p>"Something's wrong with this house. Let's lowball them."</p>
            </div>
          </div>
          <p className="lal-section-emphasis">
            Every price reduction is a <span className="lal-gold">public admission of failure</span>—and buyers know it.
          </p>
        </div>
      </section>

      {/* Missed Opportunity Section */}
      <section
        id="missed-opportunity"
        className={`lal-section lal-section-dark lal-animate ${visibleSections['missed-opportunity'] ? 'lal-visible' : ''}`}
      >
        <div className="lal-section-content lal-content-narrow">
          <h2 className="lal-section-title">The Opportunity You're Missing</h2>
          <p className="lal-large-text">
            What if you could <span className="lal-gold">neutralize the need for price reductions</span> before
            they ever become necessary?
          </p>
          <p className="lal-large-text">
            What if buyers saw your listings as <span className="lal-gold">protected investments</span> rather
            than commodities to negotiate down?
          </p>
          <p className="lal-large-text">
            What if you had a tool that <span className="lal-gold">pre-qualifies buyer confidence</span> before
            they even make an offer?
          </p>
        </div>
      </section>

      {/* List & Lock Introduction */}
      <section
        id="how-it-works"
        className={`lal-section lal-animate ${visibleSections['how-it-works'] ? 'lal-visible' : ''}`}
      >
        <div className="lal-section-content">
          <p className="lal-intro-label">Introducing</p>
          <h2 className="lal-intro-title">List & Lock<sup>®</sup></h2>
          <p className="lal-intro-tagline">
            The Rate Lock Strategy That Protects Your Listings from Day One
          </p>
          <div className="lal-intro-explanation">
            <p>
              List & Lock® is a proprietary program from CMG Financial that lets you offer
              buyers a <span className="lal-gold">locked interest rate for up to 90 days</span>—before
              they even make an offer.
            </p>
            <p>
              The result? Buyers move faster. Sellers get stronger offers. And you close
              more deals at full price.
            </p>
          </div>
        </div>
      </section>

      {/* Why It Works - 4 Pillars */}
      <section
        id="why-it-works"
        className={`lal-section lal-section-dark lal-animate ${visibleSections['why-it-works'] ? 'lal-visible' : ''}`}
      >
        <div className="lal-section-content">
          <h2 className="lal-section-title">Why List & Lock® Works</h2>
          <div className="lal-pillars-grid">
            <div className="lal-pillar">
              <div className="lal-pillar-number">01</div>
              <h3 className="lal-pillar-title">Eliminates Buyer Hesitation</h3>
              <p className="lal-pillar-text">
                Rate anxiety is the #1 reason buyers wait. Lock it, and they move.
              </p>
            </div>
            <div className="lal-pillar">
              <div className="lal-pillar-number">02</div>
              <h3 className="lal-pillar-title">Creates Urgency Without Pressure</h3>
              <p className="lal-pillar-text">
                The locked rate has an expiration. Natural motivation, no games.
              </p>
            </div>
            <div className="lal-pillar">
              <div className="lal-pillar-number">03</div>
              <h3 className="lal-pillar-title">Signals Seller Confidence</h3>
              <p className="lal-pillar-text">
                A rate-lock listing says "we're serious"—attracting serious buyers.
              </p>
            </div>
            <div className="lal-pillar">
              <div className="lal-pillar-number">04</div>
              <h3 className="lal-pillar-title">Protects Against Market Shifts</h3>
              <p className="lal-pillar-text">
                If rates rise, your listing is immune. If they fall, buyers can renegotiate down.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* What Buyers See - Yard Sign Comparison */}
      <section
        id="what-buyers-see"
        className={`lal-section lal-animate ${visibleSections['what-buyers-see'] ? 'lal-visible' : ''}`}
      >
        <div className="lal-section-content">
          <h2 className="lal-section-title">What Buyers See</h2>
          <div className="lal-signs-comparison">
            <div className="lal-sign lal-sign-traditional">
              <div className="lal-sign-post" />
              <div className="lal-sign-board">
                <div className="lal-sign-header">FOR SALE</div>
                <div className="lal-sign-content">
                  <span className="lal-sign-price">$425,000</span>
                  <span className="lal-sign-reduced">PRICE REDUCED!</span>
                </div>
                <div className="lal-sign-footer">Call Agent</div>
              </div>
              <p className="lal-sign-label">Traditional Listing</p>
              <p className="lal-sign-subtext">Signals: desperation, problems, negotiate hard</p>
            </div>
            <div className="lal-sign lal-sign-locked">
              <div className="lal-sign-post lal-sign-post-gold" />
              <div className="lal-sign-board lal-sign-board-premium">
                <div className="lal-sign-header lal-sign-header-gold">FOR SALE</div>
                <div className="lal-sign-content">
                  <span className="lal-sign-price">$425,000</span>
                  <span className="lal-sign-locked-rate">🔒 Rate Locked at 6.25%</span>
                </div>
                <div className="lal-sign-footer lal-sign-footer-gold">List & Lock®</div>
              </div>
              <p className="lal-sign-label lal-gold">List & Lock® Listing</p>
              <p className="lal-sign-subtext">Signals: confidence, value, act now</p>
            </div>
          </div>
        </div>
      </section>

      {/* Same Home, Different Outcome */}
      <section
        id="comparison"
        className={`lal-section lal-section-dark lal-animate ${visibleSections['comparison'] ? 'lal-visible' : ''}`}
      >
        <div className="lal-section-content">
          <h2 className="lal-section-title">Same Home. Different Outcome.</h2>
          <div className="lal-comparison-table">
            <div className="lal-comparison-header">
              <div className="lal-comparison-cell" />
              <div className="lal-comparison-cell lal-comparison-traditional">Traditional</div>
              <div className="lal-comparison-cell lal-comparison-locked">List & Lock®</div>
            </div>
            <div className="lal-comparison-row">
              <div className="lal-comparison-cell lal-comparison-label">Avg. Days on Market</div>
              <div className="lal-comparison-cell">34 days</div>
              <div className="lal-comparison-cell lal-gold">18 days</div>
            </div>
            <div className="lal-comparison-row">
              <div className="lal-comparison-cell lal-comparison-label">Price Reduction Rate</div>
              <div className="lal-comparison-cell">73%</div>
              <div className="lal-comparison-cell lal-gold">12%</div>
            </div>
            <div className="lal-comparison-row">
              <div className="lal-comparison-cell lal-comparison-label">Sale-to-List Ratio</div>
              <div className="lal-comparison-cell">96.2%</div>
              <div className="lal-comparison-cell lal-gold">99.1%</div>
            </div>
            <div className="lal-comparison-row">
              <div className="lal-comparison-cell lal-comparison-label">Buyer Confidence</div>
              <div className="lal-comparison-cell">Uncertain</div>
              <div className="lal-comparison-cell lal-gold">Protected</div>
            </div>
          </div>
          <p className="lal-comparison-source">*Based on Q4 2024 CMG List & Lock® program data vs. regional MLS averages</p>
        </div>
      </section>

      {/* CMG Support Section */}
      <section
        id="cmg-support"
        className={`lal-section lal-animate ${visibleSections['cmg-support'] ? 'lal-visible' : ''}`}
      >
        <div className="lal-section-content lal-content-narrow">
          <h2 className="lal-section-title">You're Not Alone</h2>
          <p className="lal-large-text">
            When you partner with CMG Financial, you get more than a rate lock program.
          </p>
          <div className="lal-support-grid">
            <div className="lal-support-item">
              <span className="lal-support-icon">📋</span>
              <span>Co-branded marketing materials</span>
            </div>
            <div className="lal-support-item">
              <span className="lal-support-icon">🎯</span>
              <span>Listing presentation scripts</span>
            </div>
            <div className="lal-support-item">
              <span className="lal-support-icon">📱</span>
              <span>Social media content kit</span>
            </div>
            <div className="lal-support-item">
              <span className="lal-support-icon">🤝</span>
              <span>Dedicated loan officer partner</span>
            </div>
            <div className="lal-support-item">
              <span className="lal-support-icon">📈</span>
              <span>Market rate alerts</span>
            </div>
            <div className="lal-support-item">
              <span className="lal-support-icon">🎓</span>
              <span>Agent certification program</span>
            </div>
          </div>
        </div>
      </section>

      {/* Who It's For */}
      <section
        id="who-its-for"
        className={`lal-section lal-section-dark lal-animate ${visibleSections['who-its-for'] ? 'lal-visible' : ''}`}
      >
        <div className="lal-section-content">
          <h2 className="lal-section-title">Who List & Lock® Is For</h2>
          <div className="lal-audience-grid">
            <div className="lal-audience-card lal-audience-yes">
              <h3>This Is For You If:</h3>
              <ul>
                <li>You're tired of the "reduce the price" conversation</li>
                <li>You want a competitive edge that actually works</li>
                <li>You believe in protecting your sellers' equity</li>
                <li>You're ready to stand out in a commoditized market</li>
                <li>You value strategy over tactics</li>
              </ul>
            </div>
            <div className="lal-audience-card lal-audience-no">
              <h3>This Is NOT For You If:</h3>
              <ul>
                <li>You're comfortable racing to the bottom on price</li>
                <li>You think "the market will figure it out"</li>
                <li>You're not willing to learn something new</li>
                <li>You prioritize volume over value</li>
                <li>You're waiting for the "right time"</li>
              </ul>
            </div>
          </div>
        </div>
      </section>

      {/* Lead Capture Form */}
      <section
        id="lead-capture"
        className={`lal-section lal-animate ${visibleSections['lead-capture'] ? 'lal-visible' : ''}`}
      >
        <div className="lal-section-content lal-content-narrow">
          <h2 className="lal-section-title">Get the Complete List & Lock® Playbook</h2>
          <p className="lal-form-subtitle">
            Free guide includes: listing presentation scripts, objection handlers,
            marketing templates, and the complete rate lock strategy breakdown.
          </p>

          {submitSuccess ? (
            <div className="lal-success-message">
              <div className="lal-success-icon">✓</div>
              <h3>You're In!</h3>
              <p>Check your email for the List & Lock® Playbook. Welcome to the future of real estate.</p>
            </div>
          ) : (
            <form className="lal-form" onSubmit={handleSubmit}>
              <div className="lal-form-group">
                <input
                  type="text"
                  name="name"
                  placeholder="Your Name"
                  value={formData.name}
                  onChange={handleInputChange}
                  required
                />
              </div>
              <div className="lal-form-group">
                <input
                  type="email"
                  name="email"
                  placeholder="Email Address"
                  value={formData.email}
                  onChange={handleInputChange}
                  required
                />
              </div>
              <div className="lal-form-group">
                <input
                  type="text"
                  name="brokerage"
                  placeholder="Brokerage Name (Optional)"
                  value={formData.brokerage}
                  onChange={handleInputChange}
                />
              </div>
              <button
                type="submit"
                className="lal-btn-primary lal-btn-full"
                disabled={isSubmitting}
              >
                {isSubmitting ? 'Sending...' : 'Send Me the Free Guide'}
              </button>
              <p className="lal-form-disclaimer">
                No spam. Unsubscribe anytime. Your info stays with CMG.
              </p>
            </form>
          )}
        </div>
      </section>

      {/* Strategy Call CTA */}
      <section
        id="strategy-call"
        className={`lal-section lal-section-gold lal-animate ${visibleSections['strategy-call'] ? 'lal-visible' : ''}`}
      >
        <div className="lal-section-content lal-content-narrow">
          <h2 className="lal-cta-title">Ready to See It In Action?</h2>
          <p className="lal-cta-text">
            Book a 15-minute strategy walkthrough with a CMG List & Lock® specialist.
            We'll show you exactly how to implement this on your next listing.
          </p>
          <button className="lal-btn-dark">
            Schedule Your Strategy Call →
          </button>
          <p className="lal-cta-note">No pitch. No pressure. Just strategy.</p>
        </div>
      </section>

      {/* Final Thought */}
      <section
        id="final-thought"
        className={`lal-section lal-animate ${visibleSections['final-thought'] ? 'lal-visible' : ''}`}
      >
        <div className="lal-section-content lal-content-narrow">
          <blockquote className="lal-final-quote">
            "In a market where everyone's cutting prices, the agents who
            <span className="lal-gold"> lock in value</span> will be the ones
            still standing when the dust settles."
          </blockquote>
          <p className="lal-final-attribution">— The List & Lock® Philosophy</p>
        </div>
      </section>

      {/* Footer */}
      <footer className="lal-footer">
        <div className="lal-footer-content">
          <div className="lal-footer-brand">
            <span className="lal-logo-icon">🔒</span>
            <span>List & Lock<sup>®</sup></span>
          </div>
          <p className="lal-footer-legal">
            List & Lock® is a registered trademark of CMG Financial.
            NMLS #1820. Equal Housing Lender.
          </p>
          <div className="lal-footer-links">
            <a href="/privacy-policy">Privacy Policy</a>
            <a href="/terms-of-service">Terms of Service</a>
            <a href="/licensing">Licensing</a>
          </div>
          <p className="lal-footer-copyright">
            © {new Date().getFullYear()} CMG Financial. All rights reserved.
          </p>
        </div>
      </footer>
    </div>
  );
}

export default ListAndLockLandingPage;
