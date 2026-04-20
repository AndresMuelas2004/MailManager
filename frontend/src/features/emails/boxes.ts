import type { EmailBox } from '../../lib/types';
import type { BulkAction } from './types';

export type EmailBoxConfig = {
  title: string;
  subtitle: string;
  allowedBulkActions: BulkAction[];
};

export const EMAIL_BOX_CONFIG: Record<EmailBox, EmailBoxConfig> = {
  ALL_MAIL: {
    title: 'Bandeja unificada',
    subtitle: 'Todos los correos de tus cuentas conectadas en un solo lugar.',
    allowedBulkActions: ['toggle_read', 'move_to_trash', 'mark_spam'],
  },
  SENT: {
    title: 'Correos enviados',
    subtitle: 'Todos los correos enviados desde tus cuentas conectadas.',
    allowedBulkActions: ['toggle_read', 'move_to_trash'],
  },
  SPAM: {
    title: 'Bandeja de spam',
    subtitle: 'Correos no deseados de tus cuentas conectadas.',
    allowedBulkActions: ['toggle_read', 'move_to_trash', 'restore_from_spam'],
  },
  TRASH: {
    title: 'Papelera de reciclaje',
    subtitle: 'Correos eliminados de tus cuentas conectadas.',
    allowedBulkActions: ['toggle_read', 'restore_from_trash', 'delete_permanently'],
  },
};
