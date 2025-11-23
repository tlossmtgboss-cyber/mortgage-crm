type Channel = "web" | "sms" | "phone" | "email" | "internal";

interface FormattingConfig {
  maxLength: number;
  style: "concise" | "detailed" | "conversational";
  includeActions: boolean;
}

const CHANNEL_CONFIG: Record<Channel, FormattingConfig> = {
  sms: {
    maxLength: 160,
    style: "concise",
    includeActions: false
  },
  phone: {
    maxLength: 500,
    style: "conversational",
    includeActions: false
  },
  email: {
    maxLength: 2000,
    style: "detailed",
    includeActions: true
  },
  web: {
    maxLength: 1500,
    style: "detailed",
    includeActions: true
  },
  internal: {
    maxLength: 3000,
    style: "detailed",
    includeActions: true
  }
};

export function formatForChannel(
  answer: string,
  channel: Channel,
  actions?: Array<{ type: string; payload: any }>
): string {
  const config = CHANNEL_CONFIG[channel];
  let formatted = answer;

  // Truncate if too long
  if (formatted.length > config.maxLength) {
    formatted = formatted.slice(0, config.maxLength - 3) + "...";
  }

  // Adjust style
  if (config.style === "concise") {
    // Remove extra whitespace and newlines for SMS
    formatted = formatted.replace(/\n+/g, " ").replace(/\s+/g, " ").trim();
  }

  // Append action summary for channels that support it
  if (config.includeActions && actions && actions.length > 0) {
    const actionSummary = actions
      .map(a => `• ${formatActionType(a.type)}`)
      .join("\n");

    const remaining = config.maxLength - formatted.length - 50;
    if (remaining > 50) {
      formatted += `\n\n**Actions planned:**\n${actionSummary}`;
    }
  }

  return formatted;
}

function formatActionType(type: string): string {
  const labels: Record<string, string> = {
    CREATE_TASK: "Create task",
    ADD_NOTE: "Add note",
    UPDATE_LOAN_STATUS: "Update loan status",
    SCHEDULE_APPOINTMENT: "Schedule appointment",
    SEND_EMAIL_DRAFT: "Draft email",
    SEND_SMS_DRAFT: "Draft SMS"
  };
  return labels[type] || type;
}

export function getChannelConfig(channel: Channel): FormattingConfig {
  return CHANNEL_CONFIG[channel];
}
