import EmailViewer from './EmailViewer';
import type { EmailMetadataOut, AccountOut } from '../../../api/types/dto';

type Props = {
  mailboxId: string;
  openedEmail: EmailMetadataOut | null;
  accounts: AccountOut[];
  onClose: () => void;
  onRead: (email: EmailMetadataOut) => Promise<void>;
};

export default function ViewerMount({ mailboxId, openedEmail, accounts, onClose, onRead }: Props) {
  if (!openedEmail) return null;
  return (
    <EmailViewer
      mailboxId={mailboxId}
      email={openedEmail}
      accounts={accounts}
      onClose={onClose}
      onRead={onRead}
    />
  );
}
