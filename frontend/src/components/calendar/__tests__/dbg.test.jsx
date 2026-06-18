import { describe, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import CommandCenterHeader from '../CommandCenterHeader';
describe('dbg', () => {
  it('roles', () => {
    render(<CommandCenterHeader userName="Tim" alerts={[]} onRefresh={()=>{}} />);
    const out = {
      settings: !!screen.queryByRole('button', { name: /settings/i }),
      refresh: !!screen.queryByRole('button', { name: /refresh/i }),
      timExact: !!screen.queryByText('Tim'),
      timRe: !!screen.queryByText(/Tim/),
      goodMorning: !!screen.queryByText(/Good morning/i),
    };
    console.log('PROBE=' + JSON.stringify(out));
  });
});
