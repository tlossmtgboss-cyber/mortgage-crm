import React, { useState } from 'react';
import api from '../../services/api.js';
import { toast } from '../../utils/toast.js';

/**
 * AIGenerateButton — clickable button that generates AI content for a field.
 *
 * Props:
 *   fieldType   - string key like "appointment_description", "lead_notes", etc.
 *   context     - object with contextual data (e.g., { name: "Discovery Call", duration: "15 min" })
 *   currentValue - current text value (for regeneration/improvement)
 *   onGenerated - callback(generatedText) called with the AI result
 *   size        - "sm" | "md" (default "sm")
 */
export default function AIGenerateButton({ fieldType, context = {}, currentValue, onGenerated, size = 'sm' }) {
  const [loading, setLoading] = useState(false);

  const handleGenerate = async () => {
    setLoading(true);
    try {
      const response = await api.post('/api/v1/email/ai-generate-text', {
        field_type: fieldType,
        context: context || {},
        current_value: currentValue || null,
      });
      const text = response.data?.text;
      if (text) {
        onGenerated(text);
        toast.success('AI description generated');
      } else {
        toast.error('No text generated');
      }
    } catch (err) {
      toast.error('AI generation failed — try again');
    } finally {
      setLoading(false);
    }
  };

  const btnStyle = {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '5px',
    padding: size === 'sm' ? '4px 10px' : '6px 14px',
    fontSize: size === 'sm' ? '12px' : '13px',
    fontWeight: 600,
    color: '#8b5cf6',
    background: 'rgba(139, 92, 246, 0.08)',
    border: '1px solid rgba(139, 92, 246, 0.25)',
    borderRadius: '6px',
    cursor: loading ? 'wait' : 'pointer',
    opacity: loading ? 0.7 : 1,
    transition: 'all 0.15s',
    whiteSpace: 'nowrap',
  };

  return (
    <button
      type="button"
      style={btnStyle}
      onClick={handleGenerate}
      disabled={loading}
      title="Generate with AI"
      onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(139, 92, 246, 0.15)'; }}
      onMouseLeave={(e) => { e.currentTarget.style.background = 'rgba(139, 92, 246, 0.08)'; }}
    >
      {loading ? (
        <>
          <span style={{ display: 'inline-block', width: 14, height: 14, border: '2px solid rgba(139,92,246,0.3)', borderTopColor: '#8b5cf6', borderRadius: '50%', animation: 'spin 0.6s linear infinite' }} />
          Generating...
        </>
      ) : (
        <>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 2L15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26z" />
          </svg>
          AI Generate
        </>
      )}
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </button>
  );
}
