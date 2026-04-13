// Auth
export type UserOut = {
  user_id: string;
  email: string;
  name: string | null;
  avatar_url: string | null;
};

export type AuthResponse = {
  user: UserOut;
  message: string;
};

// Mailboxes
export type MailboxCreate = {
  display_name: string;
};

export type MailboxOut = {
  mailbox_id: string;
  display_name: string | null;
  owner_user_id: string;
  created_at: string;
};

// Accounts
export type AccountCreate = {
  provider: string;
  display_label: string;
  config?: Record<string, unknown>;
};

export type AccountUpdate = {
  display_label?: string;
  config?: Record<string, unknown>;
};

export type AccountOut = {
  account_id: string;
  mailbox_id: string;
  provider: string;
  display_label: string;
  config: Record<string, unknown>;
  email_address: string | null;
};

export type AccountConnectResponse = {
  connected: boolean;
  provider: string | null;
  account_id: string;
  account_label: string | null;
  email_address: string | null;
  message: string | null;
};

// Emails
export type EmailMetadataOut = {
  provider_message_id: string;
  account_id: string;
  thread_id: string | null;
  from_email: string;
  from_name: string | null;
  subject: string | null;
  received_at: string;
  is_read: boolean;
  box: string;
};

export type EmailContentOut = {
  html_body: string | null;
  text_body: string | null;
};

export type EmailSendRequest = {
  account_id: string;
  subject: string;
  body: string;
  recipients: string[];
};

export type EmailItemRef = {
  account_id: string;
  provider_message_id: string;
};

export type AccountSyncDetail = {
  account_id: string;
  provider: string;
  emails_synced: number;
  sync_cursor: string | null;
};

export type SyncResultOut = {
  total_synced: number;
  accounts: AccountSyncDetail[];
};

export type MoveToTrashResult = {
  affected: number;
};

export type TrashActionResult = {
  affected: number;
};

export type ReadStatusResponse = {
  updated_count: number;
  accounts: { account_id: string; updated: number }[];
};

export type SpamResponse = {
  moved_count: number;
  accounts: { account_id: string; moved: number }[];
};

// Drafts
export type DraftCreate = {
  to_recipients?: string[];
  cc_recipients?: string[];
  bcc_recipients?: string[];
  subject?: string;
  body_html?: string;
};

export type DraftUpdate = {
  to_recipients?: string[];
  cc_recipients?: string[];
  bcc_recipients?: string[];
  subject?: string;
  body_html?: string;
};

export type DraftOut = {
  provider_draft_id: string;
  account_id: string;
  to_recipients: string[];
  cc_recipients: string[];
  bcc_recipients: string[];
  subject: string;
  body_html: string;
  created_at: string;
  updated_at: string;
};

export type DraftsAccountSyncDetail = {
  account_id: string;
  provider: string;
  drafts_synced: number;
};

export type DraftsSyncResultOut = {
  total_synced: number;
  accounts: DraftsAccountSyncDetail[];
};

export type DraftSendOut = {
  provider_message_id: string;
  provider: string;
  status: string;
};
