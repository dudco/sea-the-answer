'use client';

import React, {
  createContext,
  useContext,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  useSyncExternalStore,
} from 'react';
import { createPortal } from 'react-dom';
import { usePathname, useRouter } from 'next/navigation';
import { createWorkspace } from './controller';
import { Button } from '../components/common';
const Context = createContext(null);
export function useWorkspace() {
  const value = useContext(Context);
  if (!value) throw Error('WorkspaceProvider가 필요합니다.');
  return value;
}
function Modal({ workspace }) {
  const modal = workspace.modal,
    ref = useRef(null),
    [slot, setSlot] = useState(null);
  useLayoutEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (modal && !d.open) d.showModal();
    if (!modal && d.open) {
      d.close();
      workspace.restoreFocus();
    }
    setSlot(d.querySelector('[data-csv-slot]'));
  }, [modal, workspace]);
  return (
    <dialog
      ref={ref}
      id="dialog"
      aria-labelledby="dialog-title"
      className={modal?.drawer ? 'drawer-dialog' : ''}
      onCancel={(e) => {
        e.preventDefault();
        workspace.closeModal();
      }}
    >
      {modal && (
        <React.Fragment key={modal.id}>
          <div className="modal-head">
            <h2 id="dialog-title">{modal.title}</h2>
            <Button action="closeModal" className="ghost sm">
              닫기
            </Button>
          </div>
          <div className="modal-body">{modal.body}</div>
          {modal.footer && <div className="modal-footer">{modal.footer}</div>}
        </React.Fragment>
      )}
      {slot && workspace.csvPreview && createPortal(workspace.csvPreview, slot)}
    </dialog>
  );
}
export function WorkspaceProvider({ children }) {
  const ref = useRef(null);
  if (!ref.current) ref.current = createWorkspace();
  const workspace = ref.current;
  const router = useRouter(),
    pathname = usePathname();
  const revision = useSyncExternalStore(
    workspace.subscribe,
    workspace.getSnapshot,
    workspace.getServerSnapshot,
  );
  workspace.attach(router);
  useEffect(() => {
    workspace.start();
    const unload = (e) => {
      if (workspace.state.localFailed && workspace.state.dirty) {
        e.preventDefault();
        e.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', unload);
    return () => {
      window.removeEventListener('beforeunload', unload);
      workspace.dispose();
    };
  }, [workspace]);
  useEffect(() => {
    workspace.routeChanged(pathname);
  }, [pathname, workspace]);
  useEffect(() => {
    document.title = `해답 · ${workspace.state.loginOpen ? '관리자 로그인' : workspace.views.pageNames[workspace.state.page] || 'SEA THE ANSWER'}`;
  }, [workspace, revision]);
  return (
    <Context.Provider
      value={{
        workspace,
        revision,
      }}
    >
      <div {...workspace.events}>
        <a className="skip" href="#main">
          본문 바로가기
        </a>
        {workspace.views.shell(children)}
        <Modal workspace={workspace} />
        <div id="toasts" role="status" aria-live="polite">
          {workspace.toasts.map((t) => (
            <div key={t.id} className="toast">
              {t.text}
            </div>
          ))}
        </div>
      </div>
    </Context.Provider>
  );
}
export function WorkspacePage({ name, id }) {
  const { workspace } = useWorkspace();
  if (workspace.state.routeError) return <div className="card pad"><h2>보고서를 불러올 수 없어요</h2><p>{workspace.state.routeError}</p><Button action="reportList" className="mt">보고서 목록</Button></div>;
  if (name === 'documentPage' && id && workspace.state.doc !== id)
    return <p role="status">문서를 불러오고 있어요…</p>;
  if (name === 'editorPage' && id && id !== 'new' && workspace.state.draft.id !== id)
    return <p role="status">보고서를 불러오고 있어요…</p>;
  return workspace.views[name]();
}
