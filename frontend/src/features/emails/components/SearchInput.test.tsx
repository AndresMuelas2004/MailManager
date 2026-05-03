import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import SearchInput from './SearchInput';

describe('SearchInput', () => {
  it('renders an input that reflects the controlled value', () => {
    render(<SearchInput value="hola" onChange={() => {}} />);
    const input = screen.getByRole('searchbox');
    expect(input).toHaveValue('hola');
  });

  it('uses the default placeholder when none is provided', () => {
    render(<SearchInput value="" onChange={() => {}} />);
    expect(screen.getByPlaceholderText('Buscar correos')).toBeInTheDocument();
  });

  it('forwards a custom placeholder', () => {
    render(<SearchInput value="" onChange={() => {}} placeholder="Buscar..." />);
    expect(screen.getByPlaceholderText('Buscar...')).toBeInTheDocument();
  });

  it('does not render the clear button when value is empty', () => {
    render(<SearchInput value="" onChange={() => {}} />);
    expect(screen.queryByRole('button', { name: 'Limpiar búsqueda' })).not.toBeInTheDocument();
  });

  it('renders the clear button when value is non-empty', () => {
    render(<SearchInput value="x" onChange={() => {}} />);
    expect(screen.getByRole('button', { name: 'Limpiar búsqueda' })).toBeInTheDocument();
  });

  it('emits onChange("") when the clear button is clicked', async () => {
    const onChange = vi.fn();
    render(<SearchInput value="abc" onChange={onChange} />);
    await userEvent.click(screen.getByRole('button', { name: 'Limpiar búsqueda' }));
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith('');
  });

  it('emits onChange with the new value as the user types', async () => {
    const onChange = vi.fn();
    // Controlled component fed with empty value — userEvent.type fires one
    // change event per keystroke. We assert on the LAST event payload because
    // the parent does not flow updates back into `value`.
    render(<SearchInput value="" onChange={onChange} />);
    await userEvent.type(screen.getByRole('searchbox'), 'ab');
    expect(onChange).toHaveBeenCalledTimes(2);
    expect(onChange).toHaveBeenNthCalledWith(1, 'a');
    expect(onChange).toHaveBeenNthCalledWith(2, 'b');
  });
});
