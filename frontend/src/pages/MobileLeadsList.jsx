/**
 * MobileLeadsList
 *
 * Full-page mobile view of the lead pipeline. Features:
 * - Sticky search bar
 * - Filter chips (All, Hot, Warm, Cool, New, Contacted)
 * - Infinite scroll with pagination
 * - Pull-to-refresh
 * - FAB for quick-add
 * - Loading skeletons and empty state
 */
import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { leadsAPI } from '../services/api';
import MobileLeadCard, { MobileLeadCardSkeleton } from '../components/mobile/MobileLeadCard';
import { useVirtualList } from '../hooks/useVirtualList';
import { toast } from '../utils/toast';
import './MobileLeadsList.css';

// ── Constants ────────────────────────────────────────────────────────────────

const PAGE_SIZE = 25;

const FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'hot', label: 'Hot', className: 'hot' },
  { key: 'warm', label: 'Warm', className: 'warm' },
  { key: 'cool', label: 'Cool', className: 'cool' },
  { key: 'new', label: 'New' },
  { key: 'contacted', label: 'Contacted' },
];

function scoreGrade(aiScore) {
  if (aiScore == null) return null;
  const s = Number(aiScore);
  if (s >= 80) return 'A';
  if (s >= 60) return 'B';
  if (s >= 40) return 'C';
  return 'D';
}

// ── Component ────────────────────────────────────────────────────────────────

export default function MobileLeadsList() {
  const navigate = useNavigate();

  // Data state
  const [allLeads, setAllLeads] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  // Filter / search state
  const [activeFilter, setActiveFilter] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');

  // Infinite scroll state
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const [loadingMore, setLoadingMore] = useState(false);
  const listRef = useRef(null);
  const observerRef = useRef(null);
  const sentinelRef = useRef(null);

  // Pull-to-refresh state
  const ptrStartY = useRef(0);
  const [ptrVisible, setPtrVisible] = useState(false);

  // ── Fetch leads from API ──
  const fetchLeads = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    setError(null);
    try {
      const data = await leadsAPI.getAll();
      const leads = Array.isArray(data) ? data : (data?.leads || data?.data || []);
      setAllLeads(leads);
    } catch (err) {
      const msg = err?.message || 'Failed to load leads';
      setError(msg);
      if (!silent) toast.error(msg);
    } finally {
      setLoading(false);
      setRefreshing(false);
      setPtrVisible(false);
    }
  }, []);

  useEffect(() => {
    fetchLeads();
  }, [fetchLeads]);

  // ── Debounce search ──
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(searchQuery), 250);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  // Reset visible count when filter/search changes
  useEffect(() => {
    setVisibleCount(PAGE_SIZE);
  }, [activeFilter, debouncedSearch]);

  // ── Derived: filtered leads ──
  const filteredLeads = useMemo(() => {
    let result = allLeads;

    // Apply score/stage filter
    switch (activeFilter) {
      case 'hot':
        result = result.filter((l) => scoreGrade(l.ai_score) === 'A');
        break;
      case 'warm':
        result = result.filter((l) => scoreGrade(l.ai_score) === 'B');
        break;
      case 'cool':
        result = result.filter((l) => scoreGrade(l.ai_score) === 'C' || scoreGrade(l.ai_score) === 'D');
        break;
      case 'new':
        result = result.filter((l) => (l.stage || '').toLowerCase() === 'new');
        break;
      case 'contacted':
        result = result.filter((l) => {
          const stage = (l.stage || '').toLowerCase();
          return stage === 'attempted contact' || stage === 'contacted' || stage === 'prospect';
        });
        break;
      default:
        break;
    }

    // Apply search
    if (debouncedSearch.trim()) {
      const q = debouncedSearch.toLowerCase();
      result = result.filter((l) => {
        const name = `${l.first_name || ''} ${l.last_name || ''}`.toLowerCase();
        const email = (l.email || '').toLowerCase();
        const phone = (l.phone || '').replace(/\D/g, '');
        return name.includes(q) || email.includes(q) || phone.includes(q);
      });
    }

    return result;
  }, [allLeads, activeFilter, debouncedSearch]);

  // Slice for infinite scroll (used only when list is small enough to skip virtualization)
  const visibleLeads = useMemo(
    () => filteredLeads.slice(0, visibleCount),
    [filteredLeads, visibleCount]
  );

  const hasMore = visibleCount < filteredLeads.length;

  // Virtual list for large datasets — renders only visible cards + overscan buffer.
  // itemHeight ~160px accounts for card padding, header, contact, meta, actions, and margin.
  const {
    listRef: virtualListRef,
    visibleItems: virtualItems,
    startIndex: _virtualStartIndex,
    totalHeight: virtualTotalHeight,
    offsetY: virtualOffsetY,
    isVirtualized,
  } = useVirtualList({
    items: filteredLeads,
    itemHeight: 160,
    overscan: 5,
    useWindowScroll: true,
    enabled: true,
  });

  // ── Filter counts ──
  const filterCounts = useMemo(() => {
    const counts = { all: allLeads.length, hot: 0, warm: 0, cool: 0, new: 0, contacted: 0 };
    allLeads.forEach((l) => {
      const grade = scoreGrade(l.ai_score);
      if (grade === 'A') counts.hot++;
      if (grade === 'B') counts.warm++;
      if (grade === 'C' || grade === 'D') counts.cool++;
      const stage = (l.stage || '').toLowerCase();
      if (stage === 'new') counts.new++;
      if (stage === 'attempted contact' || stage === 'contacted' || stage === 'prospect') counts.contacted++;
    });
    return counts;
  }, [allLeads]);

  // ── Infinite scroll via IntersectionObserver ──
  useEffect(() => {
    if (observerRef.current) observerRef.current.disconnect();

    observerRef.current = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasMore && !loadingMore) {
          setLoadingMore(true);
          // Simulate brief delay for smooth UX
          setTimeout(() => {
            setVisibleCount((prev) => prev + PAGE_SIZE);
            setLoadingMore(false);
          }, 200);
        }
      },
      { rootMargin: '200px' }
    );

    if (sentinelRef.current) {
      observerRef.current.observe(sentinelRef.current);
    }

    return () => {
      if (observerRef.current) observerRef.current.disconnect();
    };
  }, [hasMore, loadingMore]);

  // ── Pull to refresh ──
  const handleTouchStart = useCallback((e) => {
    if (window.scrollY === 0) {
      ptrStartY.current = e.touches[0].clientY;
    } else {
      ptrStartY.current = 0;
    }
  }, []);

  const handleTouchMove = useCallback((e) => {
    if (ptrStartY.current === 0) return;
    const dy = e.touches[0].clientY - ptrStartY.current;
    if (dy > 60 && window.scrollY === 0) {
      setPtrVisible(true);
    }
  }, []);

  const handleTouchEnd = useCallback(() => {
    if (ptrVisible && !refreshing) {
      setRefreshing(true);
      fetchLeads(true);
    }
    ptrStartY.current = 0;
  }, [ptrVisible, refreshing, fetchLeads]);

  // ── Actions ──
  const handleCardClick = useCallback((lead) => {
    navigate(`/leads/${lead.id || lead.lead_id}`);
  }, [navigate]);

  const handleCall = useCallback((lead) => {
    if (lead.phone) {
      window.location.href = `tel:${lead.phone.replace(/\D/g, '')}`;
    } else {
      toast.info('No phone number on file');
    }
  }, []);

  const handleText = useCallback((lead) => {
    if (lead.phone) {
      window.location.href = `sms:${lead.phone.replace(/\D/g, '')}`;
    } else {
      toast.info('No phone number on file');
    }
  }, []);

  const handleEmail = useCallback((lead) => {
    if (lead.email) {
      window.location.href = `mailto:${lead.email}`;
    } else {
      toast.info('No email on file');
    }
  }, []);

  const handleNote = useCallback((lead) => {
    // Navigate to lead detail with note focus
    navigate(`/leads/${lead.id || lead.lead_id}?action=note`);
  }, [navigate]);

  const handleArchive = useCallback(async (lead) => {
    try {
      await leadsAPI.update(lead.id || lead.lead_id, { stage: 'Do Not Call' });
      setAllLeads((prev) => prev.filter((l) => (l.id || l.lead_id) !== (lead.id || lead.lead_id)));
      toast.success(`${lead.first_name || 'Lead'} archived`);
    } catch (err) {
      toast.error('Failed to archive lead');
    }
  }, []);

  const handleSchedule = useCallback((lead) => {
    navigate(`/aria/calendar?action=new&lead_id=${lead.id || lead.lead_id}&name=${encodeURIComponent(`${lead.first_name || ''} ${lead.last_name || ''}`.trim())}`);
  }, [navigate]);

  const handleAskAria = useCallback((lead) => {
    const id = lead.id || lead.lead_id;
    const name = encodeURIComponent((lead.first_name || '').trim());
    navigate(`/mobile-aria?leadId=${id}&leadName=${name}&context=lead`);
  }, [navigate]);

  const handleAddLead = useCallback(() => {
    navigate('/leads?action=add');
  }, [navigate]);

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div
      className="mll"
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
    >
      {/* Sticky header */}
      <div className="mll__header">
        <div className="mll__title-row">
          <h1 className="mll__title">Leads</h1>
          <span className="mll__count">{filteredLeads.length} total</span>
        </div>

        {/* Search bar */}
        <div className="mll__search">
          <svg className="mll__search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            className="mll__search-input"
            type="search"
            placeholder="Search name, email, or phone..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            autoComplete="off"
            autoCorrect="off"
            spellCheck="false"
          />
          {searchQuery && (
            <button
              className="mll__search-clear"
              onClick={() => setSearchQuery('')}
              aria-label="Clear search"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          )}
        </div>

        {/* Filter chips */}
        <div className="mll__filters" role="tablist">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              role="tab"
              aria-selected={activeFilter === f.key}
              className={`mll__chip${activeFilter === f.key ? ' mll__chip--active' : ''}${f.className ? ` mll__chip--${f.className}` : ''}`}
              onClick={() => setActiveFilter(f.key)}
            >
              {f.label}
              <span className="mll__chip-count">{filterCounts[f.key] || 0}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Pull to refresh indicator */}
      <div className={`mll__ptr${ptrVisible ? ' mll__ptr--visible' : ''}`}>
        <div className="mll__ptr-spinner" />
        {refreshing ? 'Refreshing...' : 'Release to refresh'}
      </div>

      {/* Content */}
      {loading && !refreshing ? (
        <div className="mll__list">
          {Array.from({ length: 6 }).map((_, i) => (
            <MobileLeadCardSkeleton key={i} />
          ))}
        </div>
      ) : error ? (
        <div className="mll__error">
          <p className="mll__error-text">{error}</p>
          <button className="mll__retry-btn" onClick={() => fetchLeads()}>
            Try Again
          </button>
        </div>
      ) : filteredLeads.length === 0 ? (
        <div className="mll__empty">
          <svg className="mll__empty-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
            <circle cx="9" cy="7" r="4" />
            <line x1="17" y1="8" x2="23" y2="8" />
          </svg>
          <p className="mll__empty-title">
            {debouncedSearch ? 'No matches found' : 'No leads yet'}
          </p>
          <p className="mll__empty-subtitle">
            {debouncedSearch
              ? `No leads matching "${debouncedSearch}". Try a different search.`
              : 'Tap the + button to add your first lead.'}
          </p>
        </div>
      ) : isVirtualized ? (
        /* Virtualized rendering for large lists (>50 items) */
        <div className="mll__list" ref={virtualListRef}>
          <div style={{ height: virtualTotalHeight, position: 'relative' }}>
            <div style={{ transform: `translateY(${virtualOffsetY}px)` }}>
              {virtualItems.map((lead) => (
                <MobileLeadCard
                  key={lead.id || lead.lead_id}
                  lead={lead}
                  onClick={handleCardClick}
                  onCall={handleCall}
                  onText={handleText}
                  onEmail={handleEmail}
                  onNote={handleNote}
                  onArchive={handleArchive}
                  onSchedule={handleSchedule}
                  onAskAria={handleAskAria}
                />
              ))}
            </div>
          </div>
        </div>
      ) : (
        /* Standard rendering with infinite scroll for small lists */
        <div className="mll__list" ref={listRef}>
          {visibleLeads.map((lead) => (
            <MobileLeadCard
              key={lead.id || lead.lead_id}
              lead={lead}
              onClick={handleCardClick}
              onCall={handleCall}
              onText={handleText}
              onEmail={handleEmail}
              onNote={handleNote}
              onArchive={handleArchive}
              onSchedule={handleSchedule}
              onAskAria={handleAskAria}
            />
          ))}

          {/* Infinite scroll sentinel */}
          <div ref={sentinelRef} style={{ height: 1 }} />

          {loadingMore && (
            <div className="mll__load-more">
              <div className="mll__ptr-spinner" />
              Loading more...
            </div>
          )}
        </div>
      )}

      {/* FAB: Quick Add Lead */}
      <button
        className="mll__fab"
        onClick={handleAddLead}
        aria-label="Add new lead"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
          <line x1="12" y1="5" x2="12" y2="19" />
          <line x1="5" y1="12" x2="19" y2="12" />
        </svg>
      </button>
    </div>
  );
}
