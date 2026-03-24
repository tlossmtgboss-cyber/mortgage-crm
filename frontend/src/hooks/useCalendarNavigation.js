import { useState, useCallback, useMemo } from 'react';

const dayNames = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const monthNames = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'
];

const getStartOfWeek = (date) => {
  const d = new Date(date);
  const day = d.getDay();
  d.setDate(d.getDate() - day);
  d.setHours(0, 0, 0, 0);
  return d;
};

/**
 * useCalendarNavigation -- Manages date navigation, view state, and derived date
 * structures (month data, week dates, header subtitle) for Calendar.js.
 *
 * @returns {Object} Navigation state, handlers, and derived data
 */
export function useCalendarNavigation() {
  const [currentDate, setCurrentDate] = useState(new Date());
  const [view, setView] = useState('month');

  // ── Navigation handlers ──

  const handlePrev = useCallback(() => {
    if (view === 'day') {
      setCurrentDate(prev => new Date(prev.getFullYear(), prev.getMonth(), prev.getDate() - 1));
    } else if (view === 'week') {
      setCurrentDate(prev => new Date(prev.getFullYear(), prev.getMonth(), prev.getDate() - 7));
    } else {
      setCurrentDate(prev => new Date(prev.getFullYear(), prev.getMonth() - 1));
    }
  }, [view]);

  const handleNext = useCallback(() => {
    if (view === 'day') {
      setCurrentDate(prev => new Date(prev.getFullYear(), prev.getMonth(), prev.getDate() + 1));
    } else if (view === 'week') {
      setCurrentDate(prev => new Date(prev.getFullYear(), prev.getMonth(), prev.getDate() + 7));
    } else {
      setCurrentDate(prev => new Date(prev.getFullYear(), prev.getMonth() + 1));
    }
  }, [view]);

  const handleToday = useCallback(() => {
    setCurrentDate(new Date());
  }, []);

  const handleScrollUp = useCallback(() => {
    setCurrentDate(prev => new Date(prev.getFullYear(), prev.getMonth() - 1, 1));
  }, []);

  const handleScrollDown = useCallback(() => {
    setCurrentDate(prev => new Date(prev.getFullYear(), prev.getMonth() + 1, 1));
  }, []);

  const handleDayHeaderClick = useCallback((day) => {
    setCurrentDate(new Date(day));
    setView('day');
  }, []);

  // ── Derived data ──

  const getDaysInMonth = useCallback((date) => {
    const year = date.getFullYear();
    const month = date.getMonth();
    const firstDay = new Date(year, month, 1);
    const lastDay = new Date(year, month + 1, 0);
    return { daysInMonth: lastDay.getDate(), startingDayOfWeek: firstDay.getDay(), year, month };
  }, []);

  const currentMonthData = useMemo(() => getDaysInMonth(currentDate), [currentDate, getDaysInMonth]);
  const nextMonthData = useMemo(() => {
    return getDaysInMonth(new Date(currentDate.getFullYear(), currentDate.getMonth() + 1, 1));
  }, [currentDate, getDaysInMonth]);

  const weekDates = useMemo(() => {
    const weekStart = getStartOfWeek(currentDate);
    return Array.from({ length: 7 }, (_, i) => {
      const d = new Date(weekStart);
      d.setDate(d.getDate() + i);
      return d;
    });
  }, [currentDate]);

  const headerSubtitle = useMemo(() => {
    if (view === 'day') {
      return `${dayNames[currentDate.getDay()]}, ${monthNames[currentDate.getMonth()]} ${currentDate.getDate()}, ${currentDate.getFullYear()}`;
    } else if (view === 'week') {
      const weekStart = getStartOfWeek(currentDate);
      const weekEnd = new Date(weekStart);
      weekEnd.setDate(weekEnd.getDate() + 6);
      const startMonth = monthNames[weekStart.getMonth()].slice(0, 3);
      const endMonth = monthNames[weekEnd.getMonth()].slice(0, 3);
      if (weekStart.getMonth() === weekEnd.getMonth()) {
        return `${startMonth} ${weekStart.getDate()} - ${weekEnd.getDate()}, ${weekEnd.getFullYear()}`;
      }
      return `${startMonth} ${weekStart.getDate()} - ${endMonth} ${weekEnd.getDate()}, ${weekEnd.getFullYear()}`;
    }
    return `${monthNames[currentDate.getMonth()]} ${currentDate.getFullYear()}`;
  }, [view, currentDate]);

  const isDashboardView = useMemo(
    () => ['analytics', 'no-shows', 'outcomes', 'webhooks'].includes(view),
    [view]
  );

  return {
    currentDate,
    setCurrentDate,
    view,
    setView,
    handlePrev,
    handleNext,
    handleToday,
    handleScrollUp,
    handleScrollDown,
    handleDayHeaderClick,
    currentMonthData,
    nextMonthData,
    weekDates,
    headerSubtitle,
    isDashboardView,
  };
}

export default useCalendarNavigation;
