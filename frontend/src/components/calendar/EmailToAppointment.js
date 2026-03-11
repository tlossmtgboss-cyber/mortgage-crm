// Parse email data from various drag formats (Outlook, Gmail, .msg/.eml files)
export const parseEmailData = (dataTransfer) => {
  const emailInfo = {
    subject: '',
    from: '',
    fromEmail: '',
    body: '',
    date: new Date()
  };

  // Try to get text/plain data (most common from Outlook drag)
  const textData = dataTransfer.getData('text/plain');
  const htmlData = dataTransfer.getData('text/html');

  if (textData) {
    // Parse text data - could be email content or subject line
    const lines = textData.split('\n').filter(l => l.trim());

    // Try to extract email patterns
    const emailMatch = textData.match(/([a-zA-Z0-9._-]+@[a-zA-Z0-9._-]+\.[a-zA-Z0-9_-]+)/);
    if (emailMatch) {
      emailInfo.fromEmail = emailMatch[1];
    }

    // Try to extract "From:" line
    const fromMatch = textData.match(/From:\s*([^\n<]+)(?:<([^>]+)>)?/i);
    if (fromMatch) {
      emailInfo.from = fromMatch[1].trim();
      if (fromMatch[2]) {
        emailInfo.fromEmail = fromMatch[2].trim();
      }
    }

    // Try to extract "Subject:" line
    const subjectMatch = textData.match(/Subject:\s*([^\n]+)/i);
    if (subjectMatch) {
      emailInfo.subject = subjectMatch[1].trim();
    }

    // If no subject found, use first line as subject
    if (!emailInfo.subject && lines.length > 0) {
      emailInfo.subject = lines[0].substring(0, 100);
    }

    // Use remaining content as body
    emailInfo.body = textData;
  }

  // Try to parse HTML data for more structured info
  if (htmlData) {
    const parser = new DOMParser();
    const doc = parser.parseFromString(htmlData, 'text/html');

    // Try to find email subject in title or headers
    const title = doc.querySelector('title');
    if (title && !emailInfo.subject) {
      emailInfo.subject = title.textContent;
    }

    // Try to find sender info
    const fromElement = doc.querySelector('[class*="from"], [class*="sender"]');
    if (fromElement && !emailInfo.from) {
      emailInfo.from = fromElement.textContent.trim();
    }
  }

  // Try to get Outlook-specific data
  const outlookData = dataTransfer.getData('application/x-moz-file') ||
                     dataTransfer.getData('text/x-moz-url') ||
                     dataTransfer.getData('application/vnd.ms-outlook');

  if (outlookData && !emailInfo.subject) {
    // Outlook data may contain subject or sender info as plain text
    const lines = outlookData.split('\n').filter(l => l.trim());
    if (lines.length > 0) emailInfo.subject = lines[0].substring(0, 100);
  }

  // Check for files (dragged .msg or .eml files)
  if (dataTransfer.files && dataTransfer.files.length > 0) {
    const file = dataTransfer.files[0];

    if (file.name.endsWith('.msg') || file.name.endsWith('.eml')) {
      emailInfo.subject = file.name.replace(/\.(msg|eml)$/i, '');
      emailInfo.fileName = file.name;
      emailInfo.file = file;
    }
  }

  return emailInfo;
};
