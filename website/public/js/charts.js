// 아주 가벼운 SVG 바 차트 유틸 (라이브러리 없이, dataviz 가이드의 마크 규격을 따름)
// - 막대 두께 <=24px, 데이터 끝 4px 라운드 / 베이스라인 쪽은 각짐
// - 인접 막대 사이 2px 서지 갭
// - 값은 막대 끝에 직접 라벨
(function (global) {
  function css(varName) {
    return getComputedStyle(document.documentElement).getPropertyValue(varName).trim();
  }

  // 순위형 단일 계열 가로 막대 (예: 약점 우선순위 what-if)
  function renderRankedBars(el, { items, unit = '', highlightNote = '가장 효과적' }) {
    const w = el.clientWidth || 300;
    const rowH = 34;
    const gap = 10;
    const labelW = 78;
    const trackW = w - labelW - 46;
    const h = items.length * (rowH + gap) - gap;
    const maxVal = Math.max(1, ...items.map((i) => Math.abs(i.value)));
    const color = css('--series-1') || '#2a78d6';
    const ink2 = css('--ink-2') || '#52514e';
    const ink = css('--ink') || '#0b0b0b';

    let bars = '';
    items.forEach((item, i) => {
      const y = i * (rowH + gap);
      const barW = Math.max(4, (Math.abs(item.value) / maxVal) * trackW);
      const isTop = i === 0;
      bars += `
        <text x="0" y="${y + rowH / 2 + 4}" class="cat-label">${escapeXml(item.label)}</text>
        <rect x="${labelW}" y="${y + (rowH - 14) / 2}" width="${trackW}" height="14" rx="7" fill="${ink2}" opacity="0.12"></rect>
        <rect x="${labelW}" y="${y + (rowH - 14) / 2}" width="${barW}" height="14" rx="7" fill="${color}"></rect>
        <text x="${labelW + barW + 8}" y="${y + rowH / 2 + 4}" class="value-label">${item.value > 0 ? '-' : ''}${Math.abs(item.value)}${unit}</text>
        ${isTop ? `<text x="${labelW}" y="${y - 4}" class="axis-label" fill="${color}">★ ${highlightNote}</text>` : ''}
      `;
    });

    el.innerHTML = `<svg class="barchart" viewBox="0 0 ${w} ${h + 14}" width="100%" height="${h + 14}">${bars}</svg>`;
  }

  // 2계열 그룹형 세로 막대 (예: 재점검 전/후 비교)
  function renderGroupedBars(el, { categories, seriesA, seriesB, yMax = 5 }) {
    const w = el.clientWidth || 300;
    const h = 180;
    const padTop = 10, padBottom = 26, padLeft = 10, padRight = 10;
    const plotH = h - padTop - padBottom;
    const colW = (w - padLeft - padRight) / categories.length;
    const barW = Math.min(24, colW * 0.28);
    const gap = 3;
    const ink2 = css('--ink-2') || '#52514e';
    const grid = css('--grid') || '#e1e0d9';
    const baseline = css('--baseline') || '#c3c2b7';

    const scaleY = (v) => plotH - (v / yMax) * plotH;

    let gridLines = '';
    for (let g = 0; g <= yMax; g++) {
      const y = padTop + scaleY(g);
      gridLines += `<line x1="${padLeft}" y1="${y}" x2="${w - padRight}" y2="${y}" stroke="${grid}" stroke-width="1"/>`;
    }

    let bars = '';
    categories.forEach((cat, i) => {
      const cx = padLeft + colW * i + colW / 2;
      const vA = seriesA.values[i];
      const vB = seriesB.values[i];
      const xA = cx - barW - gap / 2;
      const xB = cx + gap / 2;
      const yA = padTop + scaleY(vA);
      const yB = padTop + scaleY(vB);
      const baseY = padTop + plotH;

      bars += barRect(xA, yA, barW, baseY - yA, seriesA.color);
      bars += barRect(xB, yB, barW, baseY - yB, seriesB.color);
      bars += `<text x="${cx}" y="${h - 6}" text-anchor="middle" class="cat-label">${escapeXml(cat)}</text>`;
      bars += `<text x="${xA + barW / 2}" y="${yA - 5}" text-anchor="middle" class="value-label">${vA}</text>`;
      bars += `<text x="${xB + barW / 2}" y="${yB - 5}" text-anchor="middle" class="value-label">${vB}</text>`;
    });

    const baselineY = padTop + plotH;
    el.innerHTML = `
      <svg class="barchart" viewBox="0 0 ${w} ${h}" width="100%" height="${h}">
        ${gridLines}
        ${bars}
        <line x1="${padLeft}" y1="${baselineY}" x2="${w - padRight}" y2="${baselineY}" stroke="${baseline}" stroke-width="1"/>
      </svg>
      <div class="legend">
        <span><span class="dot" style="background:${seriesA.color}"></span>${escapeXml(seriesA.label)}</span>
        <span><span class="dot" style="background:${seriesB.color}"></span>${escapeXml(seriesB.label)}</span>
      </div>
    `;
  }

  function barRect(x, y, w, h, fill) {
    const rTop = Math.min(4, Math.max(0, h) / 2);
    if (h <= 0) return '';
    // 위쪽만 4px 라운드, 베이스라인 쪽은 각짐 (path로 표현)
    return `<path d="M ${x} ${y + h}
      L ${x} ${y + rTop}
      Q ${x} ${y} ${x + rTop} ${y}
      L ${x + w - rTop} ${y}
      Q ${x + w} ${y} ${x + w} ${y + rTop}
      L ${x + w} ${y + h} Z" fill="${fill}"/>`;
  }

  function escapeXml(s) {
    return String(s).replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
  }

  global.Charts = { renderRankedBars, renderGroupedBars };
})(window);
