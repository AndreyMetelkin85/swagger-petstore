import { Children, cloneElement, isValidElement, useId, useRef, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode } from 'react';
import { Link, type LinkProps } from 'react-router-dom';
import * as Dialog from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import { statusLabels } from './models';
export function Button({ testId, children, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { testId: string }) { return <button type="button" data-testid={testId} {...props}>{children}</button>; }
export function ActionLink({ testId, ...props }: LinkProps & { testId: string }) { return <Link data-testid={testId} {...props} />; }
export function Modal({ open, close, title, description, children, testId, wide = false }: { open: boolean; close: () => void; title: string; description: string; children: ReactNode; testId: string; wide?: boolean }) {
  const returnFocus = useRef<HTMLElement | null>(null);
  return <Dialog.Root open={open} onOpenChange={(value) => { if (!value) close(); }}><Dialog.Portal><Dialog.Overlay className="overlay" /><Dialog.Content data-testid={testId} className={`modal ${wide ? 'wide' : ''}`} onOpenAutoFocus={() => { returnFocus.current = document.activeElement as HTMLElement; }} onCloseAutoFocus={(event) => { if (returnFocus.current?.isConnected) { event.preventDefault(); returnFocus.current.focus(); } }}><div className="modal-heading"><Dialog.Title>{title}</Dialog.Title><Button testId={`${testId}-close`} className="icon-button" aria-label="Закрыть" onClick={close}><X size={21} /></Button></div><Dialog.Description className="modal-description">{description}</Dialog.Description>{children}</Dialog.Content></Dialog.Portal></Dialog.Root>;
}
export function Field({ label, children, error, hint, required, testId }: { label: string; children: ReactNode; error?: string; hint?: string; required?: boolean; testId: string }) {
  const uniqueId = useId(), hintId = `${uniqueId}-hint`, errorId = `${uniqueId}-error`;
  let inputId = uniqueId;
  const controls = Children.map(children, (child) => {
    if (!isValidElement<InputHTMLAttributes<HTMLInputElement>>(child) || !['input', 'select', 'textarea'].includes(String(child.type))) return child;
    inputId = child.props.id ?? uniqueId;
    return cloneElement(child, { id: inputId, required: required ?? child.props.required, 'aria-invalid': error ? true : undefined, 'aria-describedby': [child.props['aria-describedby'], hint ? hintId : '', error ? errorId : ''].filter(Boolean).join(' ') || undefined });
  });
  return <div className="form-field"><label htmlFor={inputId}>{label}{required && <span aria-hidden="true" className="required-mark"> *</span>}</label>{controls}{hint && <span id={hintId} className="field-hint" data-testid={`${testId}-hint`}>{hint}</span>}{error && <span id={errorId} role="alert" className="field-error" data-testid={`${testId}-error`}>{error}</span>}</div>;
}
export function Status({ value }: { value: string }) { return <span className={`status-pill status-${value.toLowerCase()}`} data-testid="status" data-status={value}>{statusLabels[value] ?? value}</span>; }
export function Loading({ label = 'Загружаем…' }: { label?: string }) { return <div className="loading-state" role="status" data-testid="loading"><span className="spinner" />{label}</div>; }
export function Empty({ title, text, children }: { title: string; text: string; children?: ReactNode }) { return <div className="empty-state" data-testid="empty-state"><h2>{title}</h2><p>{text}</p>{children}</div>; }
