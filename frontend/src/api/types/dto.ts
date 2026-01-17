export type MailboxCreate = {
  display_name?: string | null;
};

export type MailboxOut = {
  mailbox_id: string;
  display_name?: string | null;
  created_at?: string | null;
};

export type AccountCreate = {
  provider: string;
  display_label?: string | null;
  config?: Record<string, unknown> | null;
};

export type AccountUpdate = {
  display_label?: string | null;
  config?: Record<string, unknown> | null;
};

export type AccountOut = {
  account_id: string;
  mailbox_id: string;
  provider: string;
  display_label?: string | null;
  config?: Record<string, unknown> | null;
};

export type AccountConnectResponse = {
  connected: boolean;
  provider?: string | null;
  account_id: string;
  account_label?: string | null;
  message?: string | null;
};

export type EmailOut = {
  message_id: string;
  subject?: string | null;
  sender?: string | null;
  recipients?: string[] | null;
  body?: string | null;
  sent_at?: string | null;
  is_unread?: boolean | null;
  provider?: string | null;
  thread_id?: string | null;
  raw_rfc822_b64url?: string | null;
};

export type EmailSendRequest = {
  account_id: string;
  subject: string;
  body: string;
  recipients: string[];
};
