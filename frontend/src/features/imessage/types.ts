// Perennia iMessage — frontend types
// Mirrors the backend Pydantic models in app/integrations/imessage/schemas.py

export type Channel = "imessage" | "sms" | "auto";
export type Direction = "inbound" | "outbound";
export type MessageStatus =
  | "queued"
  | "sending"
  | "sent"
  | "delivered"
  | "read"
  | "failed"
  | "received";

export type SendStyle =
  | ""
  | "invisible"
  | "gentle"
  | "loud"
  | "slam"
  | "confetti"
  | "echo"
  | "fireworks"
  | "heart"
  | "lasers"
  | "shooting_star"
  | "sparkles"
  | "spotlight";

export type TapbackType =
  | "love"
  | "like"
  | "dislike"
  | "laugh"
  | "emphasize"
  | "question";

export interface ConversationMessage {
  id: string;
  contact_id: number;
  direction: Direction;
  body: string | null;
  media_urls: string[];
  channel: Channel;
  status: MessageStatus;
  send_style?: SendStyle | null;
  error_code?: number | null;
  error_message?: string | null;
  bb_message_guid?: string | null;
  sender_seat_id?: number | null;
  reply_to_message_id?: string | null;
  associated_message_guid?: string | null;
  tapback?: TapbackType | null;
  created_at: string;
  delivered_at?: string | null;
  read_at?: string | null;
}

export interface ConversationThread {
  contact_id: number;
  contact_phone: string | null;
  contact_email: string | null;
  chat_guid: string | null;
  last_known_channel: Channel | null;
  imessage_supported: boolean | null;
  line_id: string;
  line_handle: string;
  messages: ConversationMessage[];
}

export interface SendMessageRequest {
  contact_id: number;
  body?: string | null;
  media_url?: string | null;
  channel?: Channel;
  send_style?: SendStyle | null;
  reply_to_message_id?: string | null;
  line_id?: string | null;
}

export interface SendMessageResponse {
  message_id: string;
  bb_message_guid: string;
  chat_guid: string;
  channel: Channel;
  status: MessageStatus;
  sent_via_line_id: string;
  created_at: string;
}

export interface IMessageDetectionResult {
  handle: string;
  service: Channel;
  cached: boolean;
  checked_at: string;
}

export interface TapbackRequest {
  target_message_id: string;
  tapback: TapbackType;
  remove?: boolean;
}

// ---- Realtime WebSocket events ---------------------------------------------
export type RealtimeEvent =
  | {
      type: "imessage.message.created";
      thread_id: string;
      message: ConversationMessage;
    }
  | {
      type: "imessage.message.received";
      thread_id: string;
      contact_id: number;
      message: ConversationMessage;
    }
  | {
      type: "imessage.message.updated";
      message_id: string;
      status: MessageStatus;
      delivered_at?: string | null;
      read_at?: string | null;
    }
  | {
      type: "imessage.typing";
      chat_guid: string;
      display: boolean;
    };
