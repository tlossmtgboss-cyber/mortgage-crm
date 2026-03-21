import { Link } from 'react-router-dom';
import './PrivacyPolicy.css';

function PrivacyPolicy() {
  return (
    <div className="privacy-policy-page">
      <header className="privacy-header">
        <div className="header-content">
          <Link to="/" className="logo">Perennia AI</Link>
        </div>
      </header>

      <main className="privacy-content">
        <div className="privacy-container">
          <h1>Privacy Policy</h1>
          <p className="last-updated">Last Updated: March 20, 2026</p>

          <section className="privacy-section">
            <h2>1. Introduction</h2>
            <p>
              Perennia AI ("Company," "we," "us," or "our") is committed to protecting your privacy and the security of your personal information. This Privacy Policy describes how we collect, use, disclose, and safeguard your information when you use our mortgage customer relationship management platform and related services (collectively, the "Services").
            </p>
            <p>
              By accessing or using our Services, you agree to this Privacy Policy. If you do not agree with the terms of this Privacy Policy, please do not access or use our Services.
            </p>
          </section>

          <section className="privacy-section">
            <h2>2. Information We Collect</h2>

            <h3>2.1 Personal Information</h3>
            <p>We may collect the following types of personal information:</p>
            <ul>
              <li><strong>Identity Information:</strong> Name, date of birth, Social Security Number (SSN), driver's license number, and government-issued identification</li>
              <li><strong>Contact Information:</strong> Email address, phone number, mailing address, and residential address</li>
              <li><strong>Financial Information:</strong> Income details, employment information, bank account information, credit history, tax returns, and other financial documents</li>
              <li><strong>Property Information:</strong> Property addresses, property values, and mortgage details</li>
              <li><strong>Account Information:</strong> Username, password, and account preferences</li>
            </ul>

            <h3>2.2 Automatically Collected Information</h3>
            <p>When you use our Services, we automatically collect:</p>
            <ul>
              <li>Device information (browser type, operating system, device identifiers)</li>
              <li>IP address and geolocation data</li>
              <li>Usage data (pages viewed, features used, time spent on the platform)</li>
              <li>Cookies and similar tracking technologies</li>
            </ul>
          </section>

          <section className="privacy-section">
            <h2>3. How We Use Your Information</h2>
            <p>We use the information we collect to:</p>
            <ul>
              <li>Provide, maintain, and improve our Services</li>
              <li>Process mortgage applications and facilitate loan transactions</li>
              <li>Verify your identity and prevent fraud</li>
              <li>Communicate with you about your account, transactions, and our Services</li>
              <li>Comply with legal and regulatory requirements</li>
              <li>Analyze usage patterns to enhance user experience</li>
              <li>Provide customer support and respond to inquiries</li>
              <li>Send marketing communications (with your consent)</li>
            </ul>
          </section>

          <section className="privacy-section">
            <h2>4. How We Share Your Information</h2>
            <p>We may share your information with:</p>
            <ul>
              <li><strong>Lending Partners:</strong> To process mortgage applications and facilitate loan approvals</li>
              <li><strong>Service Providers:</strong> Third-party vendors who assist in providing our Services (e.g., cloud hosting, analytics, customer support)</li>
              <li><strong>Credit Bureaus:</strong> To verify creditworthiness and report loan information</li>
              <li><strong>Regulatory Authorities:</strong> As required by law or to comply with legal obligations</li>
              <li><strong>Business Transfers:</strong> In connection with a merger, acquisition, or sale of assets</li>
              <li><strong>With Your Consent:</strong> For any other purpose with your explicit consent</li>
            </ul>
            <p>
              We do not sell your personal information to third parties for marketing purposes.
            </p>
          </section>

          <section className="privacy-section">
            <h2>5. Data Security</h2>
            <p>
              We implement industry-standard security measures to protect your personal information, including:
            </p>
            <ul>
              <li>Encryption of data in transit and at rest using AES-256 encryption</li>
              <li>Secure Socket Layer (SSL) technology for data transmission</li>
              <li>Regular security assessments and penetration testing</li>
              <li>Access controls and authentication mechanisms</li>
              <li>Employee training on data protection and privacy</li>
              <li>Physical security measures at our data centers</li>
            </ul>
            <p>
              While we strive to protect your personal information, no method of transmission over the internet or electronic storage is 100% secure. We cannot guarantee absolute security.
            </p>
          </section>

          <section className="privacy-section">
            <h2>6. Your Rights and Choices</h2>
            <p>Depending on your location, you may have the following rights:</p>
            <ul>
              <li><strong>Access:</strong> Request access to the personal information we hold about you</li>
              <li><strong>Correction:</strong> Request correction of inaccurate or incomplete information</li>
              <li><strong>Deletion:</strong> Request deletion of your personal information (subject to legal retention requirements)</li>
              <li><strong>Portability:</strong> Request a copy of your data in a portable format</li>
              <li><strong>Opt-Out:</strong> Opt out of marketing communications at any time</li>
              <li><strong>Do Not Sell:</strong> Opt out of the sale of your personal information (we do not sell personal information)</li>
            </ul>
            <p>
              To exercise these rights, please contact us at privacy@perenniaai.com.
            </p>
          </section>

          <section className="privacy-section">
            <h2>7. California Privacy Rights (CCPA)</h2>
            <p>
              If you are a California resident, you have additional rights under the California Consumer Privacy Act (CCPA):
            </p>
            <ul>
              <li>Right to know what personal information is collected, used, shared, or sold</li>
              <li>Right to delete personal information held by businesses</li>
              <li>Right to opt out of sale of personal information</li>
              <li>Right to non-discrimination for exercising your CCPA rights</li>
            </ul>
            <p>
              We do not discriminate against you for exercising any of your privacy rights.
            </p>
          </section>

          <section className="privacy-section">
            <h2>8. Gramm-Leach-Bliley Act (GLBA) Compliance</h2>
            <p>
              As a provider of financial services technology, we comply with the Gramm-Leach-Bliley Act (GLBA) and related regulations. This includes:
            </p>
            <ul>
              <li>Providing clear privacy notices about our information practices</li>
              <li>Implementing safeguards to protect nonpublic personal information</li>
              <li>Limiting the sharing of nonpublic personal information with third parties</li>
              <li>Giving you the right to opt out of certain information sharing</li>
            </ul>
          </section>

          <section className="privacy-section">
            <h2>9. Cookies and Tracking Technologies</h2>
            <p>
              We use cookies and similar tracking technologies to enhance your experience on our platform. These include:
            </p>
            <ul>
              <li><strong>Essential Cookies:</strong> Required for the platform to function properly</li>
              <li><strong>Analytics Cookies:</strong> Help us understand how users interact with our Services</li>
              <li><strong>Preference Cookies:</strong> Remember your settings and preferences</li>
            </ul>
            <p>
              You can control cookies through your browser settings. Note that disabling certain cookies may affect the functionality of our Services.
            </p>
          </section>

          <section className="privacy-section">
            <h2>10. Data Retention</h2>
            <p>
              We retain your personal information for as long as necessary to:
            </p>
            <ul>
              <li>Provide our Services to you</li>
              <li>Comply with legal and regulatory requirements (typically 7 years for financial records)</li>
              <li>Resolve disputes and enforce our agreements</li>
              <li>Maintain business records for legitimate purposes</li>
            </ul>
            <p>
              When personal information is no longer needed, we securely delete or anonymize it.
            </p>
          </section>

          <section className="privacy-section">
            <h2>11. Children's Privacy</h2>
            <p>
              Our Services are not intended for individuals under the age of 18. We do not knowingly collect personal information from children. If we become aware that we have collected personal information from a child, we will take steps to delete such information.
            </p>
          </section>

          <section className="privacy-section">
            <h2>12. International Data Transfers</h2>
            <p>
              Your information may be transferred to and processed in countries other than your country of residence. These countries may have different data protection laws. We ensure appropriate safeguards are in place to protect your information when transferred internationally.
            </p>
          </section>

          <section className="privacy-section">
            <h2>13. Third-Party Links</h2>
            <p>
              Our Services may contain links to third-party websites or services. We are not responsible for the privacy practices of these third parties. We encourage you to review the privacy policies of any third-party sites you visit.
            </p>
          </section>

          <section className="privacy-section">
            <h2>14. Changes to This Privacy Policy</h2>
            <p>
              We may update this Privacy Policy from time to time. We will notify you of any material changes by posting the new Privacy Policy on this page and updating the "Last Updated" date. We encourage you to review this Privacy Policy periodically.
            </p>
          </section>

          <section className="privacy-section">
            <h2>15. Contact Us</h2>
            <p>
              If you have any questions about this Privacy Policy or our privacy practices, please contact us at:
            </p>
            <div className="contact-info">
              <p><strong>Perennia AI</strong></p>
              <p>Email: privacy@perenniaai.com</p>
              <p>Website: www.perenniaai.com</p>
            </div>
          </section>

          <div className="back-link">
            <Link to="/">Back to Home</Link>
          </div>
        </div>
      </main>

      <footer className="privacy-footer">
        <p>&copy; {new Date().getFullYear()} Perennia AI. All rights reserved.</p>
      </footer>
    </div>
  );
}

export default PrivacyPolicy;
