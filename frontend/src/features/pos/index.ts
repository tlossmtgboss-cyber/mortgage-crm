// Public surface of the POS feature.

export { POSContainer } from './components/POSContainer';
export { HomePage } from './components/HomePage';
export { TopNav } from './components/TopNav';
export { POSSidebar } from './components/POSSidebar';
export type { PosNavKey } from './components/POSSidebar';
export { SmartCalendar } from './components/SmartCalendar';
export { AriaPanel } from './components/AriaPanel';
export { AskAriaButton } from './components/AskAriaButton';

export { usePOSApplication } from './hooks/usePOSApplication';
export { useSmartCalendar } from './hooks/useSmartCalendar';
export { useAriaChat } from './hooks/useAriaChat';

export { posApi, APIError } from './api';

export type {
  ApplicationResponse,
  ApplicationStatus,
  AssignedLOResponse,
  AvailableSlotsResponse,
  BookingRequest,
  BookingResponse,
  Confidence,
  MeetingType,
  SectionKey,
  SectionResponse,
  Source,
  TimeSlot,
} from './types';

export { SECTION_LABELS, SECTION_CAPTIONS, SECTION_ORDER } from './types';
export { validateSection, SECTION_SCHEMAS } from './schemas/urla';
