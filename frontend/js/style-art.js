/* 운동 스타일 유형의 대표 그림 — 유형마다 사람 캐릭터 한 명 (애니메이션풍 SD 캐릭터).
 *
 * 여덟 명이 한 식구로 보이게 얼굴 틀(큰 머리 · 큰 눈 · 볼터치)은 chibi() 하나로 그리고,
 * 유형마다 머리 모양 · 머리색 · 눈색 · 옷 · 소품 · 표정만 갈아 끼운다. 선 없이 면과 그림자(셀 셰이딩)로 그린다.
 *
 * 그림 파일을 여덟 개 두지 않고 문자열로 갖고 있다가 <svg> 로 꺼내 쓴다 —
 * 결과 카드(canvas)에도 같은 그림을 그대로 그린다(image()).
 */
const STYLE_ART = (() => {
  // [바탕, 글자색(코드 · 카드 틀), 포인트]
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
  const SKIN = '#FFE2CC', SKIN_SHADE = '#F4C3A6', LINE = '#3A2A26';

  /* 눈 — 흰자 · 위가 짙은 눈동자 · 동공 · 반짝임 둘 · 윗속눈썹. closed 면 웃는 눈(^ ^). */
  function eyes(id, c, closed){
    if (closed) return `<g stroke="${LINE}" stroke-width="4.500" fill="none" stroke-linecap="round"><path d="M67 111Q80 98 93 111M107 111Q120 98 133 111"/></g>
      <g stroke="${LINE}" stroke-width="2.600" stroke-linecap="round"><path d="M66 108l-5-2M134 108l5-2"/></g>`;
    // dir: 바깥쪽 눈꼬리가 어느 쪽인가 (왼눈 -1, 오른눈 +1)
    const one = (x, dir) => `<g stroke="none"><ellipse cx="${x}" cy="110" rx="12" ry="14" fill="#fff"/>
      <ellipse cx="${x}" cy="111" rx="9.800" ry="12.500" fill="url(#eye-${id})"/><ellipse cx="${x}" cy="117" rx="6.500" ry="4.500" fill="${c[1]}" opacity=".85"/>
      <ellipse cx="${x}" cy="111" rx="4.200" ry="6" fill="${LINE}"/>
      <circle cx="${x - 3.800}" cy="104.500" r="3.800" fill="#fff"/><circle cx="${x + 3.600}" cy="117.500" r="1.800" fill="#fff"/>
      <path d="M${x - 14 * dir} 105Q${x - 2 * dir} 89 ${x + 13 * dir} 99L${x + 19 * dir} 95L${x + 15.500 * dir} 104Q${x} 94.500 ${x - 12.500 * dir} 108Z" fill="${LINE}"/></g>
      <g stroke="${LINE}" fill="none" stroke-linecap="round"><path d="M${x - 9} 92.500Q${x} 87 ${x + 9} 92" stroke-width="1.600" opacity=".45"/><path d="M${x - 7} 124.500Q${x} 127 ${x + 7} 124.500" stroke-width="1.600" opacity=".4"/></g>`;
    return `<defs><linearGradient id="eye-${id}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${c[0]}"/><stop offset="1" stop-color="${c[1]}"/></linearGradient></defs>${one(80, -1)}${one(120, 1)}`;
  }
  const MOUTH = {
    smile: `<path d="M93 133Q100 140 107 133" stroke="${LINE}" stroke-width="2.600" fill="none" stroke-linecap="round"/>`,
    open: `<path d="M92 131Q100 147 108 131Z" fill="#B5463C" stroke="${LINE}" stroke-width="2.200" stroke-linejoin="round"/><path d="M96 138Q100 142 104 138Q100 135.500 96 138Z" fill="#F29C8E" stroke="none"/>`,
    grin: `<path d="M90 129Q100 142 110 129Z" fill="#fff" stroke="${LINE}" stroke-width="2.600" stroke-linejoin="round"/>`,
    calm: `<path d="M95 132Q100 135 105 132" stroke="${LINE}" stroke-width="3" fill="none" stroke-linecap="round"/>`,
    cat: `<path d="M92 130Q96 136 100 131Q104 136 108 130" stroke="${LINE}" stroke-width="2.800" fill="none" stroke-linecap="round"/>`,
  };
  const BROWS = {
    soft: (h) => `<path d="M70 86Q80 82 90 85M110 85Q120 82 130 86" stroke="${h}" stroke-width="2.600" fill="none" stroke-linecap="round"/>`,
    keen: (h) => `<path d="M69 83Q80 82 91 87M131 83Q120 82 109 87" stroke="${h}" stroke-width="3" fill="none" stroke-linecap="round"/>`,
  };

  /* 한 명 그리기. back = 머리 뒤쪽(얼굴 뒤에 깔린다), front = 앞머리, under = 몸 뒤 소품, over = 맨 위 소품 */
  function chibi(id, o){
    const h = o.hair;
    // 면마다 같은 굵기의 짙은 갈색 선을 두른다(선화 + 셀 셰이딩). 그림자 · 볼터치 · 눈 속은 stroke="none".
    return `${o.under || ''}<g stroke="${LINE}" stroke-width="2.400" stroke-linejoin="round" stroke-linecap="round">${o.back || ''}
      <path d="M44 204Q46 168 76 160L124 160Q154 168 156 204Z" fill="${o.outfit}"/>${o.clothes || ''}
      <path d="M90 140H110V164Q100 172 90 164Z" fill="${SKIN}"/><path d="M91 150Q100 158 109 150V144H91Z" fill="${SKIN_SHADE}" stroke="none"/>
      <circle cx="55" cy="113" r="8" fill="${SKIN}"/><circle cx="145" cy="113" r="8" fill="${SKIN}"/>
      <path d="M54 102Q54 60 100 58Q146 60 146 102Q146 130 122 146Q100 158 78 146Q54 130 54 102Z" fill="${SKIN}"/>
      <path d="M57 97Q60 66 100 62Q140 66 143 97Q122 85 100 87Q78 85 57 97Z" fill="${SKIN_SHADE}" opacity=".7" stroke="none"/>
      <g stroke="none"><ellipse cx="68" cy="128" rx="9.500" ry="5.500" fill="#FF9D8F" opacity=".55"/><ellipse cx="132" cy="128" rx="9.500" ry="5.500" fill="#FF9D8F" opacity=".55"/></g>
      <path d="M64 127l3-4M69 129l3-4M128 129l3-4M133 127l3-4" stroke="#F0776A" stroke-width="1.400" opacity=".7"/>
      <path d="M99.500 122l1.500 2.500" stroke-width="1.600" opacity=".45" fill="none"/>
      ${eyes(id, o.eyes, o.closed)}${BROWS[o.brows || 'soft'](h[1])}${MOUTH[o.mouth || 'smile']}
      ${o.front || ''}${o.over || ''}</g>`;
  }

  const BODY = {
    // 바람의 야생마 — 높이 묶은 머리가 바람에 날리고, 머리띠를 맸다
    runner: () => { const h = ['#6B4632', '#4A2E20', '#8C6248']; return chibi('runner', { hair: h, eyes: ['#2F6B4F', '#7CC9A0'], outfit: '#2E5B4B', brows: 'keen', mouth: 'open',
      under: `<path d="M12 96H38M6 116H32M16 136H38" stroke="#1F4136" stroke-width="6" stroke-linecap="round" opacity=".28"/>`,
      back: `<path d="M128 58C168 40 196 70 186 112C182 132 168 140 160 130C172 108 164 86 140 80Z" fill="${h[0]}"/><path d="M150 62C176 60 188 84 182 108C176 90 166 76 146 74Z" fill="${h[2]}" opacity=".7" stroke="none"/>
        <path d="M50 108Q44 52 100 48Q156 52 150 108Q150 84 140 74L60 74Q50 84 50 108Z" fill="${h[0]}"/>`,
      clothes: `<path d="M82 160L100 176L118 160Z" fill="#FFF6EA"/><path d="M60 176H140" stroke="#E0873C" stroke-width="5"/>`,
      front: `<path d="M52 100Q50 54 100 50Q150 54 148 100Q140 78 124 72Q120 88 104 92Q108 80 100 72Q92 92 70 94Q76 82 72 74Q58 80 52 100Z" fill="${h[0]}"/>
        <path d="M70 60Q100 50 130 60" stroke="${h[2]}" stroke-width="5" fill="none" stroke-linecap="round" opacity=".8"/>
        <path d="M51 84Q100 66 149 84L149 74Q100 56 51 74Z" fill="#E0873C"/><path d="M149 78L172 68L166 82L178 90L149 86Z" fill="#E0873C"/>` }); },
    // 우직한 불곰 — 짧은 머리, 민소매, 어깨에 아령
    builder: () => { const h = ['#2E2A2A', '#1B1818', '#55504E']; return chibi('builder', { hair: h, eyes: ['#5A3420', '#C98A5A'], outfit: '#C1793C', brows: 'keen', mouth: 'grin',
      back: `<path d="M50 104Q46 50 100 46Q154 50 150 104Q150 80 138 70L62 70Q50 80 50 104Z" fill="${h[0]}"/>`,
      clothes: `<path d="M44 200Q46 172 66 164L78 200Z" fill="${SKIN}"/><path d="M156 200Q154 172 134 164L122 200Z" fill="${SKIN}"/><path d="M84 160L100 174L116 160Z" fill="${SKIN}"/>`,
      front: `<path d="M52 98Q50 52 100 48Q150 52 148 98Q142 80 132 74L126 86L116 72L106 88L96 72L86 88L76 74L68 84Q58 84 52 98Z" fill="${h[0]}"/>
        <path d="M72 58Q100 48 128 58" stroke="${h[2]}" stroke-width="5" fill="none" stroke-linecap="round" opacity=".7"/>`,
      over: `<rect x="120" y="172" width="64" height="9" rx="4.500" fill="#A9ADB3"/><rect x="112" y="156" width="16" height="42" rx="7" fill="#7A2F1D"/><rect x="176" y="156" width="16" height="42" rx="7" fill="#7A2F1D"/>
        <ellipse cx="150" cy="178" rx="13" ry="11" fill="${SKIN}"/><path d="M140 176h20" stroke="${SKIN_SHADE}" stroke-width="2.500"/>` }); },
    // 무리의 늑대 — 헝클어진 머리, 유니폼, 옆구리에 공. 뒤에 동료들
    team: () => { const h = ['#3E5A72', '#2A4258', '#6E8CA6']; return chibi('team', { hair: h, eyes: ['#1E5F8C', '#7CC4EE'], outfit: '#E0873C', mouth: 'open',
      under: `<g fill="#B9CCD5"><circle cx="34" cy="120" r="24"/><path d="M6 200Q8 160 34 152Q60 160 62 200Z"/><circle cx="168" cy="116" r="24"/><path d="M140 200Q142 156 168 148Q194 156 196 200Z"/></g>`,
      back: `<path d="M48 110Q42 48 100 44Q158 48 152 110L144 96L138 112Q140 84 130 72L70 72Q60 84 62 112L56 96Z" fill="${h[0]}"/>`,
      clothes: `<path d="M80 160L100 180L120 160L112 160L100 170L88 160Z" fill="#FFF6EA"/><path d="M96 184h8v12h-8z" fill="#FFF6EA"/>`,
      front: `<path d="M52 100Q48 50 100 46Q152 50 148 100L138 82L130 94L120 76L110 92L100 74L90 92L80 76L72 94L62 82Z" fill="${h[0]}"/>
        <path d="M70 58Q100 46 130 58" stroke="${h[2]}" stroke-width="5" fill="none" stroke-linecap="round" opacity=".8"/>`,
      over: `<circle cx="160" cy="172" r="23" fill="#FFFDF7" stroke="#23485A" stroke-width="4"/><path d="M160 159l10 7.500-4 11h-12l-4-11z" fill="#23485A"/>
        <path d="M160 159v-9M170 166.500l9-3M166 177.500l5.500 8M154 177.500l-5.500 8M150 166.500l-9-3" stroke="#23485A" stroke-width="3" stroke-linecap="round"/>` }); },
    // 승부의 송골매 — 단발에 선바이저, 매서운 눈썹, 어깨 뒤에 라켓
    racket: () => { const h = ['#4A3F6B', '#332A50', '#7A6EA0']; return chibi('racket', { hair: h, eyes: ['#5A3FA0', '#B9A2F0'], outfit: '#F4F1E6', brows: 'keen', mouth: 'smile',
      under: `<path d="M150 200L164 146" stroke="#34386F" stroke-width="8" stroke-linecap="round"/><ellipse cx="170" cy="114" rx="20" ry="27" transform="rotate(14 170 114)" fill="#FFFDF7" stroke="#34386F" stroke-width="6"/>
        <path d="M157 102L185 108M155 117L184 123M166 90L161 138M179 92L174 140" stroke="#34386F" stroke-width="2" opacity=".5"/>`,
      back: `<path d="M46 132Q38 48 100 44Q162 48 154 132Q156 146 144 146L140 100L60 100L56 146Q44 146 46 132Z" fill="${h[0]}"/>`,
      clothes: `<path d="M82 160L100 178L118 160Z" fill="#34386F"/><path d="M44 200Q46 176 60 168" stroke="#D9653B" stroke-width="5" fill="none"/><path d="M156 200Q154 176 140 168" stroke="#D9653B" stroke-width="5" fill="none"/>`,
      front: `<path d="M52 104Q48 50 100 46Q152 50 148 104Q142 84 134 78Q110 92 66 82Q56 88 52 104Z" fill="${h[0]}"/>
        <path d="M50 84Q100 62 150 84L152 74Q100 50 48 74Z" fill="#FFFDF7"/><path d="M46 84Q100 70 154 84Q160 90 150 92Q100 80 50 92Q40 90 46 84Z" fill="#D9653B"/>
        <path d="M72 58Q100 48 128 58" stroke="${h[2]}" stroke-width="5" fill="none" stroke-linecap="round" opacity=".7"/>` }); },
    // 파도 타는 돌고래 — 양갈래 머리, 헤드폰, 음표
    rhythm: () => { const h = ['#E27A9B', '#B9506F', '#F7B3C6']; return chibi('rhythm', { hair: h, eyes: ['#A03A66', '#F59BC0'], outfit: '#7D2E47', mouth: 'open',
      under: `<g fill="#C1793C" stroke="#C1793C" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"><ellipse cx="24" cy="62" rx="7" ry="5" transform="rotate(-20 24 62)" stroke="none"/><path d="M29 61V34Q42 38 40 50" fill="none"/>
        <ellipse cx="166" cy="50" rx="6.500" ry="4.500" transform="rotate(-20 166 50)" stroke="none"/><ellipse cx="186" cy="44" rx="6.500" ry="4.500" transform="rotate(-20 186 44)" stroke="none"/><path d="M171 48V24L191 18V42" fill="none"/></g>`,
      back: `<circle cx="40" cy="78" r="24" fill="${h[0]}"/><circle cx="160" cy="78" r="24" fill="${h[0]}"/><circle cx="34" cy="70" r="9" fill="${h[2]}" opacity=".6" stroke="none"/><circle cx="154" cy="70" r="9" fill="${h[2]}" opacity=".6" stroke="none"/>
        <path d="M50 110Q44 50 100 46Q156 50 150 110Q150 84 140 74L60 74Q50 84 50 110Z" fill="${h[0]}"/>`,
      clothes: `<path d="M82 160L100 176L118 160Z" fill="#FFF6EA"/><path d="M70 178l8 6 8-6M114 178l8 6 8-6" stroke="#F7B3C6" stroke-width="3" fill="none" stroke-linecap="round"/>`,
      front: `<path d="M52 102Q48 52 100 48Q152 52 148 102Q142 80 128 74Q118 92 100 90Q82 92 72 74Q58 80 52 102Z" fill="${h[0]}"/>
        <path d="M70 60Q100 48 130 60" stroke="${h[2]}" stroke-width="5" fill="none" stroke-linecap="round" opacity=".85"/>
        <path d="M50 96Q52 40 100 40Q148 40 150 96" stroke="#3A2A26" stroke-width="7" fill="none" stroke-linecap="round"/>
        <rect x="40" y="92" width="18" height="34" rx="9" fill="#3A2A26"/><rect x="142" y="92" width="18" height="34" rx="9" fill="#3A2A26"/><rect x="44" y="98" width="7" height="22" rx="3.500" fill="#C1793C"/><rect x="149" y="98" width="7" height="22" rx="3.500" fill="#C1793C"/>` }); },
    // 기지개 켜는 고양이 — 긴 머리를 낮게 묶고 눈을 감았다. 가슴 앞에 두 손, 잎 머리핀
    balance: () => { const h = ['#8E7AB8', '#6A578F', '#B9A9DA']; return chibi('balance', { hair: h, eyes: ['#4B3A72', '#B9A9DA'], outfit: '#F4F0FA', closed: true, mouth: 'calm',
      under: `<path d="M160 72Q180 62 182 40Q160 46 160 72Z" fill="#5F9C7D"/><path d="M36 100Q18 92 16 72Q36 76 36 100Z" fill="#5F9C7D"/>`,
      back: `<path d="M46 150Q34 46 100 42Q166 46 154 150Q156 186 138 190L134 110L66 110L62 190Q44 186 46 150Z" fill="${h[0]}"/><path d="M58 150Q52 120 60 100" stroke="${h[2]}" stroke-width="5" fill="none" stroke-linecap="round" opacity=".6"/>`,
      clothes: `<path d="M84 160L100 182L116 160Z" fill="#8E7AB8"/>`,
      front: `<path d="M52 104Q48 50 100 46Q152 50 148 104Q146 84 136 76Q104 70 82 96Q80 82 84 74Q60 80 52 104Z" fill="${h[0]}"/>
        <path d="M70 60Q100 48 130 60" stroke="${h[2]}" stroke-width="5" fill="none" stroke-linecap="round" opacity=".85"/>
        <path d="M128 66Q142 58 146 44Q130 46 128 66Z" fill="#5F9C7D"/>`,
      over: `<path d="M99 166Q86 168 86 186Q88 200 99 200Z" fill="${SKIN}"/><path d="M101 166Q114 168 114 186Q112 200 101 200Z" fill="${SKIN}"/><path d="M100 168V198" stroke="${SKIN_SHADE}" stroke-width="2.500"/>` }); },
    // 느긋한 거북이 — 벙거지 모자, 단발, 배낭 끈
    walker: () => { const h = ['#7A5A3A', '#5A4028', '#A8835C']; return chibi('walker', { hair: h, eyes: ['#4E6A2A', '#A9CF7A'], outfit: '#8DB56F', mouth: 'smile',
      under: `<circle cx="164" cy="44" r="16" fill="#F2D27A"/><path d="M6 180Q40 150 78 176T150 172T200 176V200H0Z" fill="#B9D39A" opacity=".8"/>`,
      back: `<path d="M48 138Q40 52 100 48Q160 52 152 138Q152 150 142 150L138 104L62 104L58 150Q48 150 48 138Z" fill="${h[0]}"/>`,
      clothes: `<path d="M82 160L100 176L118 160Z" fill="#FFF6EA"/><path d="M70 162Q64 182 66 200M130 162Q136 182 134 200" stroke="#5A4028" stroke-width="9" fill="none" stroke-linecap="round"/>`,
      front: `<path d="M54 106Q52 70 100 68Q148 70 146 106Q140 90 128 86Q112 96 72 88Q60 92 54 106Z" fill="${h[0]}"/>
        <path d="M30 86Q100 62 170 86Q178 96 164 98Q100 80 36 98Q22 96 30 86Z" fill="#E9BD5C"/><path d="M56 84Q58 34 100 32Q142 34 144 84Q100 70 56 84Z" fill="#F2CE76"/><path d="M57 78Q100 64 143 78" stroke="#6FA15C" stroke-width="7" fill="none"/>` }); },
    // 틈새의 다람쥐 — 짧은 머리에 삐죽 솟은 머리카락, 후드티, 손에 초시계
    quick: () => { const h = ['#D98848', '#B5652A', '#F2B57E']; return chibi('quick', { hair: h, eyes: ['#9A4A12', '#F0A860'], outfit: '#F2B84B', mouth: 'cat',
      under: `<path d="M20 60l8 14-14 2 12 10-6 14 14-8 10 12 2-16 14-4-12-8 4-14-14 6z" fill="#FFF3C4" opacity=".9"/>`,
      back: `<path d="M50 108Q46 50 100 46Q154 50 150 108Q150 84 140 72L60 72Q50 84 50 108Z" fill="${h[0]}"/>
        <path d="M58 200Q52 162 72 150Q100 140 128 150Q148 162 142 200Z" fill="#E0A23A"/>`,
      clothes: `<path d="M80 160Q100 178 120 160L126 170Q100 190 74 170Z" fill="#E0A23A"/><path d="M92 178v16M108 178v16" stroke="#FFF6EA" stroke-width="3" stroke-linecap="round"/>`,
      front: `<path d="M52 100Q50 52 100 48Q150 52 148 100Q142 80 130 74Q122 90 106 90Q110 80 104 72Q90 92 68 92Q74 82 72 74Q58 80 52 100Z" fill="${h[0]}"/>
        <path d="M96 50Q92 26 110 22Q104 36 112 48Z" fill="${h[0]}"/><path d="M70 60Q100 48 130 60" stroke="${h[2]}" stroke-width="5" fill="none" stroke-linecap="round" opacity=".85"/>`,
      over: `<path d="M150 150V142M142 142H158" stroke="#7A4E10" stroke-width="6" stroke-linecap="round"/><circle cx="150" cy="172" r="21" fill="#FFFDF7" stroke="#7A4E10" stroke-width="6"/>
        <path d="M150 172V158M150 172L160 178" stroke="#D9653B" stroke-width="5" stroke-linecap="round"/><ellipse cx="130" cy="184" rx="11" ry="9" fill="${SKIN}"/>` }); },
  };

  const has = id => Object.prototype.hasOwnProperty.call(BODY, id);

  /* 유형 id → <svg> 문자열. 모르는 id 면 빈 문자열(그림 없이도 화면은 그대로 나온다). */
  function svg(id, size = 160, label = ''){
    if (!has(id)) return '';
    const clip = `sa-${id}`;
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" width="${size}" height="${size}" role="img" aria-label="${label}"><defs><clipPath id="${clip}"><rect width="200" height="200" rx="46"/></clipPath></defs><g clip-path="url(#${clip})"><rect width="200" height="200" fill="${TONE[id][0]}"/>${BODY[id]()}</g></svg>`;
  }

  /* 유형 × 성별 그림 파일 — 같은 유형이어도 사용자의 성별에 따라 다른 그림이 나온다 (예현 요청).
     SD 캐릭터(애니메이션과 일러스트의 중간 그림체), img/style/<유형>-<m|f>.webp. 성별을 모르면 여성 그림을 쓴다.
     파일이 없거나 못 받으면 위의 SVG 그림으로 돌아간다 — 그림 때문에 화면이 비는 일은 없다. */
  const photo = (id, sex) => (has(id) ? `/img/style/${id}-${sex === 'M' ? 'm' : 'f'}.webp` : '');

  /* 결과 화면에 넣을 그림 — <img>. 못 받으면 그 자리를 SVG 로 바꾼다. */
  function html(id, sex, size = 160, label = ''){
    if (!has(id)) return '';
    const alt = String(label).replace(/"/g, '&quot;');
    return `<img src="${photo(id, sex)}" width="${size}" height="${size}" alt="${alt}" decoding="async" style="display:block;border-radius:23%;object-fit:cover" onerror="this.outerHTML = STYLE_ART.svg('${id}', ${size}, this.alt)">`;
  }

  function svgImage(id, size){
    return new Promise((resolve, reject) => {
      const s = svg(id, size);
      if (!s) { reject(new Error('no art')); return; }
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = reject;
      img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(s);
    });
  }

  /* canvas 에 그릴 수 있게 그림을 이미지로 — 공유 카드가 쓴다. 성별 그림을 SVG 와 같은 둥근 네모로 오려서 준다. */
  function image(id, size = 400, sex){
    return new Promise((resolve, reject) => {
      if (!has(id)) { reject(new Error('no art')); return; }
      const img = new Image();
      img.onload = () => {
        const c = document.createElement('canvas'); c.width = c.height = size;
        const g = c.getContext('2d'), r = size * 0.23;
        g.beginPath(); g.moveTo(r, 0); g.arcTo(size, 0, size, size, r); g.arcTo(size, size, 0, size, r);
        g.arcTo(0, size, 0, 0, r); g.arcTo(0, 0, size, 0, r); g.closePath(); g.clip();
        g.drawImage(img, 0, 0, size, size);
        resolve(c);
      };
      img.onerror = () => svgImage(id, size).then(resolve, reject);
      img.src = photo(id, sex);
    });
  }

  return { svg, html, image, photo, has, tone: id => (has(id) ? TONE[id] : null) };
})();
