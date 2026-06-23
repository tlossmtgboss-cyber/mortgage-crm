import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';

const API_BASE = import.meta.env.VITE_API_URL || 'https://api.perenniaai.com';
const APP_BASE = 'https://recruit.perenniaai.com';

const styles = {
  root: {
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
    background: '#f8fafc',
    minHeight: '100vh',
    padding: '0',
  },
  header: {
    background: '#0f172a',
    color: '#fff',
    padding: '20px 24px 18px',
  },
  headerTitle: {
    fontSize: 20,
    fontWeight: 700,
    margin: 0,
  },
  headerSub: {
    fontSize: 13,
    color: 'rgba(255,255,255,0.55)',
    marginTop: 3,
  },
  list: {
    padding: '20px 16px',
    display: 'flex',
    flexDirection: 'column',
    gap: 12,
    maxWidth: 680,
    margin: '0 auto',
  },
  card: {
    background: '#fff',
    border: '1px solid #e2e8f0',
    borderRadius: 10,
    padding: '18px 20px',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: 16,
  },
  cardInfo: {
    flex: 1,
  },
  jobTitle: {
    fontSize: 16,
    fontWeight: 700,
    color: '#0f172a',
    margin: '0 0 6px',
  },
  metaRow: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: 8,
    alignItems: 'center',
  },
  meta: {
    fontSize: 12.5,
    color: '#64748b',
  },
  remoteBadge: {
    display: 'inline-block',
    padding: '2px 8px',
    background: '#dcfce7',
    color: '#166534',
    borderRadius: 999,
    fontSize: 11.5,
    fontWeight: 700,
  },
  deptBadge: {
    display: 'inline-block',
    padding: '2px 8px',
    background: '#e0f2fe',
    color: '#0369a1',
    borderRadius: 999,
    fontSize: 11.5,
    fontWeight: 600,
  },
  applyBtn: {
    display: 'inline-block',
    padding: '9px 18px',
    background: '#1d4ed8',
    color: '#fff',
    border: 'none',
    borderRadius: 8,
    fontSize: 13.5,
    fontWeight: 700,
    cursor: 'pointer',
    textDecoration: 'none',
    whiteSpace: 'nowrap',
    transition: 'background 0.12s',
    flexShrink: 0,
  },
  empty: {
    textAlign: 'center',
    padding: '48px 24px',
    color: '#94a3b8',
    fontSize: 15,
  },
  loading: {
    textAlign: 'center',
    padding: '48px 24px',
    color: '#64748b',
    fontSize: 14,
  },
};

export default function JobsPublic() {
  const { orgSlug } = useParams();
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [orgName, setOrgName] = useState('');

  useEffect(() => {
    fetch(`${API_BASE}/api/v1/recruit-platform/jobs?tenant_slug=${encodeURIComponent(orgSlug)}`)
      .then(r => r.ok ? r.json() : [])
      .then(data => {
        const list = Array.isArray(data) ? data : (data.items || data.jobs || []);
        setJobs(list);
        if (list[0]?.org_name) setOrgName(list[0].org_name);
      })
      .catch(() => setJobs([]))
      .finally(() => setLoading(false));

    // Fetch org name separately if not in jobs
    fetch(`${API_BASE}/api/v1/recruit-platform/apply/${orgSlug}`)
      .then(r => r.ok ? r.json() : {})
      .then(data => { if (data.org_name || data.name) setOrgName(data.org_name || data.name); })
      .catch(() => {});
  }, [orgSlug]);

  function applyUrl(job) {
    return `${APP_BASE}/recruit/apply/${orgSlug}?job=${job.id}`;
  }

  return (
    <div style={styles.root}>
      <div style={styles.header}>
        <h1 style={styles.headerTitle}>{orgName || orgSlug} — Open Positions</h1>
        <div style={styles.headerSub}>Join our team</div>
      </div>

      {loading ? (
        <div style={styles.loading}>Loading positions…</div>
      ) : jobs.length === 0 ? (
        <div style={styles.empty}>
          <div style={{ fontSize: 36, marginBottom: 12 }}>🏢</div>
          No positions currently open. Check back soon!
        </div>
      ) : (
        <div style={styles.list}>
          {jobs.map(job => (
            <div key={job.id} style={styles.card}>
              <div style={styles.cardInfo}>
                <h2 style={styles.jobTitle}>{job.title}</h2>
                <div style={styles.metaRow}>
                  {job.department && <span style={styles.deptBadge}>{job.department}</span>}
                  {job.location && <span style={styles.meta}>📍 {job.location}</span>}
                  {(job.remote || job.is_remote) && <span style={styles.remoteBadge}>Remote</span>}
                  {job.employment_type && <span style={styles.meta}>· {job.employment_type}</span>}
                </div>
                {job.description && (
                  <p style={{ fontSize: 13, color: '#475569', marginTop: 8, marginBottom: 0, lineHeight: 1.5 }}>
                    {job.description.length > 160 ? job.description.slice(0, 157) + '…' : job.description}
                  </p>
                )}
              </div>
              <a
                href={applyUrl(job)}
                style={styles.applyBtn}
                target="_top"
                rel="noopener noreferrer"
              >
                Apply Now
              </a>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
