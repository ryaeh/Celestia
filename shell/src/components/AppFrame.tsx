import type { ReactNode } from "react";

type Props = {
  /** The chats column. Renders its own <aside> and toggle button. */
  sidebar: ReactNode;
  /** The right rail ("under the hood"). Omit and the frame is two columns. */
  rail?: ReactNode;
  /** The conversation, or whichever secondary page is open. */
  children: ReactNode;
};

/**
 * The Console frame: sidebar | main | rail. The sidebar fragment must stay a
 * sibling that comes before the main column — App.css relies on
 * `.sidebar-closed ~ .main-column` and `.sidebar-open ~ .sidebar-toggle`.
 * The rail is hidden under 1100px by App.css, so it must never hold the only
 * way to do something.
 */
export default function AppFrame({ sidebar, rail, children }: Props) {
  return (
    <div className="app-shell">
      {sidebar}
      <div className="main-column">{children}</div>
      {rail ? (
        <aside className="rail" aria-label="Under the hood">
          {rail}
        </aside>
      ) : null}
    </div>
  );
}
