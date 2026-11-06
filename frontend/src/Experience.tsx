import { TechnicalScope } from "./TechnicalDetails";
import { useLayoutEffect, useRef, type ReactNode } from "react";
import { Icon } from "./icons";
export function Help({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <details className="help-note">
      <summary>
        <Icon name="review" />
        {title}
      </summary>
      <div>{children}</div>
    </details>
  );
}
export function Dialog({
  title,
  onClose,
  children,
  wide = false,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  wide?: boolean;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useLayoutEffect(() => {
    const node = dialog.current;
    const previous = document.activeElement;
    node?.showModal();
    return () => {
      node?.close();
      if (previous instanceof HTMLElement && previous.isConnected) {
        const restore =
          previous.closest("details:not([open])")?.querySelector("summary") ??
          previous;
        if (restore instanceof HTMLElement) restore.focus();
      } else document.getElementById("main-content")?.focus();
    };
  }, []);
  return (
    <dialog
      ref={dialog}
      className={"customer-dialog" + (wide ? " dialog-wide" : "")}
      aria-label={title}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
    >
      <div className="dialog-heading">
        <div>
          <p className="eyebrow">INVOICEGUARD</p>
          <h2>{title}</h2>
        </div>
        <button
          type="button"
          className="icon-button"
          aria-label={
            title === "Email details" ? "Close email detail" : "Close dialog"
          }
          onClick={onClose}
        >
          <Icon name="close" />
        </button>
      </div>
      <TechnicalScope>{children}</TechnicalScope>
    </dialog>
  );
}
