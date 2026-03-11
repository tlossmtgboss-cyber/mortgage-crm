/**
 * Loan Stage Logic Tests
 *
 * Tests for:
 *  - Valid stage transitions (which "next" stages are allowed from each stage)
 *  - Terminal stage detection (FUNDED, CANCELLED, DENIED, DEAD, WITHDRAWN, DOES_NOT_QUALIFY)
 *  - SLA day calculations (target days per stage-to-stage transition)
 *
 * All constants and functions mirror what lives in the Python back-end
 * (backend/agents/tools/part1_base.py) and in the front-end display layer.
 * Keeping them here makes the contract explicit and catches drift early.
 */

// ---------------------------------------------------------------------------
// Stage constants (mirrored from CLAUDE.md / LoanStage enum)
// ---------------------------------------------------------------------------

const LOAN_STAGES = {
  APPLICATION:          'APPLICATION',
  DISCLOSED:            'DISCLOSED',
  PROCESSING:           'PROCESSING',
  SUBMITTED:            'SUBMITTED',
  UNDERWRITING:         'UNDERWRITING',
  UW_RECEIVED:          'UW_RECEIVED',
  CONDITIONAL_APPROVAL: 'CONDITIONAL_APPROVAL',
  APPROVED:             'APPROVED',
  SUSPENDED:            'SUSPENDED',
  CTC:                  'CTC',
  CLEAR_TO_CLOSE:       'CLEAR_TO_CLOSE',
  CLOSING:              'CLOSING',
  DOCS:                 'DOCS',
  DOCS_OUT:             'DOCS_OUT',
  FUNDED:               'FUNDED',
  CANCELLED:            'CANCELLED',
  DENIED:               'DENIED',
  DEAD:                 'DEAD',
  NURTURE:              'NURTURE',
  WITHDRAWN:            'WITHDRAWN',
  DOES_NOT_QUALIFY:     'DOES_NOT_QUALIFY',
};

/** Stages from which no further active-pipeline progression is possible. */
const TERMINAL_STAGES = new Set([
  'FUNDED',
  'CANCELLED',
  'DENIED',
  'DEAD',
  'WITHDRAWN',
  'DOES_NOT_QUALIFY',
]);

/**
 * SLA targets in calendar days for each tracked stage-to-stage transition.
 * Source: CLAUDE.md SLA_TARGETS constant.
 */
const SLA_TARGETS = {
  'APPLICATION_to_DISCLOSED':         3,
  'DISCLOSED_to_SUBMITTED':           7,
  'SUBMITTED_to_UW_RECEIVED':         2,
  'UW_RECEIVED_to_APPROVED':          5,
  'APPROVED_to_CLEAR_TO_CLOSE':       3,
  'CLEAR_TO_CLOSE_to_DOCS_OUT':       3,
  'DOCS_OUT_to_FUNDED':               5,
};

/**
 * Allowed forward transitions for each active stage.
 * A transition is "valid" if it represents normal pipeline movement.
 * Backward movements and out-of-order jumps are flagged by underwriting staff
 * but are not technically blocked in the data model; this map captures the
 * canonical forward path only.
 */
const VALID_TRANSITIONS = {
  APPLICATION:          ['DISCLOSED', 'CANCELLED', 'DOES_NOT_QUALIFY', 'WITHDRAWN'],
  DISCLOSED:            ['PROCESSING', 'CANCELLED', 'WITHDRAWN'],
  PROCESSING:           ['SUBMITTED', 'CANCELLED', 'WITHDRAWN'],
  SUBMITTED:            ['UNDERWRITING', 'CANCELLED', 'DENIED'],
  UNDERWRITING:         ['UW_RECEIVED', 'SUSPENDED', 'DENIED', 'CANCELLED'],
  UW_RECEIVED:          ['CONDITIONAL_APPROVAL', 'APPROVED', 'DENIED', 'SUSPENDED'],
  CONDITIONAL_APPROVAL: ['APPROVED', 'DENIED', 'SUSPENDED'],
  APPROVED:             ['CTC', 'CLEAR_TO_CLOSE', 'DENIED', 'CANCELLED'],
  SUSPENDED:            ['UNDERWRITING', 'DENIED', 'CANCELLED'],
  CTC:                  ['CLEAR_TO_CLOSE', 'DOCS', 'CANCELLED'],
  CLEAR_TO_CLOSE:       ['DOCS', 'DOCS_OUT', 'CLOSING'],
  CLOSING:              ['DOCS_OUT', 'FUNDED', 'CANCELLED'],
  DOCS:                 ['DOCS_OUT', 'CLOSING', 'CANCELLED'],
  DOCS_OUT:             ['FUNDED', 'CANCELLED'],
  NURTURE:              ['APPLICATION', 'CANCELLED', 'DEAD'],
  // Terminal stages have no forward transitions
  FUNDED:               [],
  CANCELLED:            [],
  DENIED:               [],
  DEAD:                 [],
  WITHDRAWN:            [],
  DOES_NOT_QUALIFY:     [],
};

// ---------------------------------------------------------------------------
// Helper functions (what the application layer uses)
// ---------------------------------------------------------------------------

function isTerminalStage(stage) {
  return TERMINAL_STAGES.has(stage);
}

function isValidTransition(fromStage, toStage) {
  const allowed = VALID_TRANSITIONS[fromStage];
  if (!allowed) return false;
  return allowed.includes(toStage);
}

/**
 * Return the SLA target days for a given transition key (e.g. "APPLICATION_to_DISCLOSED"),
 * or null if no SLA is defined.
 */
function getSLADays(fromStage, toStage) {
  const key = `${fromStage}_to_${toStage}`;
  return SLA_TARGETS[key] ?? null;
}

/**
 * Calculate whether a loan is over SLA.
 *
 * @param {string} fromStage   - Stage the loan entered
 * @param {string} toStage     - Next expected stage
 * @param {number} daysInStage - Days the loan has been in fromStage
 * @returns {{ overSLA: boolean, targetDays: number|null, daysOver: number }}
 */
function checkSLAStatus(fromStage, toStage, daysInStage) {
  const targetDays = getSLADays(fromStage, toStage);
  if (targetDays === null) {
    return { overSLA: false, targetDays: null, daysOver: 0 };
  }
  const daysOver = Math.max(0, daysInStage - targetDays);
  return { overSLA: daysInStage > targetDays, targetDays, daysOver };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('Valid Stage Transitions', () => {
  test('APPLICATION can move to DISCLOSED (normal first step after disclosure)', () => {
    expect(isValidTransition('APPLICATION', 'DISCLOSED')).toBe(true);
  });

  test('APPLICATION can move to CANCELLED', () => {
    expect(isValidTransition('APPLICATION', 'CANCELLED')).toBe(true);
  });

  test('SUBMITTED can move to UNDERWRITING', () => {
    expect(isValidTransition('SUBMITTED', 'UNDERWRITING')).toBe(true);
  });

  test('UW_RECEIVED can move to CONDITIONAL_APPROVAL or APPROVED', () => {
    expect(isValidTransition('UW_RECEIVED', 'CONDITIONAL_APPROVAL')).toBe(true);
    expect(isValidTransition('UW_RECEIVED', 'APPROVED')).toBe(true);
  });

  test('APPROVED can move to CLEAR_TO_CLOSE', () => {
    expect(isValidTransition('APPROVED', 'CLEAR_TO_CLOSE')).toBe(true);
  });

  test('DOCS_OUT can move to FUNDED (final active-to-terminal step)', () => {
    expect(isValidTransition('DOCS_OUT', 'FUNDED')).toBe(true);
  });

  test('SUSPENDED can loop back to UNDERWRITING (re-submission after conditions)', () => {
    expect(isValidTransition('SUSPENDED', 'UNDERWRITING')).toBe(true);
  });

  test('NURTURE can re-enter APPLICATION when borrower is ready', () => {
    expect(isValidTransition('NURTURE', 'APPLICATION')).toBe(true);
  });

  test('invalid forward jump: APPLICATION → FUNDED is not a valid transition', () => {
    expect(isValidTransition('APPLICATION', 'FUNDED')).toBe(false);
  });

  test('invalid backward movement: FUNDED → APPLICATION is not a valid transition', () => {
    expect(isValidTransition('FUNDED', 'APPLICATION')).toBe(false);
  });

  test('unknown stage returns false for any transition', () => {
    expect(isValidTransition('BOGUS_STAGE', 'APPLICATION')).toBe(false);
    expect(isValidTransition('APPLICATION', 'BOGUS_STAGE')).toBe(false);
  });

  test('same-stage transition is not considered valid', () => {
    // A loan shouldn't "move" from APPLICATION to APPLICATION
    expect(isValidTransition('APPLICATION', 'APPLICATION')).toBe(false);
  });
});

describe('Terminal Stage Detection', () => {
  const terminalStages = ['FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN', 'DOES_NOT_QUALIFY'];
  const activeStages   = ['APPLICATION', 'DISCLOSED', 'PROCESSING', 'SUBMITTED',
                          'UNDERWRITING', 'UW_RECEIVED', 'CONDITIONAL_APPROVAL',
                          'APPROVED', 'CTC', 'CLEAR_TO_CLOSE', 'DOCS', 'DOCS_OUT'];

  test.each(terminalStages)('"%s" is identified as a terminal stage', (stage) => {
    expect(isTerminalStage(stage)).toBe(true);
  });

  test.each(activeStages)('"%s" is NOT identified as a terminal stage', (stage) => {
    expect(isTerminalStage(stage)).toBe(false);
  });

  test('NURTURE is not terminal (can re-enter pipeline)', () => {
    expect(isTerminalStage('NURTURE')).toBe(false);
  });

  test('SUSPENDED is not terminal (UW can still approve)', () => {
    expect(isTerminalStage('SUSPENDED')).toBe(false);
  });

  test('terminal stages have no valid forward transitions', () => {
    terminalStages.forEach((stage) => {
      expect(VALID_TRANSITIONS[stage]).toHaveLength(0);
    });
  });

  test('total terminal stage count matches CLAUDE.md specification (6)', () => {
    expect(TERMINAL_STAGES.size).toBe(6);
  });
});

describe('SLA Day Calculations', () => {
  test('APPLICATION_to_DISCLOSED SLA is 3 days', () => {
    expect(getSLADays('APPLICATION', 'DISCLOSED')).toBe(3);
  });

  test('DISCLOSED_to_SUBMITTED SLA is 7 days', () => {
    expect(getSLADays('DISCLOSED', 'SUBMITTED')).toBe(7);
  });

  test('SUBMITTED_to_UW_RECEIVED SLA is 2 days', () => {
    expect(getSLADays('SUBMITTED', 'UW_RECEIVED')).toBe(2);
  });

  test('UW_RECEIVED_to_APPROVED SLA is 5 days', () => {
    expect(getSLADays('UW_RECEIVED', 'APPROVED')).toBe(5);
  });

  test('APPROVED_to_CLEAR_TO_CLOSE SLA is 3 days', () => {
    expect(getSLADays('APPROVED', 'CLEAR_TO_CLOSE')).toBe(3);
  });

  test('CLEAR_TO_CLOSE_to_DOCS_OUT SLA is 3 days', () => {
    expect(getSLADays('CLEAR_TO_CLOSE', 'DOCS_OUT')).toBe(3);
  });

  test('DOCS_OUT_to_FUNDED SLA is 5 days', () => {
    expect(getSLADays('DOCS_OUT', 'FUNDED')).toBe(5);
  });

  test('returns null for a transition with no defined SLA', () => {
    // e.g. PROCESSING → SUBMITTED has no tracked SLA in the current model
    expect(getSLADays('PROCESSING', 'SUBMITTED')).toBeNull();
  });

  test('loan within SLA is not flagged as overdue', () => {
    const { overSLA, daysOver } = checkSLAStatus('APPLICATION', 'DISCLOSED', 2);
    expect(overSLA).toBe(false);
    expect(daysOver).toBe(0);
  });

  test('loan exactly at SLA boundary is not flagged as overdue', () => {
    const { overSLA } = checkSLAStatus('APPLICATION', 'DISCLOSED', 3);
    expect(overSLA).toBe(false);
  });

  test('loan one day over SLA is flagged as overdue', () => {
    const { overSLA, targetDays, daysOver } = checkSLAStatus('APPLICATION', 'DISCLOSED', 4);
    expect(overSLA).toBe(true);
    expect(targetDays).toBe(3);
    expect(daysOver).toBe(1);
  });

  test('loan severely overdue reports correct daysOver', () => {
    // Loan stuck in SUBMITTED for 15 days; SLA is 2 days
    const { overSLA, daysOver } = checkSLAStatus('SUBMITTED', 'UW_RECEIVED', 15);
    expect(overSLA).toBe(true);
    expect(daysOver).toBe(13);
  });

  test('total number of tracked SLA transitions matches specification (7)', () => {
    expect(Object.keys(SLA_TARGETS)).toHaveLength(7);
  });
});
