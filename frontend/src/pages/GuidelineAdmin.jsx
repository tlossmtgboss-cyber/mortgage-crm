import React, { useState, useEffect, useCallback } from 'react';
import { guidelinesAPI } from '../services/api';
import { toast } from '../utils/toast';
import { usePermissions } from '../contexts/PermissionContext';

function GuidelineAdmin() {
  const { isAdmin } = usePermissions();
  const [guidelines, setGuidelines] = useState([]);
  const [stats, setStats] = useState(null);
  const [isUploading, setIsUploading] = useState(false);

  const [uploadName, setUploadName] = useState('');
  const [uploadType, setUploadType] = useState('agency');
  const [uploadProgram, setUploadProgram] = useState('all');
  const [uploadFile, setUploadFile] = useState(null);

  const fetchGuidelines = useCallback(async () => {
    try {
      const res = await guidelinesAPI.list();
      setGuidelines(res.data?.guidelines || res.data || []);
    } catch (err) {
      toast.error('Failed to load guidelines');
    }
  }, []);

  const fetchStats = useCallback(async () => {
    try {
      const res = await guidelinesAPI.stats();
      setStats(res.data);
    } catch (err) {
      // Stats endpoint may not exist yet
    }
  }, []);

  useEffect(() => {
    fetchGuidelines();
    fetchStats();
  }, [fetchGuidelines, fetchStats]);

  const handleUpload = useCallback(async () => {
    if (!uploadFile || !uploadName) {
      toast.error('Please provide a name and file');
      return;
    }

    setIsUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', uploadFile);
      formData.append('name', uploadName);
      formData.append('guideline_type', uploadType);
      formData.append('loan_program', uploadProgram);

      await guidelinesAPI.upload(formData);
      toast.success('Guideline uploaded — processing will begin shortly');
      setUploadName('');
      setUploadFile(null);
      fetchGuidelines();
      fetchStats();
    } catch (err) {
      toast.error('Upload failed');
    } finally {
      setIsUploading(false);
    }
  }, [uploadFile, uploadName, uploadType, uploadProgram, fetchGuidelines, fetchStats]);

  if (!isAdmin) {
    return <div style={{ padding: 40 }}>Admin access required.</div>;
  }

  return (
    <div style={{ padding: 32, maxWidth: 1000, margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 700, color: '#0f172a', marginBottom: 4 }}>Guideline Management</h1>
          <p style={{ fontSize: 14, color: '#64748b' }}>Upload, manage, and monitor mortgage guideline documents</p>
        </div>
        <a href="/guideline-search" style={{ fontSize: 13, color: '#16a34a' }}>Back to Search</a>
      </div>

      {/* Stats */}
      {stats && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 32 }}>
          <StatCard label="Total Guidelines" value={stats.total_guidelines} />
          <StatCard label="Total Sections" value={stats.total_sections} />
          <StatCard label="Embedded" value={stats.embedded_sections} />
          <StatCard label="Coverage" value={`${stats.embedding_coverage}%`} />
        </div>
      )}

      {/* Upload */}
      <div style={{ background: 'white', border: '1px solid #e2e8f0', borderRadius: 12, padding: 24, marginBottom: 32 }}>
        <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 16 }}>Upload Guideline</h2>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
          <div>
            <label style={{ fontSize: 13, fontWeight: 500, display: 'block', marginBottom: 4 }}>Name</label>
            <input
              type="text"
              value={uploadName}
              onChange={(e) => setUploadName(e.target.value)}
              placeholder="e.g., FHA Handbook 4000.1"
              style={{ width: '100%', padding: '8px 12px', border: '1px solid #e2e8f0', borderRadius: 8, fontSize: 14 }}
            />
          </div>
          <div>
            <label style={{ fontSize: 13, fontWeight: 500, display: 'block', marginBottom: 4 }}>Type</label>
            <select
              value={uploadType}
              onChange={(e) => setUploadType(e.target.value)}
              style={{ width: '100%', padding: '8px 12px', border: '1px solid #e2e8f0', borderRadius: 8, fontSize: 14 }}
            >
              <option value="agency">Agency Guideline</option>
              <option value="investor">Investor Overlay</option>
              <option value="company">Company Overlay</option>
              <option value="state">State Regulation</option>
            </select>
          </div>
          <div>
            <label style={{ fontSize: 13, fontWeight: 500, display: 'block', marginBottom: 4 }}>Loan Program</label>
            <select
              value={uploadProgram}
              onChange={(e) => setUploadProgram(e.target.value)}
              style={{ width: '100%', padding: '8px 12px', border: '1px solid #e2e8f0', borderRadius: 8, fontSize: 14 }}
            >
              <option value="all">All Programs</option>
              <option value="conventional">Conventional</option>
              <option value="fha">FHA</option>
              <option value="va">VA</option>
              <option value="usda">USDA</option>
              <option value="jumbo">Jumbo</option>
              <option value="dscr">DSCR</option>
              <option value="bank_statement">Bank Statement</option>
            </select>
          </div>
          <div>
            <label style={{ fontSize: 13, fontWeight: 500, display: 'block', marginBottom: 4 }}>File (PDF, DOCX, TXT)</label>
            <input
              type="file"
              accept=".pdf,.docx,.txt,.md,.html"
              onChange={(e) => setUploadFile(e.target.files[0])}
              style={{ fontSize: 14 }}
            />
          </div>
        </div>
        <button
          onClick={handleUpload}
          disabled={isUploading || !uploadFile || !uploadName}
          style={{
            padding: '10px 24px', background: isUploading ? '#94a3b8' : '#16a34a',
            color: 'white', border: 'none', borderRadius: 8, fontSize: 14, fontWeight: 600, cursor: 'pointer',
          }}
        >
          {isUploading ? 'Uploading...' : 'Upload & Process'}
        </button>
      </div>

      {/* Guideline List */}
      <div style={{ background: 'white', border: '1px solid #e2e8f0', borderRadius: 12, padding: 24 }}>
        <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 16 }}>
          Uploaded Guidelines ({guidelines.length})
        </h2>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ background: '#f8fafc' }}>
              <th style={{ padding: '8px 12px', textAlign: 'left', borderBottom: '1px solid #e2e8f0' }}>Name</th>
              <th style={{ padding: '8px 12px', textAlign: 'left', borderBottom: '1px solid #e2e8f0' }}>Type</th>
              <th style={{ padding: '8px 12px', textAlign: 'left', borderBottom: '1px solid #e2e8f0' }}>Program</th>
              <th style={{ padding: '8px 12px', textAlign: 'left', borderBottom: '1px solid #e2e8f0' }}>Status</th>
              <th style={{ padding: '8px 12px', textAlign: 'left', borderBottom: '1px solid #e2e8f0' }}>Sections</th>
            </tr>
          </thead>
          <tbody>
            {guidelines.map((g, i) => (
              <tr key={g.id || i}>
                <td style={{ padding: '8px 12px', borderBottom: '1px solid #f1f5f9', fontWeight: 500 }}>{g.name}</td>
                <td style={{ padding: '8px 12px', borderBottom: '1px solid #f1f5f9' }}>{g.guideline_type}</td>
                <td style={{ padding: '8px 12px', borderBottom: '1px solid #f1f5f9' }}>{g.loan_program}</td>
                <td style={{ padding: '8px 12px', borderBottom: '1px solid #f1f5f9' }}>
                  <span style={{
                    padding: '2px 8px', borderRadius: 12, fontSize: 11, fontWeight: 600,
                    background: g.embedding_status === 'complete' ? '#dcfce7' : g.embedding_status === 'processing' ? '#fef3c7' : '#f1f5f9',
                    color: g.embedding_status === 'complete' ? '#16a34a' : g.embedding_status === 'processing' ? '#d97706' : '#64748b',
                  }}>
                    {g.embedding_status || 'pending'}
                  </span>
                </td>
                <td style={{ padding: '8px 12px', borderBottom: '1px solid #f1f5f9' }}>{g.chunk_count || 0}</td>
              </tr>
            ))}
            {guidelines.length === 0 && (
              <tr>
                <td colSpan={5} style={{ padding: 24, textAlign: 'center', color: '#94a3b8' }}>
                  No guidelines uploaded yet. Upload your first guideline above.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function StatCard({ label, value }) {
  return (
    <div style={{ background: 'white', border: '1px solid #e2e8f0', borderRadius: 12, padding: 20, textAlign: 'center' }}>
      <div style={{ fontSize: 28, fontWeight: 700, color: '#0f172a' }}>{value}</div>
      <div style={{ fontSize: 12, color: '#64748b', marginTop: 4 }}>{label}</div>
    </div>
  );
}

export default GuidelineAdmin;
