// PDF.js is bundled locally: uploaded document bytes never leave this server/browser.
export async function extractPdf(file, progress = () => {}) {
  if (!file || file.size > 25 * 1024 * 1024) throw Error('25MB 이하의 PDF를 선택해 주세요.');
  const bytes = new Uint8Array(await file.arrayBuffer());
  const pdfjs = await import(/* webpackIgnore: true */ '/vendor/pdfjs/pdf.mjs');
  const base = new URL('/vendor/pdfjs/', window.location.origin).href;
  pdfjs.GlobalWorkerOptions.workerSrc = base + 'pdf.worker.mjs';
  const task = pdfjs.getDocument({
    data: bytes.slice(),
    cMapUrl: base + 'cmaps/',
    cMapPacked: true,
    standardFontDataUrl: base + 'standard_fonts/',
    isEvalSupported: false,
  });
  let pdf;
  try {
    pdf = await task.promise;
    if (pdf.numPages > 1000) throw Error('1,000페이지 이하의 PDF를 나누어 등록해 주세요.');
    const sections = [],
      emptyPages = [];
    let total = 0;
    for (let i = 1; i <= pdf.numPages; i++) {
      progress(`${i} / ${pdf.numPages}페이지의 텍스트를 읽는 중…`);
      const page = await pdf.getPage(i),
        content = await page.getTextContent();
      const text = content.items
        .map((x) => x.str + (x.hasEOL ? '\n' : ' '))
        .join('')
        .trim();
      if (text) {
        total += text.length;
        if (total > 2000000)
          throw Error('추출 텍스트가 2백만 자를 넘습니다. 문서를 나누어 주세요.');
        sections.push({
          page: i,
          heading: `페이지 ${i}`,
          text,
        });
      } else emptyPages.push(i);
      page.cleanup();
    }
    if (!sections.length)
      throw Error(
        '추출할 텍스트가 없습니다. 스캔 PDF는 OCR 처리 후 등록하거나 페이지별 본문을 입력해 주세요.',
      );
    let binary = '';
    for (let i = 0; i < bytes.length; i += 32768)
      binary += String.fromCharCode(...bytes.subarray(i, i + 32768));
    return {
      sections,
      emptyPages,
      file: {
        name: file.name,
        base64: btoa(binary),
      },
    };
  } finally {
    if (pdf) await pdf.destroy();
    else await task.destroy();
  }
}
export function sectionsToText(sections) {
  return sections.map((s) => `--- PAGE ${s.page || '?'} ---\n${s.text}`).join('\n\n');
}
export function textToSections(text, reference) {
  const parts = text.split(/^--- PAGE (\d+|\?) ---\s*$/m);
  if (parts.length === 1) {
    const s = [];
    for (let i = 0; i < text.trim().length; i += 19000)
      s.push({
        heading: reference || '본문',
        text: text.trim().slice(i, i + 19000),
      });
    return s;
  }
  const sections = [];
  for (let i = 1; i < parts.length; i += 2) {
    const page = parts[i] === '?' ? null : Number(parts[i]);
    const t = parts[i + 1]?.trim();
    if (t) {
      for (let j = 0; j < t.length; j += 19000)
        sections.push({
          page,
          heading: reference || `페이지 ${page || '미지정'}`,
          text: t.slice(j, j + 19000),
        });
    }
  }
  return sections;
}
