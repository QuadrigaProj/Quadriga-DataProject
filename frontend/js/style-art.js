/* 운동 스타일 유형의 대표 그림 — 유형마다 한 장.
 *
 * 동작 선 그림(move-art.js)과 같은 말투다: 둥근 끝의 굵은 선으로 그린 사람 + 그 유형을 말해 주는 소품 하나둘.
 * 다만 결과 화면과 공유 카드의 '얼굴' 이라, 유형마다 바탕색 · 선색 · 포인트색을 따로 준다.
 *
 * 그림 파일을 여덟 개 두지 않고 문자열로 갖고 있다가 <svg> 로 꺼내 쓴다 —
 * 결과 카드(canvas)에도 같은 그림을 그대로 그린다(image()).
 */
const STYLE_ART = (() => {
  // [바탕, 선, 포인트]
  const TONE = {
    runner:  ['#DDE9E0', '#1F4136', '#E0873C'],
    builder: ['#F3DFD3', '#7A2F1D', '#C1793C'],
    team:    ['#DCE8EC', '#23485A', '#E0873C'],
    racket:  ['#E1E2F0', '#34386F', '#D9653B'],
    rhythm:  ['#F3DEE4', '#7D2E47', '#C1793C'],
    balance: ['#E7E1F0', '#4B3A72', '#5F9C7D'],
    walker:  ['#E6EACF', '#3F4C1F', '#6FA15C'],
    quick:   ['#F6E6C8', '#7A4E10', '#D9653B'],
  };

  // 사람은 <g class="p"> (선색 · 굵기 11), 머리는 <circle class="h">, 소품은 포인트색 a / 선색 i 로 적는다.
  const BODY = {
    // 야외 러너형 — 앞으로 기운 달리기, 해와 바람
    runner: `<circle cx="160" cy="42" r="16" fill="A"/>
      <path d="M22 86H46M12 106H40" stroke="I" stroke-width="6" opacity=".35"/>
      <path d="M26 170H174" stroke="I" stroke-width="5" opacity=".3"/>
      <g class="p"><path d="M112 66L94 112"/><path d="M94 112L124 124L116 158"/><path d="M94 112L72 138L44 132"/>
        <path d="M110 74L132 90L150 76"/><path d="M110 74L86 82L74 104"/></g><circle class="h" cx="118" cy="50" r="13"/>`,
    // 근력 빌더형 — 바벨을 머리 위로
    builder: `<path d="M34 48H166" stroke="I" stroke-width="7"/>
      <path d="M46 28V68M154 28V68" stroke="A" stroke-width="14"/><path d="M62 36V60M138 36V60" stroke="I" stroke-width="9"/>
      <path d="M40 178H160" stroke="I" stroke-width="5" opacity=".3"/>
      <g class="p"><path d="M100 88V132"/><path d="M100 132L82 152L80 176"/><path d="M100 132L118 152L120 176"/>
        <path d="M100 94L74 84L72 50"/><path d="M100 94L126 84L128 50"/></g><circle class="h" cx="100" cy="72" r="13"/>`,
    // 팀플레이어형 — 공을 차는 사람과 기다리는 동료들
    team: `<g opacity=".38"><circle cx="150" cy="50" r="10" fill="I"/><path d="M132 84Q150 58 168 84" stroke="I" stroke-width="9" fill="none"/>
        <circle cx="40" cy="64" r="9" fill="I"/><path d="M24 94Q40 72 56 94" stroke="I" stroke-width="8" fill="none"/></g>
      <path d="M22 176H178" stroke="I" stroke-width="5" opacity=".3"/>
      <g class="p"><path d="M88 74L96 118"/><path d="M96 118L90 146L86 174"/><path d="M96 118L124 126L148 142"/>
        <path d="M90 80L68 92L56 78"/><path d="M90 80L112 94L126 106"/></g><circle class="h" cx="88" cy="58" r="13"/>
      <circle cx="168" cy="156" r="13" fill="#FFFDF7" stroke="I" stroke-width="5"/><path d="M168 149l6 5-2 7h-8l-2-7z" fill="A"/>`,
    // 라켓 승부사형 — 라켓을 치켜든 스매시
    racket: `<path d="M22 176H178" stroke="I" stroke-width="5" opacity=".3"/>
      <g class="p"><path d="M92 80L98 124"/><path d="M98 124L80 148L66 174"/><path d="M98 124L120 146L138 172"/>
        <path d="M94 86L118 72L132 50"/><path d="M94 86L70 96L58 82"/></g><circle class="h" cx="92" cy="64" r="13"/>
      <path d="M132 50L143 37" stroke="I" stroke-width="7"/>
      <ellipse cx="154" cy="24" rx="13" ry="17" transform="rotate(38 154 24)" fill="#FFFDF7" stroke="I" stroke-width="6"/>
      <circle cx="178" cy="70" r="7" fill="A"/><path d="M166 58L158 50M170 52L164 42" stroke="A" stroke-width="4"/>`,
    // 리듬 표현형 — 춤추는 사람과 음표
    rhythm: `<g fill="A" stroke="A" stroke-width="5"><ellipse cx="40" cy="62" rx="8" ry="6" transform="rotate(-20 40 62)" stroke="none"/><path d="M47 60V32Q60 36 58 50" fill="none"/>
        <ellipse cx="154" cy="106" rx="7" ry="5" transform="rotate(-20 154 106)" stroke="none"/><ellipse cx="176" cy="100" rx="7" ry="5" transform="rotate(-20 176 100)" stroke="none"/>
        <path d="M160 104V76L182 70V98" fill="none"/></g>
      <path d="M30 176H170" stroke="I" stroke-width="5" opacity=".3"/>
      <g class="p"><path d="M100 72Q93 94 98 118"/><path d="M98 118L92 146L98 174"/><path d="M98 118L124 132L142 156"/>
        <path d="M100 80L124 66L136 40"/><path d="M100 80L76 88L56 100"/></g><circle class="h" cx="100" cy="56" r="13"/>`,
    // 밸런스 유연형 — 나무 자세와 잎
    balance: `<ellipse cx="100" cy="180" rx="48" ry="7" fill="A" opacity=".45"/>
      <path d="M152 78Q170 68 172 48Q152 52 152 78Z" fill="A"/><path d="M48 104Q30 96 28 76Q48 80 48 104Z" fill="A"/>
      <g class="p"><path d="M100 84V130"/><path d="M100 130V176"/><path d="M100 130L136 146L106 158"/>
        <path d="M100 92L66 62L100 22"/><path d="M100 92L134 62L100 22"/></g><circle class="h" cx="100" cy="62" r="13"/>`,
    // 산책 회복형 — 느긋한 걸음과 나무
    walker: `<circle cx="154" cy="96" r="28" fill="A"/><circle cx="134" cy="112" r="16" fill="A"/><path d="M156 176V112" stroke="I" stroke-width="8"/>
      <path d="M22 176H178" stroke="I" stroke-width="5" opacity=".3"/>
      <g class="p"><path d="M84 76V124"/><path d="M84 124L72 148L62 174"/><path d="M84 124L98 148L108 174"/>
        <path d="M84 84L72 104L76 122"/><path d="M84 84L98 102L108 112"/></g><circle class="h" cx="84" cy="60" r="13"/>`,
    // 짬짬이 실속형 — 줄넘기와 초시계
    quick: `<path d="M58 94C22 132 50 184 92 184C134 184 162 132 126 94" stroke="A" stroke-width="5" fill="none"/>
      <circle cx="160" cy="52" r="19" fill="#FFFDF7" stroke="I" stroke-width="6"/><path d="M160 30V22M151 22H169" stroke="I" stroke-width="6"/>
      <path d="M160 52V39M160 52L169 57" stroke="A" stroke-width="5"/>
      <g class="p"><path d="M92 76V118"/><path d="M92 118L76 136L84 160"/><path d="M92 118L108 136L100 160"/>
        <path d="M92 84L72 100L58 94"/><path d="M92 84L112 100L126 94"/></g><circle class="h" cx="92" cy="60" r="13"/>`,
  };

  const has = id => Object.prototype.hasOwnProperty.call(BODY, id);

  /* 유형 id → <svg> 문자열. 모르는 id 면 빈 문자열(그림 없이도 화면은 그대로 나온다). */
  function svg(id, size = 160, label = ''){
    if (!has(id)) return '';
    const [bg, ink, accent] = TONE[id];
    const body = BODY[id].replace(/="A"/g, `="${accent}"`).replace(/="I"/g, `="${ink}"`)
      .replace(/<g class="p">/g, `<g fill="none" stroke="${ink}" stroke-width="11" stroke-linecap="round" stroke-linejoin="round">`)
      .replace(/<circle class="h"/g, `<circle fill="${ink}"`);
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" width="${size}" height="${size}" role="img" aria-label="${label}" stroke-linecap="round" stroke-linejoin="round"><rect width="200" height="200" rx="46" fill="${bg}"/>${body}</svg>`;
  }

  /* canvas 에 그릴 수 있게 그림을 이미지로 — 공유 카드가 쓴다. */
  function image(id, size = 400){
    return new Promise((resolve, reject) => {
      const s = svg(id, size);
      if (!s) { reject(new Error('no art')); return; }
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = reject;
      img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(s);
    });
  }

  return { svg, image, has, tone: id => (has(id) ? TONE[id] : null) };
})();
