import React from 'react';

import { SmartCalendar } from '../SmartCalendar';
import type { PanelProps } from './_shared';

export const SchedulePanel: React.FC<PanelProps> = ({ application, onComplete }) => {
  if (!application) return null;

  return (
    <>
      <section className="urla-form-section">
        <h3 className="urla-form-section__title">Talk to your loan officer</h3>
        <p className="urla-form-section__desc">
          Pick a time that works for you. Your loan officer will walk through
          your application, answer questions, and help you finalize everything
          before submission.
        </p>
        <SmartCalendar
          applicationId={application.id}
          onBooked={() => onComplete()}
        />
      </section>
    </>
  );
};
