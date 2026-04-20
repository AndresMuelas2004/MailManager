import { Check, Minus } from 'lucide-react';

export type CheckboxState = 'checked' | 'indeterminate' | 'unchecked';

type Props = {
  state: CheckboxState;
  onClick: () => void;
  ariaLabel: string;
};

export default function Checkbox({ state, onClick, ariaLabel }: Props) {
  const base =
    'flex h-[18px] w-[18px] items-center justify-center rounded border-[1.5px] transition-colors';
  const style =
    state === 'unchecked'
      ? 'border-zinc-300 bg-white hover:border-zinc-400'
      : 'border-blue-600 bg-blue-600 text-white';
  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
      aria-label={ariaLabel}
      aria-checked={state === 'indeterminate' ? 'mixed' : state === 'checked'}
      role="checkbox"
      className={`${base} ${style}`}
    >
      {state === 'checked' && <Check className="h-3 w-3" strokeWidth={3} />}
      {state === 'indeterminate' && <Minus className="h-3 w-3" strokeWidth={3} />}
    </button>
  );
}
