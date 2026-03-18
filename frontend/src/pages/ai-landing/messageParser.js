/**
 * Parse AI response text to extract actionable items for the sidebar.
 * userQuestion is used to determine the context/type of the sidebar content.
 */
export function parseResponseForActionItems(responseText, userQuestion = '') {
  const items = [];
  let itemId = 1;
  const questionLower = userQuestion.toLowerCase();

  // Determine the analysis type based on the question
  const isBottleneckQuestion = questionLower.includes('bottleneck') || questionLower.includes('stuck') || questionLower.includes('stall');
  const isPipelineQuestion = questionLower.includes('pipeline') || questionLower.includes('deal') || questionLower.includes('loan');
  const isClosingQuestion = questionLower.includes('closing') || questionLower.includes('close') || questionLower.includes('clear to close');

  // Extract tasks with due dates: "Task name" (Due: MM/DD/YYYY) or *"Task name"* (Due: ...)
  const taskPattern = /[*-\u2022]\s*["\u201C]([^"\u201D]+)["\u201D][*]?\s*\(Due:\s*([^)]+)\)/gi;
  let taskMatch;
  while ((taskMatch = taskPattern.exec(responseText)) !== null) {
    items.push({
      id: itemId++,
      title: taskMatch[1].trim(),
      client: '',
      stage: 'Task',
      priority: taskMatch[2].includes('overdue') || new Date(taskMatch[2]) < new Date() ? 'URGENT' : 'HIGH',
      type: 'Outstanding Task',
      source: 'AI Analysis',
      owner: 'Loan Officer',
      dateCreated: new Date().toLocaleString(),
      details: `Due: ${taskMatch[2]}`,
      dueTime: taskMatch[2],
      loanAmount: null
    });
  }

  // Extract borrowers with dollar amounts in various formats
  const borrowerPatterns = [
    /\*\*([^*]+)\*\*\s*\(\$?([\d,]+)\)/g,
    /\*\*([^*]+)\*\*\s*[-\u2013]\s*\$([\d,]+)/g,
    /[-\u2022]\s*\*\*([^*]+)\*\*\s*\(\$?([\d,]+)\)/g,
    /([A-Z][a-z]+\s+[A-Z][a-z]+)\s*\(\$?([\d,]+)\)/g,
    /([A-Z][a-z]+\s+[A-Z][a-z]+)\s*[-\u2013]\s*\$([\d,]+)/g,
  ];

  const seenBorrowers = new Set();
  const personNamePattern = /^[A-Z][a-z]+\s+(?:[A-Z]\.?\s+)?[A-Z][a-z]+$/;

  for (const borrowerPattern of borrowerPatterns) {
    let borrowerMatch;
    while ((borrowerMatch = borrowerPattern.exec(responseText)) !== null) {
      const name = borrowerMatch[1].trim();
      const amount = borrowerMatch[2].replace(/,/g, '');

      if (!personNamePattern.test(name)) {
        continue;
      }

      const lowerName = name.toLowerCase();
      if (seenBorrowers.has(name) ||
          lowerName.includes('stage') ||
          lowerName.includes('review') ||
          lowerName.includes('completeness') ||
          lowerName.includes('communicate') ||
          lowerName.includes('prioritize') ||
          lowerName.includes('follow') ||
          lowerName.includes('regular') ||
          lowerName.includes('underwriting') ||
          lowerName.includes('received') ||
          lowerName.includes('actionable') ||
          lowerName === 'action' ||
          name.length < 5 ||
          name.length > 30) {
        continue;
      }
      seenBorrowers.add(name);

      const contextStart = Math.max(0, borrowerMatch.index - 200);
      const context = responseText.substring(contextStart, borrowerMatch.index).toLowerCase();

      let stage = 'Active Loan';
      let priority = 'MEDIUM';
      if (context.includes('clear to close') || context.includes('closing')) {
        stage = 'Clear to Close';
        priority = 'URGENT';
      } else if (context.includes('underwriting')) {
        stage = 'Underwriting';
        priority = 'HIGH';
      } else if (context.includes('processing')) {
        stage = 'Processing';
        priority = 'MEDIUM';
      }

      let title = `Follow up - ${stage}`;
      let type = 'Pipeline Item';
      let details = `Review loan status and take necessary action`;

      if (isBottleneckQuestion) {
        title = `${stage} Bottleneck`;
        type = 'Bottleneck';
        details = `Loan stuck in ${stage.toLowerCase()} - needs attention`;
      } else if (isClosingQuestion) {
        title = `${stage} - Ready to Close`;
        type = 'Closing';
        details = `Review closing requirements and schedule`;
      } else if (isPipelineQuestion) {
        title = `${stage} Review`;
        type = 'Pipeline Review';
        details = `Check loan progress in ${stage.toLowerCase()}`;
      }

      items.push({
        id: itemId++,
        title: title,
        client: name,
        stage: stage,
        priority: priority,
        type: type,
        source: 'AI Analysis',
        owner: 'Loan Officer',
        dateCreated: new Date().toLocaleString(),
        details: details,
        dueTime: priority === 'URGENT' ? 'Today' : 'This Week',
        loanAmount: `$${parseInt(amount).toLocaleString()}`
      });
    }
  }

  // Extract leads mentioned
  const leadPattern = /(?:for|with|contact|follow[- ]?up)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)/gi;
  let leadMatch;
  const seenLeads = new Set();
  while ((leadMatch = leadPattern.exec(responseText)) !== null) {
    const name = leadMatch[1].trim();
    if (seenLeads.has(name) || seenBorrowers.has(name) || name.length < 4) continue;
    seenLeads.add(name);

    if (/^[A-Z][a-z]+\s+[A-Z][a-z]+$/.test(name)) {
      items.push({
        id: itemId++,
        title: `Contact ${name}`,
        client: name,
        stage: 'Lead',
        priority: 'MEDIUM',
        type: 'Lead Follow-up',
        source: 'AI Analysis',
        owner: 'Loan Officer',
        dateCreated: new Date().toLocaleString(),
        details: 'Follow up with lead',
        dueTime: 'This Week',
        loanAmount: null
      });
    }
  }

  return items;
}

/**
 * Check if a user message is an explicit task question (triggers task sidebar).
 */
export function isExplicitTaskQuestion(msgLower) {
  return (
    (msgLower.includes('task') && msgLower.includes('what')) ||
    (msgLower.includes('task') && msgLower.includes('need')) ||
    (msgLower.includes('what') && msgLower.includes('need') && msgLower.includes('do') &&
      !msgLower.includes('briefing') && !msgLower.includes('pipeline') && !msgLower.includes('audit')) ||
    msgLower.includes('outstanding task') ||
    msgLower.includes('overdue task') ||
    (msgLower.includes('to-do') && (msgLower.includes('list') || msgLower.includes('what'))) ||
    (msgLower.includes('todo') && (msgLower.includes('list') || msgLower.includes('what')))
  );
}

/**
 * Check if a user message should show the action sidebar.
 */
export function shouldShowActionSidebar(msgLower) {
  return (
    msgLower.includes('task') ||
    msgLower.includes('to-do') ||
    msgLower.includes('todo') ||
    msgLower.includes('reconcil') ||
    (msgLower.includes('call') && (msgLower.includes('need') || msgLower.includes('make') || msgLower.includes('who') || msgLower.includes('today'))) ||
    msgLower.includes('phone') ||
    msgLower.includes('appointment') ||
    msgLower.includes('schedule') ||
    msgLower.includes('calendar') ||
    msgLower.includes('meeting')
  );
}
