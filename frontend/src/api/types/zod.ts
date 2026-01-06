import { z } from "zod";

const userOutSchema = z.object({
  user_id: z.string(),
  display_name: z.string().nullable().optional(),
  created_at: z.string().nullable().optional(),
});

const accountOutSchema = z.object({
  account_id: z.string(),
  user_id: z.string(),
  provider: z.string(),
  display_label: z.string().nullable().optional(),
  config: z.record(z.unknown()).nullable().optional(),
});

const emailOutSchema = z.object({
  message_id: z.string(),
  subject: z.string().nullable().optional(),
  sender: z.string().nullable().optional(),
  recipients: z.array(z.string()).nullable().optional(),
  body: z.string().nullable().optional(),
  sent_at: z.string().nullable().optional(),
  is_unread: z.boolean().nullable().optional(),
  provider: z.string().nullable().optional(),
  thread_id: z.string().nullable().optional(),
  raw_rfc822_b64url: z.string().nullable().optional(),
});

export function parseCreateUserResponse(payload: unknown) {
  return userOutSchema.parse(payload);
}

export function parseListAccountsResponse(payload: unknown) {
  return z.array(accountOutSchema).parse(payload);
}

export function parseUnreadEmailsResponse(payload: unknown) {
  return z.array(emailOutSchema).parse(payload);
}
