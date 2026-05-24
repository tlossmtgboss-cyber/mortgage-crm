import React, { useState, useCallback, useRef, useEffect } from 'react';
import { guidelinesAPI } from '../services/api';
import { toast } from '../utils/toast';
import { usePermissions } from '../contexts/PermissionContext';
import { sanitizeHTML } from '../utils/sanitize';
import './GuidelineSearch.css';

const SOURCE_GROUPS = [
  {
    label: 'Agency',
    sources: [
      { id: 'conventional', label: 'Fannie Mae (Conv)' },
      { id: 'freddie_mac', label: 'Freddie Mac' },
      { id: 'fha', label: 'FHA' },
      { id: 'va', label: 'VA' },
      { id: 'usda', label: 'USDA' },
    ],
  },
  {
    label: 'Non-QM',
    sources: [
      { id: 'dscr', label: 'DSCR' },
      { id: 'bank_statement', label: 'Bank Statement' },
      { id: 'asset_depletion', label: 'Asset Depletion' },
      { id: 'p_and_l', label: 'P&L Only' },
      { id: '1099', label: '1099' },
      { id: 'foreign_national', label: 'Foreign National' },
      { id: 'itin', label: 'ITIN' },
    ],
  },
  {
    label: 'Specialty',
    sources: [
      { id: 'jumbo', label: 'Jumbo' },
      { id: 'heloc', label: 'HELOC' },
      { id: 'construction', label: 'Construction' },
      { id: 'renovation', label: 'Renovation' },
      { id: 'reverse_mortgage', label: 'Reverse Mortgage' },
      { id: 'dpa', label: 'Down Payment Assistance' },
      { id: 'aio', label: 'AIO' },
      { id: 'portfolio', label: 'Portfolio' },
    ],
  },
];

const SAVED_QUERIES = [
  'FHA credit score requirements',
  'VA funding fee chart',
  'Conventional DTI limits',
  'Gift fund rules by program',
  'Self-employment income calculation',
];

function GuidelineSearch() {
  const { isAdmin } = usePermissions();
  const [query, setQuery] = useState('');
  const [selectedSources, setSelectedSources] = useState(new Set());
  const [activeTab, setActiveTab] = useState('answer');
  const [isSearching, setIsSearching] = useState(false);
  const [result, setResult] = useState(null);
  const [comparisonData, setComparisonData] = useState(null);
  const textareaRef = useRef(null);
  const debounceRef = useRef(null);

  const toggleSource = useCallback((sourceId) => {
    setSelectedSources((prev) => {
      const next = new Set(prev);
      if (next.has(sourceId)) {
        next.delete(sourceId);
      } else {
        next.add(sourceId);
      }
      return next;
    });
  }, []);

  const handleSearch = useCallback(async () => {
    if (!query.trim()) return;

    setIsSearching(true);
    setResult(null);
    setComparisonData(null);
    setActiveTab('answer');

    try {
      const agencies = selectedSources.size > 0 ? Array.from(selectedSources) : undefined;
      const response = await guidelinesAPI.search(query.trim(), {
        agencies,
        top_k: 8,
      });
      setResult(response.data);
    } catch (err) {
      toast.error('Search failed. Please try again.');
    } finally {
      setIsSearching(false);
    }
  }, [query, selectedSources]);

  const debouncedSearch = useCallback(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      handleSearch();
    }, 300);
  }, [handleSearch]);

  const handleKeyDown = useCallback((e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      debouncedSearch();
    }
  }, [debouncedSearch]);

  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  const handleSavedQuery = useCallback((q) => {
    setQuery(q);
    setTimeout(() => {
      setQuery(q);
      handleSearch();
    }, 0);
  }, [handleSearch]);

  const handleViewComparison = useCallback(async (topic) => {
    try {
      const response = await guidelinesAPI.compare(topic);
      setComparisonData(response.data);
      setActiveTab('comparison');
    } catch (err) {
      toast.error('Failed to load comparison chart.');
    }
  }, []);

  const handleCopyAnswer = useCallback(() => {
    if (result?.answer) {
      navigator.clipboard.writeText(result.answer);
      toast.success('Answer copied to clipboard');
    }
  }, [result]);

  return (
    <div className="guideline-search-page">
      {/* Left Sidebar */}
      <aside className="gs-sidebar">
        <div className="gs-sidebar-header">
          <div className="gs-sidebar-title">Guideline Search</div>
          <div className="gs-sidebar-subtitle">RAG-powered mortgage guidelines</div>
        </div>

        <div className="gs-source-section">
          {SOURCE_GROUPS.map((group) => (
            <div key={group.label} style={{ marginBottom: 16 }}>
              <div className="gs-source-group-label">{group.label}</div>
              {group.sources.map((source) => (
                <div key={source.id} className="gs-source-item">
                  <input
                    type="checkbox"
                    id={`src-${source.id}`}
                    checked={selectedSources.has(source.id)}
                    onChange={() => toggleSource(source.id)}
                  />
                  <label htmlFor={`src-${source.id}`}>{source.label}</label>
                </div>
              ))}
            </div>
          ))}
        </div>

        <div className="gs-library-section">
          <div className="gs-library-title">Library</div>
          {SAVED_QUERIES.map((q, i) => (
            <div
              key={i}
              className="gs-library-item"
              onClick={() => handleSavedQuery(q)}
            >
              {q}
            </div>
          ))}
        </div>

        {isAdmin && (
          <div className="gs-admin-link">
            <a href="/guideline-admin">Manage Guidelines</a>
          </div>
        )}
      </aside>

      {/* Main Content */}
      <main className="gs-main">
        <div className="gs-search-area">
          <h1 className="gs-search-heading">Ask a Guideline Question</h1>
          <p className="gs-search-subheading">
            Search across all mortgage underwriting guidelines with AI-powered answers and citations
          </p>
          <div className="gs-search-box">
            <textarea
              ref={textareaRef}
              className="gs-search-textarea"
              placeholder="e.g., What is the minimum credit score for FHA with 3.5% down?"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              rows={3}
              aria-label="Search guidelines"
            />
            <div className="gs-search-actions">
              <button
                className="gs-search-btn"
                onClick={handleSearch}
                disabled={isSearching || !query.trim()}
              >
                {isSearching ? 'Searching...' : 'Search Guidelines'}
              </button>
            </div>
          </div>
        </div>

        {/* Loading */}
        {isSearching && (
          <div className="gs-loading">
            <div className="gs-spinner" />
            <span>Searching guidelines and synthesizing answer...</span>
          </div>
        )}

        {/* Results */}
        {result && !isSearching && (
          <div className="gs-results">
            {/* Tabs */}
            <div className="gs-tabs" role="tablist" aria-label="Search results">
              <button
                className={`gs-tab ${activeTab === 'answer' ? 'active' : ''}`}
                onClick={() => setActiveTab('answer')}
                role="tab"
                aria-selected={activeTab === 'answer'}
              >
                Answer
              </button>
              <button
                className={`gs-tab ${activeTab === 'citations' ? 'active' : ''}`}
                onClick={() => setActiveTab('citations')}
                role="tab"
                aria-selected={activeTab === 'citations'}
              >
                Citations ({result.citations?.length || 0})
              </button>
              <button
                className={`gs-tab ${activeTab === 'sources' ? 'active' : ''}`}
                onClick={() => setActiveTab('sources')}
                role="tab"
                aria-selected={activeTab === 'sources'}
              >
                Sources ({result.sources?.length || 0})
              </button>
              {comparisonData && (
                <button
                  className={`gs-tab ${activeTab === 'comparison' ? 'active' : ''}`}
                  onClick={() => setActiveTab('comparison')}
                  role="tab"
                  aria-selected={activeTab === 'comparison'}
                >
                  Comparison
                </button>
              )}
            </div>

            {!result.answer && (!result.citations || result.citations.length === 0) && (
              <div style={{ textAlign: 'center', padding: 40, color: '#64748b' }}>
                <p style={{ fontSize: 16, marginBottom: 8 }}>No matching guidelines found</p>
                <p style={{ fontSize: 13 }}>Try broadening your search or selecting different sources</p>
              </div>
            )}

            {/* Answer Tab */}
            {activeTab === 'answer' && (
              <div>
                <div
                  className="gs-answer"
                  dangerouslySetInnerHTML={{ __html: formatAnswer(result.answer) }}
                />

                {result.citations?.some((c) => c.is_overlay) && (
                  <div className="gs-overlay-callout">
                    <div className="gs-overlay-callout-label">Company Overlay</div>
                    Your company overlay may differ from agency guidelines on this topic.
                    Check overlay-marked citations for specifics.
                  </div>
                )}

                <div className="gs-answer-actions">
                  <button className="gs-action-btn" onClick={handleCopyAnswer}>
                    Copy
                  </button>
                </div>

                <div className="gs-disclaimer">
                  AI-generated answer based on indexed guideline documents. Always verify against
                  official agency guidelines before making lending decisions. Confidence:{' '}
                  {Math.round((result.confidence || 0) * 100)}%
                </div>
              </div>
            )}

            {/* Citations Tab */}
            {activeTab === 'citations' && (
              <div className="gs-citations-grid">
                {(result.citations || []).map((c, i) => (
                  <div
                    key={i}
                    className={`gs-citation-card ${c.is_overlay ? 'overlay' : ''}`}
                  >
                    <div className="gs-citation-index">{c.index}</div>
                    <div className="gs-citation-doc">{c.guideline_name}</div>
                    <div className="gs-citation-section">
                      Section {c.section_number}
                      {c.page_number ? ` — Page ${c.page_number}` : ''}
                    </div>
                    <div className="gs-citation-snippet">{c.snippet}</div>
                  </div>
                ))}
              </div>
            )}

            {/* Sources Tab */}
            {activeTab === 'sources' && (
              <div className="gs-sources-list">
                {(result.sources || []).map((s, i) => (
                  <div
                    key={i}
                    className="gs-source-card"
                    onClick={() => handleViewComparison(s.loan_program)}
                  >
                    <div>
                      <div className="gs-source-name">{s.name}</div>
                      <div className="gs-source-meta">
                        {s.guideline_type} — {s.loan_program}
                      </div>
                    </div>
                    <div className="gs-source-count">
                      {s.citation_count} citation{s.citation_count !== 1 ? 's' : ''}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Comparison Tab */}
            {activeTab === 'comparison' && comparisonData && (
              <div className="gs-comparison">
                <h2 className="gs-comparison-title">{comparisonData.topic_name}</h2>
                <table className="gs-comparison-table">
                  <thead>
                    <tr>
                      <th>Program</th>
                      <th>Guideline</th>
                      <th>Details</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(comparisonData.programs || []).map((p, i) => (
                      <tr
                        key={i}
                        className={p.overlay_priority < 4 ? 'overlay-row' : ''}
                      >
                        <td style={{ fontWeight: 600 }}>{p.program}</td>
                        <td>{p.guideline_name}</td>
                        <td>
                          {Object.entries(p.data || {}).map(([k, v]) => (
                            <div key={k} style={{ marginBottom: 4 }}>
                              <strong>{k.replace(/_/g, ' ')}:</strong> {v}
                            </div>
                          ))}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}

function formatAnswer(rawAnswer) {
  if (!rawAnswer) return '';
  let html = rawAnswer
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n\n/g, '<br/><br/>')
    .replace(/\n/g, '<br/>');

  html = html.replace(
    /\[(\d+)\]/g,
    '<span class="gs-citation-pill">[$1]</span>'
  );

  return sanitizeHTML(html, {
    allowedTags: ['strong', 'br', 'span', 'table', 'tr', 'td', 'th', 'thead', 'tbody'],
    allowedAttr: ['class'],
  });
}

export default GuidelineSearch;
