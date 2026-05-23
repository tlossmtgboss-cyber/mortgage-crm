import React, { useCallback, useRef, useState } from 'react';

import { ContinueButton, FormSection, PanelProps, usePanelData } from './_shared';
import { posApi, API_BASE, getPurlToken } from '../../api';

interface UploadedFile {
  name: string;
  category: string;
  size: number;
  uploadedAt: string;
}

const DOC_CATEGORIES = [
  { key: 'paystubs', label: 'Pay Stubs', desc: 'Most recent 30 days', icon: '💰' },
  { key: 'w2s', label: 'W-2s', desc: 'Last 2 years', icon: '📄' },
  { key: 'tax_returns', label: 'Tax Returns', desc: 'Last 2 years (all pages)', icon: '📋' },
  { key: 'bank_statements', label: 'Bank Statements', desc: 'Last 2 months, all pages', icon: '🏦' },
  { key: 'id', label: 'Photo ID', desc: "Driver's license or passport", icon: '🪪' },
  { key: 'other', label: 'Other Documents', desc: 'Gift letters, divorce decrees, etc.', icon: '📁' },
];

export const DocumentsUploadPanel: React.FC<PanelProps> = ({
  section,
  onChange,
  onComplete,
  application,
  onAskAria,
}) => {
  const { data } = usePanelData(section, onChange);
  const [uploading, setUploading] = useState<string | null>(null);
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>(
    (data.uploaded_files as UploadedFile[]) || [],
  );
  const fileInputRef = useRef<HTMLInputElement>(null);
  const activeCategoryRef = useRef<string>('');

  const handleUploadClick = (category: string) => {
    activeCategoryRef.current = category;
    fileInputRef.current?.click();
  };

  const [uploadError, setUploadError] = useState<string | null>(null);
  const [fileProgress, setFileProgress] = useState<Record<string, 'uploading' | 'done' | 'error'>>({});

  const handleFileChange = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files?.length || !application) return;

    const category = activeCategoryRef.current;
    setUploading(category);
    setUploadError(null);

    const token = getPurlToken();
    const uploadUrl = `${API_BASE}/api/v1/pos/applications/${application.id}/documents/upload`;

    try {
      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        if (file.size > 25 * 1024 * 1024) {
          setUploadError(`${file.name} exceeds the 25 MB limit.`);
          continue;
        }

        const fileKey = `${file.name}-${Date.now()}`;
        setFileProgress(prev => ({ ...prev, [fileKey]: 'uploading' }));

        const formData = new FormData();
        formData.append('file', file);
        formData.append('category', category);

        try {
          const resp = await fetch(uploadUrl, {
            method: 'POST',
            headers: {
              ...(token ? { Authorization: `Bearer ${token}` } : {}),
            },
            body: formData,
            credentials: 'include',
          });

          if (!resp.ok) {
            let detail = 'Upload failed';
            try {
              const err = await resp.json();
              detail = err.detail || detail;
            } catch { /* ignore parse errors */ }
            setFileProgress(prev => ({ ...prev, [fileKey]: 'error' }));
            setUploadError(`${file.name}: ${detail}`);
            continue;
          }

          setFileProgress(prev => ({ ...prev, [fileKey]: 'done' }));
          const uploaded: UploadedFile = {
            name: file.name,
            category,
            size: file.size,
            uploadedAt: new Date().toISOString(),
          };
          setUploadedFiles(prev => {
            const updated = [...prev, uploaded];
            onChange({ ...data, uploaded_files: updated });
            return updated;
          });
        } catch (err: any) {
          setFileProgress(prev => ({ ...prev, [fileKey]: 'error' }));
          setUploadError(`${file.name}: ${err?.message || 'Network error'}`);
        }
      }
    } finally {
      setUploading(null);
      setFileProgress({});
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  }, [application, data, onChange]);

  const filesForCategory = (key: string) => uploadedFiles.filter(f => f.category === key);

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const handleContinue = async () => {
    if (!application) return;
    setUploadError(null);
    try {
      await posApi.updateSection(application.id, 'documents_upload', {
        data: { ...data, uploaded_files: uploadedFiles },
        mark_complete: true,
      });
      onComplete();
    } catch (err: any) {
      setUploadError(err?.message || 'Failed to save. Please try again.');
    }
  };

  return (
    <>
      <p className="urla-form-section__desc">
        Upload your supporting documents now to speed up processing.
        You can always add more later from the Documents tab.
      </p>

      {uploadError && (
        <div role="alert" style={{
          background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 8,
          padding: '12px 16px', marginBottom: 16,
        }}>
          <p style={{ fontWeight: 600, color: '#991b1b', margin: 0, fontSize: 14 }}>{uploadError}</p>
        </div>
      )}

      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept=".pdf,.jpg,.jpeg,.png,.heic,.doc,.docx"
        style={{ display: 'none' }}
        onChange={handleFileChange}
      />

      <FormSection>
        <div className="urla-field urla-field--cols-4">
          <div style={{ display: 'grid', gap: 12 }}>
            {DOC_CATEGORIES.map(cat => {
              const files = filesForCategory(cat.key);
              const isUploading = uploading === cat.key;
              return (
                <div key={cat.key} style={{
                  display: 'flex', alignItems: 'center', gap: 14,
                  padding: '14px 16px', borderRadius: 12,
                  background: files.length ? 'var(--bt-primary-tint, #EFF3EE)' : 'var(--bt-bg-soft, #FBF8F2)',
                  border: `1px solid ${files.length ? 'var(--bt-success, #2D7A52)' : 'var(--bt-border, #ECE6D8)'}`,
                  transition: 'all 0.2s',
                }}>
                  <span style={{ fontSize: 24 }}>{cat.icon}</span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 600, fontSize: 14, color: 'var(--bt-text-primary)' }}>{cat.label}</div>
                    <div style={{ fontSize: 12, color: 'var(--bt-text-muted)', marginTop: 2 }}>{cat.desc}</div>
                    {files.length > 0 && (
                      <div style={{ fontSize: 12, color: 'var(--bt-success)', marginTop: 4, fontWeight: 500 }}>
                        {files.length} file{files.length > 1 ? 's' : ''} uploaded
                        ({files.map(f => f.name).join(', ')})
                      </div>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={() => handleUploadClick(cat.key)}
                    disabled={isUploading}
                    style={{
                      padding: '8px 16px', borderRadius: 8, border: 'none',
                      background: files.length ? 'var(--bt-bg-elevated)' : 'var(--bt-primary)',
                      color: files.length ? 'var(--bt-text-primary)' : '#fff',
                      fontSize: 13, fontWeight: 600, cursor: 'pointer',
                      opacity: isUploading ? 0.5 : 1,
                    }}
                  >
                    {isUploading ? 'Uploading...' : files.length ? 'Add More' : 'Upload'}
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      </FormSection>

      {onAskAria && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 12,
          padding: '14px 18px', borderRadius: 12, marginTop: 8,
          background: 'var(--bt-accent-light, #F5EDD9)',
          border: '1px solid var(--bt-accent, #B8924A)',
        }}>
          <span style={{ fontSize: 14, color: 'var(--bt-text-secondary)', flex: 1 }}>
            Not sure which documents you need?
          </span>
          <button type="button" onClick={onAskAria} style={{
            padding: '8px 16px', borderRadius: 8, border: 'none',
            background: 'var(--bt-primary)', color: '#fff',
            fontSize: 13, fontWeight: 600, cursor: 'pointer',
          }}>
            Ask Aria
          </button>
        </div>
      )}

      <ContinueButton
        onClick={handleContinue}
        label={uploadedFiles.length > 0 ? 'Save & Continue' : 'Skip for Now'}
      />
    </>
  );
};
