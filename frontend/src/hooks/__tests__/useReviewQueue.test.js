import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';

// ---------------------------------------------------------------------------
// Mocks — vi.hoisted ensures mockApi is defined before the hoisted vi.mock
// ---------------------------------------------------------------------------

const mockApi = vi.hoisted(() => ({
  getQueue: vi.fn(),
  getQueueStats: vi.fn(),
  claimDocument: vi.fn(),
  releaseDocument: vi.fn(),
}));

vi.mock('../../services/docReviewApi', () => ({
  getQueue: mockApi.getQueue,
  getQueueStats: mockApi.getQueueStats,
  claimDocument: mockApi.claimDocument,
  releaseDocument: mockApi.releaseDocument,
}));

import useReviewQueue from '../useReviewQueue';

// ---------------------------------------------------------------------------
// Default mock responses
// ---------------------------------------------------------------------------

const MOCK_ITEMS = [
  { id: 1, doc_type: 'paystubs', priority: 'HIGH' },
  { id: 2, doc_type: 'w2', priority: 'NORMAL' },
];

const MOCK_STATS = {
  total: 10,
  claimed: 3,
  unclaimed: 7,
};

function setDefaultMocks() {
  mockApi.getQueue.mockResolvedValue({ items: MOCK_ITEMS, total: 2 });
  mockApi.getQueueStats.mockResolvedValue(MOCK_STATS);
  mockApi.claimDocument.mockResolvedValue({ id: 1, status: 'claimed' });
  mockApi.releaseDocument.mockResolvedValue({ id: 1, status: 'released' });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useReviewQueue', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setDefaultMocks();
  });

  // =========================================================================
  // Mount / initial load
  // =========================================================================

  describe('initial load', () => {
    it('loads queue items and stats on mount', async () => {
      const { result } = renderHook(() => useReviewQueue());

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.items).toEqual(MOCK_ITEMS);
      expect(result.current.stats).toEqual(MOCK_STATS);
      expect(result.current.total).toBe(2);
      expect(result.current.error).toBeNull();
    });

    it('calls getQueue and getQueueStats in parallel on mount', async () => {
      renderHook(() => useReviewQueue());

      await waitFor(() => {
        expect(mockApi.getQueue).toHaveBeenCalledTimes(1);
      });

      expect(mockApi.getQueueStats).toHaveBeenCalledTimes(1);
    });

    it('starts with default filters { limit: 50, offset: 0 }', () => {
      const { result } = renderHook(() => useReviewQueue());

      expect(result.current.filters).toEqual({ limit: 50, offset: 0 });
    });

    it('passes default filters to getQueue on mount', async () => {
      renderHook(() => useReviewQueue());

      await waitFor(() => {
        expect(mockApi.getQueue).toHaveBeenCalledWith({ limit: 50, offset: 0 });
      });
    });

    it('sets loading=true initially then false after load', async () => {
      const { result } = renderHook(() => useReviewQueue());

      // loading starts true
      expect(result.current.loading).toBe(true);

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });
    });

    it('sets error when getQueue rejects', async () => {
      mockApi.getQueue.mockRejectedValue(new Error('Network error'));

      const { result } = renderHook(() => useReviewQueue());

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.error).toBe('Network error');
      expect(result.current.items).toEqual([]);
    });
  });

  // =========================================================================
  // claim
  // =========================================================================

  describe('claim', () => {
    it('calls claimDocument with documentId and reviewerId', async () => {
      const { result } = renderHook(() => useReviewQueue());

      await waitFor(() => expect(result.current.loading).toBe(false));

      await act(async () => {
        await result.current.claim(42, 'user-123');
      });

      expect(mockApi.claimDocument).toHaveBeenCalledWith(42, 'user-123');
    });

    it('refreshes the queue and stats after claiming', async () => {
      const { result } = renderHook(() => useReviewQueue());

      await waitFor(() => expect(result.current.loading).toBe(false));

      // Reset call counts after initial load
      mockApi.getQueue.mockClear();
      mockApi.getQueueStats.mockClear();

      await act(async () => {
        await result.current.claim(42, 'user-123');
      });

      expect(mockApi.getQueue).toHaveBeenCalledTimes(1);
      expect(mockApi.getQueueStats).toHaveBeenCalledTimes(1);
    });

    it('propagates errors from claimDocument', async () => {
      mockApi.claimDocument.mockRejectedValue(new Error('Already claimed'));

      const { result } = renderHook(() => useReviewQueue());

      await waitFor(() => expect(result.current.loading).toBe(false));

      await act(async () => {
        await expect(result.current.claim(42)).rejects.toThrow('Already claimed');
      });
    });
  });

  // =========================================================================
  // release
  // =========================================================================

  describe('release', () => {
    it('calls releaseDocument with documentId', async () => {
      const { result } = renderHook(() => useReviewQueue());

      await waitFor(() => expect(result.current.loading).toBe(false));

      await act(async () => {
        await result.current.release(7);
      });

      expect(mockApi.releaseDocument).toHaveBeenCalledWith(7);
    });

    it('refreshes the queue and stats after releasing', async () => {
      const { result } = renderHook(() => useReviewQueue());

      await waitFor(() => expect(result.current.loading).toBe(false));

      mockApi.getQueue.mockClear();
      mockApi.getQueueStats.mockClear();

      await act(async () => {
        await result.current.release(7);
      });

      expect(mockApi.getQueue).toHaveBeenCalledTimes(1);
      expect(mockApi.getQueueStats).toHaveBeenCalledTimes(1);
    });
  });

  // =========================================================================
  // setFilters
  // =========================================================================

  describe('setFilters', () => {
    it('merges new filters and resets offset to 0', async () => {
      const { result } = renderHook(() => useReviewQueue());

      await waitFor(() => expect(result.current.loading).toBe(false));

      act(() => {
        result.current.setFilters({ priority: 'HIGH' });
      });

      expect(result.current.filters).toEqual({ limit: 50, offset: 0, priority: 'HIGH' });
    });

    it('triggers a reload with merged filters', async () => {
      const { result } = renderHook(() => useReviewQueue());

      await waitFor(() => expect(result.current.loading).toBe(false));

      mockApi.getQueue.mockClear();

      act(() => {
        result.current.setFilters({ priority: 'HIGH' });
      });

      await waitFor(() => {
        expect(mockApi.getQueue).toHaveBeenCalledWith({
          limit: 50,
          offset: 0,
          priority: 'HIGH',
        });
      });
    });

    it('resets offset to 0 even if current offset is non-zero', async () => {
      const { result } = renderHook(() => useReviewQueue());

      await waitFor(() => expect(result.current.loading).toBe(false));

      // Move to page 2
      act(() => {
        result.current.nextPage();
      });

      await waitFor(() => {
        expect(result.current.filters.offset).toBe(50);
      });

      // setFilters should reset offset
      act(() => {
        result.current.setFilters({ docType: 'w2' });
      });

      expect(result.current.filters.offset).toBe(0);
    });
  });

  // =========================================================================
  // Pagination
  // =========================================================================

  describe('pagination', () => {
    it('nextPage increments offset by limit', async () => {
      const { result } = renderHook(() => useReviewQueue());

      await waitFor(() => expect(result.current.loading).toBe(false));

      act(() => {
        result.current.nextPage();
      });

      expect(result.current.filters.offset).toBe(50);
    });

    it('prevPage decrements offset by limit', async () => {
      const { result } = renderHook(() => useReviewQueue());

      await waitFor(() => expect(result.current.loading).toBe(false));

      // First go to page 2
      act(() => {
        result.current.nextPage();
      });

      await waitFor(() => expect(result.current.filters.offset).toBe(50));

      // Then go back
      act(() => {
        result.current.prevPage();
      });

      expect(result.current.filters.offset).toBe(0);
    });

    it('prevPage does not go below offset 0', async () => {
      const { result } = renderHook(() => useReviewQueue());

      await waitFor(() => expect(result.current.loading).toBe(false));

      act(() => {
        result.current.prevPage();
      });

      expect(result.current.filters.offset).toBe(0);
    });

    it('nextPage triggers a reload with updated offset', async () => {
      const { result } = renderHook(() => useReviewQueue());

      await waitFor(() => expect(result.current.loading).toBe(false));

      mockApi.getQueue.mockClear();

      act(() => {
        result.current.nextPage();
      });

      await waitFor(() => {
        expect(mockApi.getQueue).toHaveBeenCalledWith({ limit: 50, offset: 50 });
      });
    });
  });

  // =========================================================================
  // refresh
  // =========================================================================

  describe('refresh', () => {
    it('reloads queue and stats', async () => {
      const { result } = renderHook(() => useReviewQueue());

      await waitFor(() => expect(result.current.loading).toBe(false));

      mockApi.getQueue.mockClear();
      mockApi.getQueueStats.mockClear();

      await act(async () => {
        await result.current.refresh();
      });

      expect(mockApi.getQueue).toHaveBeenCalledTimes(1);
      expect(mockApi.getQueueStats).toHaveBeenCalledTimes(1);
    });
  });
});
