'use client';

export default function ErrorPage({ reset }) {
  return (
    <div className="card pad">
      <h2>화면을 불러오지 못했어요.</h2>
      <p>입력한 내용은 브라우저 임시 보관이나 저장된 보고서에서 확인할 수 있습니다.</p>
      <button className="btn mt" onClick={reset}>
        다시 시도
      </button>
    </div>
  );
}
