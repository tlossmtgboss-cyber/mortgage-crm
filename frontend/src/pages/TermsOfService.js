import { Link } from 'react-router-dom';
import './TermsOfService.css';

function TermsOfService() {
  return (
    <div className="terms-page">
      <header className="terms-header">
        <div className="header-content">
          <Link to="/" className="logo">Perennia AI</Link>
        </div>
      </header>

      <main className="terms-content">
        <div className="terms-container">
          <h1>Terms of Service</h1>
          <p className="last-updated">Last Updated: January 1, 2025</p>

          <section className="terms-section">
            <h2>1. Acceptance of Terms</h2>
            <p>
              Welcome to Perennia AI. These Terms of Service ("Terms") govern your access to and use of the Perennia AI platform, website, applications, and related services (collectively, the "Services") provided by Perennia AI ("Company," "we," "us," or "our").
            </p>
            <p>
              By accessing or using our Services, you agree to be bound by these Terms. If you do not agree to these Terms, you may not access or use our Services. If you are using the Services on behalf of an organization, you represent and warrant that you have the authority to bind that organization to these Terms.
            </p>
          </section>

          <section className="terms-section">
            <h2>2. Description of Services</h2>
            <p>
              Perennia AI provides a cloud-based customer relationship management (CRM) platform designed specifically for mortgage professionals. Our Services include, but are not limited to:
            </p>
            <ul>
              <li>Lead management and tracking</li>
              <li>Loan pipeline management</li>
              <li>Document collection and management</li>
              <li>Client communication tools</li>
              <li>AI-powered automation and insights</li>
              <li>Compliance tracking and reporting</li>
              <li>Integration with third-party services</li>
            </ul>
          </section>

          <section className="terms-section">
            <h2>3. Account Registration and Security</h2>

            <h3>3.1 Account Creation</h3>
            <p>
              To use certain features of our Services, you must register for an account. You agree to provide accurate, current, and complete information during the registration process and to update such information to keep it accurate, current, and complete.
            </p>

            <h3>3.2 Account Security</h3>
            <p>
              You are responsible for safeguarding your account credentials and for all activities that occur under your account. You agree to:
            </p>
            <ul>
              <li>Maintain the confidentiality of your password</li>
              <li>Notify us immediately of any unauthorized access or use of your account</li>
              <li>Use strong, unique passwords and enable multi-factor authentication when available</li>
              <li>Not share your account credentials with any third party</li>
            </ul>

            <h3>3.3 Account Termination</h3>
            <p>
              We reserve the right to suspend or terminate your account if you violate these Terms or if we reasonably believe that your use of the Services may harm us, other users, or third parties.
            </p>
          </section>

          <section className="terms-section">
            <h2>4. Acceptable Use Policy</h2>
            <p>You agree not to use our Services to:</p>
            <ul>
              <li>Violate any applicable laws, regulations, or third-party rights</li>
              <li>Upload or transmit viruses, malware, or other malicious code</li>
              <li>Interfere with or disrupt the integrity or performance of the Services</li>
              <li>Attempt to gain unauthorized access to the Services or related systems</li>
              <li>Engage in any fraudulent, deceptive, or misleading practices</li>
              <li>Harass, abuse, or harm another person or entity</li>
              <li>Collect or store personal data about other users without their consent</li>
              <li>Use the Services for any purpose other than legitimate mortgage business operations</li>
              <li>Resell, sublicense, or redistribute the Services without authorization</li>
              <li>Reverse engineer, decompile, or disassemble any part of the Services</li>
            </ul>
          </section>

          <section className="terms-section">
            <h2>5. Subscription and Payment Terms</h2>

            <h3>5.1 Subscription Plans</h3>
            <p>
              Access to our Services requires a paid subscription. Subscription plans, features, and pricing are described on our website and may be updated from time to time. We will provide notice of any material changes to pricing.
            </p>

            <h3>5.2 Billing and Payment</h3>
            <p>
              By subscribing to our Services, you authorize us to charge your designated payment method for the applicable subscription fees. Fees are billed in advance on a monthly or annual basis, depending on your chosen plan.
            </p>

            <h3>5.3 Automatic Renewal</h3>
            <p>
              Your subscription will automatically renew at the end of each billing period unless you cancel before the renewal date. You may cancel your subscription at any time through your account settings.
            </p>

            <h3>5.4 Refunds</h3>
            <p>
              Subscription fees are non-refundable except as required by law or as expressly stated in these Terms. If you cancel your subscription, you will continue to have access to the Services until the end of your current billing period.
            </p>

            <h3>5.5 Taxes</h3>
            <p>
              All fees are exclusive of applicable taxes, and you are responsible for paying any taxes associated with your use of the Services.
            </p>
          </section>

          <section className="terms-section">
            <h2>6. Data and Privacy</h2>

            <h3>6.1 Your Data</h3>
            <p>
              You retain all rights to the data you submit to the Services ("Your Data"). You grant us a limited license to use, store, and process Your Data solely to provide and improve the Services.
            </p>

            <h3>6.2 Data Protection</h3>
            <p>
              We implement industry-standard security measures to protect Your Data. However, no method of electronic storage is 100% secure, and we cannot guarantee absolute security. You are responsible for maintaining backups of Your Data.
            </p>

            <h3>6.3 Privacy Policy</h3>
            <p>
              Our collection and use of personal information is governed by our <Link to="/privacy-policy">Privacy Policy</Link>, which is incorporated into these Terms by reference.
            </p>

            <h3>6.4 Data Portability</h3>
            <p>
              Upon request, we will provide you with a copy of Your Data in a commonly used format. Upon termination of your account, we will retain Your Data for a reasonable period to allow for data export, after which it may be deleted.
            </p>
          </section>

          <section className="terms-section">
            <h2>7. Intellectual Property</h2>

            <h3>7.1 Our Intellectual Property</h3>
            <p>
              The Services, including all software, designs, text, graphics, logos, and other content, are owned by Perennia AI or our licensors and are protected by copyright, trademark, and other intellectual property laws. You may not copy, modify, distribute, or create derivative works without our prior written consent.
            </p>

            <h3>7.2 License to Use Services</h3>
            <p>
              Subject to these Terms, we grant you a limited, non-exclusive, non-transferable, revocable license to access and use the Services for your internal business purposes during your subscription term.
            </p>

            <h3>7.3 Feedback</h3>
            <p>
              If you provide us with feedback, suggestions, or ideas about the Services, you grant us a perpetual, irrevocable, royalty-free license to use such feedback for any purpose without compensation to you.
            </p>
          </section>

          <section className="terms-section">
            <h2>8. Third-Party Services and Integrations</h2>
            <p>
              Our Services may integrate with or provide access to third-party services, applications, or websites. These third-party services are governed by their own terms and privacy policies. We are not responsible for the content, functionality, or practices of any third-party services.
            </p>
            <p>
              Your use of third-party integrations may require you to agree to additional terms and may result in fees charged by the third-party provider.
            </p>
          </section>

          <section className="terms-section">
            <h2>9. Compliance with Laws</h2>
            <p>
              You agree to use the Services in compliance with all applicable laws and regulations, including but not limited to:
            </p>
            <ul>
              <li>Real Estate Settlement Procedures Act (RESPA)</li>
              <li>Truth in Lending Act (TILA)</li>
              <li>Equal Credit Opportunity Act (ECOA)</li>
              <li>Fair Housing Act</li>
              <li>Gramm-Leach-Bliley Act (GLBA)</li>
              <li>State mortgage licensing requirements</li>
              <li>Consumer Financial Protection Bureau (CFPB) regulations</li>
              <li>CAN-SPAM Act and applicable telemarketing laws</li>
            </ul>
            <p>
              While our Services include compliance features, you are solely responsible for ensuring your use of the Services complies with applicable laws.
            </p>
          </section>

          <section className="terms-section">
            <h2>10. Disclaimers</h2>

            <h3>10.1 "As Is" Basis</h3>
            <p>
              THE SERVICES ARE PROVIDED "AS IS" AND "AS AVAILABLE" WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO IMPLIED WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, AND NON-INFRINGEMENT.
            </p>

            <h3>10.2 No Guarantee</h3>
            <p>
              We do not warrant that the Services will be uninterrupted, error-free, or completely secure. We do not guarantee any specific results from your use of the Services.
            </p>

            <h3>10.3 Professional Advice</h3>
            <p>
              The Services are not intended to provide legal, financial, or compliance advice. You should consult with qualified professionals for advice specific to your situation.
            </p>
          </section>

          <section className="terms-section">
            <h2>11. Limitation of Liability</h2>
            <p>
              TO THE MAXIMUM EXTENT PERMITTED BY LAW, IN NO EVENT SHALL PERENNIA AI, ITS AFFILIATES, OFFICERS, DIRECTORS, EMPLOYEES, OR AGENTS BE LIABLE FOR:
            </p>
            <ul>
              <li>Any indirect, incidental, special, consequential, or punitive damages</li>
              <li>Loss of profits, revenue, data, or business opportunities</li>
              <li>Any damages arising from your use of or inability to use the Services</li>
              <li>Any damages arising from unauthorized access to or alteration of your data</li>
            </ul>
            <p>
              OUR TOTAL LIABILITY FOR ALL CLAIMS ARISING OUT OF OR RELATED TO THESE TERMS OR THE SERVICES SHALL NOT EXCEED THE AMOUNT YOU PAID US IN THE TWELVE (12) MONTHS PRECEDING THE CLAIM.
            </p>
          </section>

          <section className="terms-section">
            <h2>12. Indemnification</h2>
            <p>
              You agree to indemnify, defend, and hold harmless Perennia AI and its affiliates, officers, directors, employees, and agents from and against any claims, liabilities, damages, losses, and expenses (including reasonable attorneys' fees) arising out of or related to:
            </p>
            <ul>
              <li>Your use of the Services</li>
              <li>Your violation of these Terms</li>
              <li>Your violation of any applicable laws or regulations</li>
              <li>Your violation of any third-party rights</li>
              <li>Any data or content you submit to the Services</li>
            </ul>
          </section>

          <section className="terms-section">
            <h2>13. Modifications to Terms</h2>
            <p>
              We may modify these Terms at any time. If we make material changes, we will notify you by email or by posting a notice on our website at least thirty (30) days before the changes take effect. Your continued use of the Services after the effective date of any changes constitutes your acceptance of the modified Terms.
            </p>
          </section>

          <section className="terms-section">
            <h2>14. Termination</h2>
            <p>
              Either party may terminate these Terms at any time. You may terminate by canceling your subscription and ceasing use of the Services. We may terminate or suspend your access to the Services immediately if you breach these Terms.
            </p>
            <p>
              Upon termination, your right to use the Services will immediately cease. Provisions of these Terms that by their nature should survive termination will survive, including intellectual property rights, disclaimers, limitations of liability, and indemnification.
            </p>
          </section>

          <section className="terms-section">
            <h2>15. Dispute Resolution</h2>

            <h3>15.1 Governing Law</h3>
            <p>
              These Terms shall be governed by and construed in accordance with the laws of the State of Delaware, without regard to its conflict of law provisions.
            </p>

            <h3>15.2 Arbitration</h3>
            <p>
              Any dispute arising out of or relating to these Terms or the Services shall be resolved by binding arbitration in accordance with the rules of the American Arbitration Association. The arbitration shall take place in Delaware, and the arbitrator's decision shall be final and binding.
            </p>

            <h3>15.3 Class Action Waiver</h3>
            <p>
              You agree that any dispute resolution proceedings will be conducted only on an individual basis and not in a class, consolidated, or representative action.
            </p>
          </section>

          <section className="terms-section">
            <h2>16. General Provisions</h2>

            <h3>16.1 Entire Agreement</h3>
            <p>
              These Terms, together with our Privacy Policy and any other agreements referenced herein, constitute the entire agreement between you and Perennia AI regarding the Services.
            </p>

            <h3>16.2 Severability</h3>
            <p>
              If any provision of these Terms is found to be unenforceable, the remaining provisions will continue in full force and effect.
            </p>

            <h3>16.3 Waiver</h3>
            <p>
              Our failure to enforce any provision of these Terms shall not be deemed a waiver of such provision or our right to enforce it later.
            </p>

            <h3>16.4 Assignment</h3>
            <p>
              You may not assign or transfer these Terms or your rights under them without our prior written consent. We may assign these Terms without restriction.
            </p>

            <h3>16.5 Force Majeure</h3>
            <p>
              We shall not be liable for any failure or delay in performance due to circumstances beyond our reasonable control, including natural disasters, war, terrorism, labor disputes, or government actions.
            </p>
          </section>

          <section className="terms-section">
            <h2>17. Contact Information</h2>
            <p>
              If you have any questions about these Terms, please contact us at:
            </p>
            <div className="contact-info">
              <p><strong>Perennia AI</strong></p>
              <p>Email: legal@perenniaai.com</p>
              <p>Website: www.perenniaai.com</p>
            </div>
          </section>

          <div className="back-link">
            <Link to="/">Back to Home</Link>
          </div>
        </div>
      </main>

      <footer className="terms-footer">
        <p>&copy; 2025 Perennia AI. All rights reserved.</p>
      </footer>
    </div>
  );
}

export default TermsOfService;
