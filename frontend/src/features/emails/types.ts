export type BulkAction =
  | 'toggle_read'
  | 'move_to_trash'
  | 'mark_spam'
  | 'restore_from_spam'
  | 'delete_permanently'
  | 'restore_from_trash';

export type ReadToggleTarget = 'mark_read' | 'mark_unread';
