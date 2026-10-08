import '../styles/base.css';
import '../styles/workspace.css';
import { WorkspaceProvider } from '../workspace/provider';
export const metadata = {
  title: '해답 · SEA THE ANSWER',
  description: '선박 운항 업무지원 · 문서·운항 데이터·보고서',
};
export default function RootLayout({ children }) {
  return (
    <html lang="ko">
      <head>
        <link rel="stylesheet" href="/fonts/prototype/fonts.css" />
        <link rel="icon" href="/favicon.svg" />
      </head>
      <body>
        <WorkspaceProvider>{children}</WorkspaceProvider>
      </body>
    </html>
  );
}
