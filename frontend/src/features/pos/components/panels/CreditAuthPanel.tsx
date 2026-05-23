import React, { useEffect, useState } from 'react';

import { ContinueButton, FormSection, PanelProps, usePanelData } from './_shared';
import { posApi } from '../../api';
import { validateSection } from '../../schemas/urla';

export const CreditAuthPanel: React.FC<PanelProps> = ({
  section,
  onChange,
  onComplete,
  application,
}) => {
  const { data, updateField } = usePanelData(section, onChange);
  const [agreed, setAgreed] = useState((data.authorization_granted as boolean) || false);
  const [errors, setErrors] = useState<{ path: string; message: string }[]>([]);

  useEffect(() => {
    if (data.authorization_granted != null) setAgreed(Boolean(data.authorization_granted));
  }, [data.authorization_granted]);

  const handleContinue = async () => {
    if (!application || !agreed) return;
    const submitData = {
      ...data,
      authorization_granted: true,
      borrower_name: data.borrower_name || '',
    };
    const result = validateSection('credit_auth', submitData);
    if (!result.ok) {
      setErrors((result as { ok: false; issues: { path: string; message: string }[] }).issues);
      return;
    }
    setErrors([]);
    await posApi.updateSection(application.id, 'credit_auth', {
      data: submitData,
      mark_complete: true,
    });
    onComplete();
  };

  return (
    <>
      <p className="urla-form-section__desc">
        To proceed with your application, we need your permission to pull a credit report.
        This is a standard part of the mortgage process.
      </p>

      {errors.length > 0 && (
        <div className="pos-validation-errors" role="alert" style={{
          background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 8,
          padding: '12px 16px', marginBottom: 16,
        }}>
          <p style={{ fontWeight: 600, color: '#991b1b', margin: '0 0 8px', fontSize: 14 }}>
            Please fix the following before continuing:
          </p>
          <ul style={{ margin: 0, paddingLeft: 20, color: '#b91c1c', fontSize: 13, lineHeight: 1.6 }}>
            {errors.map((err, i) => (
              <li key={i}>{err.path ? `${err.path}: ` : ''}{err.message}</li>
            ))}
          </ul>
        </div>
      )}

      <FormSection>
        <div className="urla-field urla-field--cols-4">
          <div style={{
            padding: '24px', borderRadius: 14,
            background: 'var(--bt-bg-soft, #FBF8F2)',
            border: '1px solid var(--bt-border, #ECE6D8)',
          }}>
            <h4 style={{
              margin: '0 0 16px', fontSize: 16, fontWeight: 600,
              color: 'var(--bt-text-primary)',
              fontFamily: 'var(--bt-font-display)',
            }}>
              Credit Report Authorization
            </h4>

            <div style={{ fontSize: 14, lineHeight: 1.7, color: 'var(--bt-text-secondary)' }}>
              <p style={{ margin: '0 0 12px' }}>
                By checking the box below, I authorize the lender and its agents to:
              </p>
              <ul style={{ margin: '0 0 16px', paddingLeft: 20 }}>
                <li>Obtain my credit report from one or more consumer reporting agencies</li>
                <li>Use the information to evaluate my mortgage application</li>
                <li>Verify my employment, income, and assets as needed</li>
                <li>Share credit information with investors, insurers, and service providers involved in my loan</li>
              </ul>
              <p style={{ margin: '0 0 12px' }}>
                I understand that this authorization is valid for 120 days from the date of my application
                and that a hard credit inquiry will be recorded on my credit report.
              </p>
              <p style={{ margin: 0, fontSize: 13, color: 'var(--bt-text-muted)' }}>
                Under the Fair Credit Reporting Act (FCRA), you have the right to know what is in your
                credit file and to dispute any inaccurate information.
              </p>
            </div>
          </div>
        </div>
      </FormSection>

      <FormSection>
        <div className="urla-field urla-field--cols-4">
          <label style={{
            display: 'flex', alignItems: 'flex-start', gap: 14,
            padding: '18px 20px', borderRadius: 12, cursor: 'pointer',
            background: agreed ? 'var(--bt-primary-tint, #EFF3EE)' : '#fff',
            border: `2px solid ${agreed ? 'var(--bt-primary, #1F3D2E)' : 'var(--bt-border, #ECE6D8)'}`,
            transition: 'all 0.2s',
          }}>
            <input
              type="checkbox"
              checked={agreed}
              onChange={e => {
                setAgreed(e.target.checked);
                updateField('authorization_granted', e.target.checked);
              }}
              style={{
                width: 20, height: 20, marginTop: 2,
                accentColor: 'var(--bt-primary, #1F3D2E)',
                flexShrink: 0,
              }}
            />
            <div>
              <div style={{ fontWeight: 600, fontSize: 15, color: 'var(--bt-text-primary)', marginBottom: 4 }}>
                I agree to the credit report authorization
              </div>
              <div style={{ fontSize: 13, color: 'var(--bt-text-muted)', lineHeight: 1.5 }}>
                I have read and understand the terms above and authorize the lender to obtain my credit report.
              </div>
            </div>
          </label>
        </div>
      </FormSection>

      <div style={{
        display: 'flex', alignItems: 'center', gap: 10,
        padding: '12px 16px', borderRadius: 10, marginTop: 8,
        background: '#f0fdf4', border: '1px solid #bbf7d0',
      }}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#15803d" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="3" y="11" width="18" height="11" rx="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" />
        </svg>
        <span style={{ fontSize: 13, color: '#15803d', fontWeight: 500 }}>
          Your data is encrypted with 256-bit SSL and never shared without your consent.
        </span>
      </div>

      <ContinueButton
        onClick={handleContinue}
        disabled={!agreed}
      />
    </>
  );
};
