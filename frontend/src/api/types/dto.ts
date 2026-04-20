import { z } from 'zod';

// Generic envelopes — reused across resources for small responses.
export const statusResponseSchema = z.object({
  status: z.string(),
});
export type StatusResponse = z.infer<typeof statusResponseSchema>;

export const messageResponseSchema = z.object({
  message: z.string(),
});
export type MessageResponse = z.infer<typeof messageResponseSchema>;

// Auth
export const userOutSchema = z.object({
  user_id: z.string(),
  email: z.string(),
  name: z.string().nullable(),
  avatar_url: z.string().nullable(),
});
export type UserOut = z.infer<typeof userOutSchema>;

export const authResponseSchema = z.object({
  user: userOutSchema,
  message: z.string(),
});
export type AuthResponse = z.infer<typeof authResponseSchema>;

// Mailboxes
export const mailboxCreateSchema = z.object({
  display_name: z.string(),
});
export type MailboxCreate = z.infer<typeof mailboxCreateSchema>;

export const mailboxOutSchema = z.object({
  mailbox_id: z.string(),
  display_name: z.string().nullable(),
  owner_user_id: z.string(),
  created_at: z.string(),
});
export type MailboxOut = z.infer<typeof mailboxOutSchema>;

export const mailboxListSchema = z.array(mailboxOutSchema);

// Accounts
export const accountCreateSchema = z.object({
  provider: z.string(),
  display_label: z.string(),
  config: z.record(z.string(), z.unknown()).optional(),
});
export type AccountCreate = z.infer<typeof accountCreateSchema>;

export const accountUpdateSchema = z.object({
  display_label: z.string().optional(),
  config: z.record(z.string(), z.unknown()).optional(),
});
export type AccountUpdate = z.infer<typeof accountUpdateSchema>;

export const accountOutSchema = z.object({
  account_id: z.string(),
  mailbox_id: z.string(),
  provider: z.string(),
  display_label: z.string(),
  config: z.record(z.string(), z.unknown()),
  email_address: z.string().nullable(),
});
export type AccountOut = z.infer<typeof accountOutSchema>;

export const accountListSchema = z.array(accountOutSchema);

export const accountConnectResponseSchema = z.object({
  connected: z.boolean(),
  provider: z.string().nullable(),
  account_id: z.string(),
  account_label: z.string().nullable(),
  email_address: z.string().nullable(),
  message: z.string().nullable(),
});
export type AccountConnectResponse = z.infer<typeof accountConnectResponseSchema>;

// Emails
export const emailMetadataOutSchema = z.object({
  provider_message_id: z.string(),
  account_id: z.string(),
  thread_id: z.string().nullable(),
  from_email: z.string(),
  from_name: z.string().nullable(),
  subject: z.string().nullable(),
  received_at: z.string(),
  is_read: z.boolean(),
  box: z.string(),
});
export type EmailMetadataOut = z.infer<typeof emailMetadataOutSchema>;

export const emailMetadataListSchema = z.array(emailMetadataOutSchema);

export const emailContentOutSchema = z.object({
  html_body: z.string().nullable(),
  text_body: z.string().nullable(),
});
export type EmailContentOut = z.infer<typeof emailContentOutSchema>;

export const emailSendRequestSchema = z.object({
  account_id: z.string(),
  subject: z.string(),
  body: z.string(),
  recipients: z.array(z.string()),
});
export type EmailSendRequest = z.infer<typeof emailSendRequestSchema>;

export const emailItemRefSchema = z.object({
  account_id: z.string(),
  provider_message_id: z.string(),
});
export type EmailItemRef = z.infer<typeof emailItemRefSchema>;

export const accountSyncDetailSchema = z.object({
  account_id: z.string(),
  provider: z.string(),
  emails_synced: z.number(),
  sync_cursor: z.string().nullable(),
});
export type AccountSyncDetail = z.infer<typeof accountSyncDetailSchema>;

export const syncResultOutSchema = z.object({
  total_synced: z.number(),
  accounts: z.array(accountSyncDetailSchema),
});
export type SyncResultOut = z.infer<typeof syncResultOutSchema>;

export const moveToTrashResultSchema = z.object({
  affected: z.number(),
});
export type MoveToTrashResult = z.infer<typeof moveToTrashResultSchema>;

export const trashActionResultSchema = z.object({
  affected: z.number(),
});
export type TrashActionResult = z.infer<typeof trashActionResultSchema>;

export const readStatusResponseSchema = z.object({
  updated_count: z.number(),
  accounts: z.array(
    z.object({
      account_id: z.string(),
      updated: z.number(),
    }),
  ),
});
export type ReadStatusResponse = z.infer<typeof readStatusResponseSchema>;

export const spamResponseSchema = z.object({
  moved_count: z.number(),
  accounts: z.array(
    z.object({
      account_id: z.string(),
      moved: z.number(),
    }),
  ),
});
export type SpamResponse = z.infer<typeof spamResponseSchema>;

// Drafts
export const draftCreateSchema = z.object({
  to_recipients: z.array(z.string()).optional(),
  cc_recipients: z.array(z.string()).optional(),
  bcc_recipients: z.array(z.string()).optional(),
  subject: z.string().optional(),
  body_html: z.string().optional(),
});
export type DraftCreate = z.infer<typeof draftCreateSchema>;

export const draftUpdateSchema = z.object({
  to_recipients: z.array(z.string()).optional(),
  cc_recipients: z.array(z.string()).optional(),
  bcc_recipients: z.array(z.string()).optional(),
  subject: z.string().optional(),
  body_html: z.string().optional(),
});
export type DraftUpdate = z.infer<typeof draftUpdateSchema>;

export const draftOutSchema = z.object({
  provider_draft_id: z.string(),
  account_id: z.string(),
  to_recipients: z.array(z.string()),
  cc_recipients: z.array(z.string()),
  bcc_recipients: z.array(z.string()),
  subject: z.string(),
  body_html: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
});
export type DraftOut = z.infer<typeof draftOutSchema>;

export const draftListSchema = z.array(draftOutSchema);

export const draftsAccountSyncDetailSchema = z.object({
  account_id: z.string(),
  provider: z.string(),
  drafts_synced: z.number(),
});
export type DraftsAccountSyncDetail = z.infer<typeof draftsAccountSyncDetailSchema>;

export const draftsSyncResultOutSchema = z.object({
  total_synced: z.number(),
  accounts: z.array(draftsAccountSyncDetailSchema),
});
export type DraftsSyncResultOut = z.infer<typeof draftsSyncResultOutSchema>;

export const draftSendOutSchema = z.object({
  provider_message_id: z.string(),
  provider: z.string(),
  status: z.string(),
});
export type DraftSendOut = z.infer<typeof draftSendOutSchema>;
