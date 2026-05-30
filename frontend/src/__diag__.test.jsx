import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import CalendarSetupWizard from './components/calendar/CalendarSetupWizard';
global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
describe('diag', () => {
  it('count google', () => {
    render(<CalendarSetupWizard />);
    const all = screen.queryAllByText(/google/i);
    console.log('GOOGLE_COUNT=' + all.length);
    all.forEach(e => console.log('  ['+e.tagName+'] ' + e.textContent));
    const step = screen.queryAllByText(/step|1 of|progress/i);
    console.log('STEP_COUNT=' + step.length);
    step.forEach(e => console.log('  ['+e.tagName+'] ' + e.textContent));
    expect(true).toBe(true);
  });
});
