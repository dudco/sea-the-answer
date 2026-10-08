import Link from 'next/link';
export default function NotFound() {
  return (
    <div className="card pad">
      <h1>페이지를 찾을 수 없어요</h1>
      <Link href="/chat">통합 질문으로 돌아가기</Link>
    </div>
  );
}
