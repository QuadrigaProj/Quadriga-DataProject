/* 운동 스타일 유형의 대표 그림 — 유형마다 캐릭터 한 마리.
 *
 * 유형 이름이 은유(바람의 야생마 · 우직한 불곰 …)라서 그림도 그 동물이 그 운동을 하는 모습이다.
 * 같은 눈 · 같은 볼터치 · 같은 둥근 모서리로 한 식구처럼 보이게 그렸다. 선 없이 면으로만 그린다.
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

  // 식구끼리 같은 눈과 볼터치
  const eye = (x, y, s = 1) => `<ellipse cx="${x}" cy="${y}" rx="${5.2 * s}" ry="${6.2 * s}" fill="#2A211C"/><circle cx="${x - 1.6 * s}" cy="${y - 2.2 * s}" r="${1.9 * s}" fill="#fff"/>`;
  const blush = (x1, x2, y) => `<ellipse cx="${x1}" cy="${y}" rx="8" ry="5" fill="#F29C8E" opacity=".55"/><ellipse cx="${x2}" cy="${y}" rx="8" ry="5" fill="#F29C8E" opacity=".55"/>`;

  const BODY = {
    // 바람의 야생마 — 머리띠를 맨 말, 갈기가 바람에 날린다
    runner: `<path d="M14 98H40M6 116H34M18 134H40" stroke="#1F4136" stroke-width="6" stroke-linecap="round" opacity=".3"/>
      <path d="M96 44C132 30 172 52 176 96C178 120 164 132 150 124C158 104 150 84 132 76Z" fill="#5B3A29"/>
      <path d="M58 200Q60 164 100 160Q140 164 142 200Z" fill="#C08A5C"/>
      <path d="M66 78Q56 40 80 46Q88 62 82 80Z" fill="#C08A5C"/><path d="M70 72Q66 52 78 54Q82 64 79 74Z" fill="#EBC3A4"/>
      <path d="M134 78Q144 40 120 46Q112 62 118 80Z" fill="#C08A5C"/><path d="M130 72Q134 52 122 54Q118 64 121 74Z" fill="#EBC3A4"/>
      <ellipse cx="100" cy="106" rx="41" ry="50" fill="#C08A5C"/>
      <ellipse cx="100" cy="143" rx="31" ry="25" fill="#EDD6BC"/>
      <ellipse cx="90" cy="147" rx="3.6" ry="5" fill="#5B3A29"/><ellipse cx="110" cy="147" rx="3.6" ry="5" fill="#5B3A29"/>
      <path d="M92 158Q100 164 108 158" stroke="#5B3A29" stroke-width="3" fill="none" stroke-linecap="round"/>
      <path d="M82 62Q100 42 120 64Q112 86 98 80Q88 76 82 62Z" fill="#5B3A29"/>
      <path d="M60 92Q100 76 140 92L140 80Q100 64 60 80Z" fill="#E0873C"/>
      <path d="M140 84L164 74L158 88L170 96L140 92Z" fill="#E0873C"/>
      ${eye(82, 110)}${eye(118, 110)}${blush(70, 130, 124)}`,
    // 우직한 불곰 — 아령을 든 곰
    builder: `<path d="M42 200Q44 160 100 156Q156 160 158 200Z" fill="#8A5A3C"/>
      <circle cx="60" cy="64" r="17" fill="#8A5A3C"/><circle cx="60" cy="64" r="9" fill="#C99A78"/>
      <circle cx="140" cy="64" r="17" fill="#8A5A3C"/><circle cx="140" cy="64" r="9" fill="#C99A78"/>
      <circle cx="100" cy="104" r="54" fill="#8A5A3C"/>
      <ellipse cx="100" cy="124" rx="25" ry="20" fill="#E6C9AA"/>
      <ellipse cx="100" cy="115" rx="8.5" ry="6.5" fill="#3B2418"/>
      <path d="M100 121V128M100 128Q94 135 87 131M100 128Q106 135 113 131" stroke="#3B2418" stroke-width="3" fill="none" stroke-linecap="round"/>
      ${eye(80, 98)}${eye(120, 98)}${blush(66, 134, 116)}
      <rect x="40" y="168" width="120" height="8" rx="4" fill="#A9ADB3"/>
      <rect x="26" y="146" width="20" height="52" rx="8" fill="#C1793C"/><rect x="46" y="154" width="11" height="36" rx="5.500" fill="#7A2F1D"/>
      <rect x="154" y="146" width="20" height="52" rx="8" fill="#C1793C"/><rect x="143" y="154" width="11" height="36" rx="5.500" fill="#7A2F1D"/>
      <ellipse cx="78" cy="172" rx="12" ry="11" fill="#6F4429"/><ellipse cx="122" cy="172" rx="12" ry="11" fill="#6F4429"/>`,
    // 무리의 늑대 — 뒤에 무리가 있고, 공을 끼고 있다
    team: `<g fill="#B5C8D1"><path d="M22 80L28 52L44 70Z"/><path d="M62 80L56 52L40 70Z"/><circle cx="42" cy="92" r="24"/>
        <path d="M140 74L146 46L162 64Z"/><path d="M180 74L174 46L158 64Z"/><circle cx="160" cy="86" r="24"/></g>
      <path d="M46 200Q48 162 100 158Q152 162 154 200Z" fill="#E0873C"/><path d="M84 160L100 178L116 160Z" fill="#FFF6EA"/>
      <path d="M58 100L60 40L98 74Z" fill="#6B7C8C"/><path d="M66 88L67 58L86 76Z" fill="#CBD5DC"/>
      <path d="M142 100L140 40L102 74Z" fill="#6B7C8C"/><path d="M134 88L133 58L114 76Z" fill="#CBD5DC"/>
      <path d="M100 58C134 58 152 82 150 108C149 118 158 126 160 134C148 136 140 142 132 150C122 158 78 158 68 150C60 142 52 136 40 134C42 126 51 118 50 108C48 82 66 58 100 58Z" fill="#6B7C8C"/>
      <path d="M100 94C84 96 72 110 66 128C76 150 90 156 100 156C110 156 124 150 134 128C128 110 116 96 100 94Z" fill="#F1F4F6"/>
      <ellipse cx="100" cy="130" rx="8.5" ry="6.5" fill="#2A211C"/>
      <path d="M100 136V142M100 142Q94 148 88 145M100 142Q106 148 112 145" stroke="#2A211C" stroke-width="3" fill="none" stroke-linecap="round"/>
      ${eye(80, 108)}${eye(120, 108)}${blush(68, 132, 124)}
      <circle cx="160" cy="166" r="22" fill="#FFFDF7" stroke="#23485A" stroke-width="4"/>
      <path d="M160 154l9 7-3.5 10h-11L151 161z" fill="#23485A"/><path d="M160 154V146M169 161l8-3M165.500 171l5 7M154.500 171l-5 7M151 161l-8-3" stroke="#23485A" stroke-width="3" stroke-linecap="round"/>`,
    // 한 점의 송골매 — 눈매가 매서운 매, 어깨에 라켓
    racket: `<path d="M150 196L164 142" stroke="#34386F" stroke-width="8" stroke-linecap="round"/>
      <ellipse cx="170" cy="112" rx="19" ry="26" transform="rotate(14 170 112)" fill="#FFFDF7" stroke="#34386F" stroke-width="6"/>
      <path d="M158 100L184 106M156 114L184 120M166 90L162 134M178 92L174 136" stroke="#34386F" stroke-width="2" opacity=".5"/>
      <path d="M44 200Q46 162 100 158Q154 162 156 200Z" fill="#4F5D80"/>
      <path d="M70 200Q72 172 100 170Q128 172 130 200Z" fill="#F4F1E6"/>
      <path d="M88 184l4 5 4-5M104 184l4 5 4-5M96 194l4 5 4-5" stroke="#4F5D80" stroke-width="2.5" fill="none" stroke-linecap="round"/>
      <circle cx="100" cy="104" r="52" fill="#4F5D80"/>
      <path d="M100 96C80 96 64 108 62 128C70 148 86 156 100 156C114 156 130 148 138 128C136 108 120 96 100 96Z" fill="#F4F1E6"/>
      <path d="M70 106Q64 132 76 146Q82 128 84 110Z" fill="#2E3757"/><path d="M130 106Q136 132 124 146Q118 128 116 110Z" fill="#2E3757"/>
      <path d="M100 108L86 118Q92 146 100 150Q108 146 114 118Z" fill="#F2B84B"/><path d="M93 136Q100 154 100 154Q100 154 107 136Q100 140 93 136Z" fill="#55504A"/>
      <circle cx="80" cy="104" r="10" fill="#F2B84B"/><circle cx="120" cy="104" r="10" fill="#F2B84B"/>
      <circle cx="81" cy="105" r="6" fill="#2A211C"/><circle cx="119" cy="105" r="6" fill="#2A211C"/><circle cx="79" cy="102.500" r="2" fill="#fff"/><circle cx="117" cy="102.500" r="2" fill="#fff"/>
      <path d="M64 90L92 97M136 90L108 97" stroke="#2E3757" stroke-width="5" stroke-linecap="round"/>`,
    // 파도 타는 돌고래 — 물 위로 뛰어오른 돌고래와 음표
    rhythm: `<g fill="#C1793C"><ellipse cx="38" cy="60" rx="8" ry="6" transform="rotate(-20 38 60)"/><path d="M43 59V30Q57 34 55 48" fill="none" stroke="#C1793C" stroke-width="5" stroke-linecap="round"/>
        <ellipse cx="150" cy="40" rx="7" ry="5" transform="rotate(-20 150 40)"/><ellipse cx="172" cy="34" rx="7" ry="5" transform="rotate(-20 172 34)"/>
        <path d="M156 38V14L178 8V32" fill="none" stroke="#C1793C" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/></g>
      <path d="M44 146L20 132Q26 152 44 156Q32 166 30 180Q48 176 56 160Z" fill="#4C7FA8"/>
      <path d="M44 150C56 100 96 68 130 66C152 64 166 74 172 84L190 92Q176 104 158 102C134 126 96 148 56 160Z" fill="#5C8FB8"/>
      <path d="M56 160C96 148 134 126 158 102Q176 104 190 92Q170 98 150 96C120 110 86 136 50 152Z" fill="#E3EEF5"/>
      <path d="M104 76Q100 46 128 48Q120 62 124 70Z" fill="#4C7FA8"/>
      <path d="M112 116Q120 142 100 148Q104 130 100 120Z" fill="#4C7FA8"/>
      ${eye(152, 82, .9)}<ellipse cx="140" cy="94" rx="7" ry="4.500" fill="#F29C8E" opacity=".55"/>
      <path d="M164 96Q174 98 182 93" stroke="#2A211C" stroke-width="3" fill="none" stroke-linecap="round"/>
      <path d="M0 176Q16 162 34 176T68 176T102 176T136 176T170 176T204 176V200H0Z" fill="#9CCBE0"/>
      <path d="M0 188Q16 176 34 188T68 188T102 188T136 188T170 188T204 188V200H0Z" fill="#C6E2EE"/>`,
    // 기지개 켜는 고양이 — 눈 감고 합장한 고양이와 잎
    balance: `<path d="M158 74Q178 62 180 40Q158 46 158 74Z" fill="#5F9C7D"/><path d="M40 96Q20 88 18 66Q40 70 40 96Z" fill="#5F9C7D"/>
      <path d="M46 200Q48 162 100 158Q152 162 154 200Z" fill="#F0B27A"/>
      <path d="M60 96L64 42L100 74Z" fill="#F0B27A"/><path d="M69 84L71 58L89 74Z" fill="#F7C9C0"/>
      <path d="M140 96L136 42L100 74Z" fill="#F0B27A"/><path d="M131 84L129 58L111 74Z" fill="#F7C9C0"/>
      <ellipse cx="100" cy="106" rx="52" ry="47" fill="#F0B27A"/>
      <path d="M100 62V78M87 64L90 78M113 64L110 78" stroke="#D98F4E" stroke-width="5" stroke-linecap="round"/>
      <circle cx="90" cy="126" r="12" fill="#FFF6EA"/><circle cx="110" cy="126" r="12" fill="#FFF6EA"/>
      <path d="M95 116H105L100 123Z" fill="#E98C86"/>
      <path d="M100 123Q97 131 90 129M100 123Q103 131 110 129" stroke="#2A211C" stroke-width="2.800" fill="none" stroke-linecap="round"/>
      <path d="M72 106Q81 97 90 106M110 106Q119 97 128 106" stroke="#2A211C" stroke-width="4" fill="none" stroke-linecap="round"/>
      <path d="M58 118H36M58 126L38 134M142 118H164M142 126L162 134" stroke="#B8793F" stroke-width="2.500" stroke-linecap="round"/>
      ${blush(70, 130, 120)}
      <path d="M99 160Q84 162 84 182Q86 198 99 198Z" fill="#FFF6EA"/><path d="M101 160Q116 162 116 182Q114 198 101 198Z" fill="#FFF6EA"/>
      <path d="M90 168V174M95 166V172M105 166V172M110 168V174" stroke="#E0B58A" stroke-width="2.500" stroke-linecap="round"/>`,
    // 느긋한 거북이 — 모자 쓰고 걷는 거북이
    walker: `<circle cx="38" cy="50" r="15" fill="#F2D27A"/>
      <path d="M12 178H188" stroke="#3F4C1F" stroke-width="5" stroke-linecap="round" opacity=".3"/>
      <path d="M22 148L38 138L38 158Z" fill="#9CC07A"/>
      <rect x="52" y="148" width="24" height="30" rx="10" fill="#9CC07A" transform="rotate(14 64 163)"/><rect x="112" y="148" width="24" height="30" rx="10" fill="#9CC07A" transform="rotate(-14 124 163)"/>
      <path d="M138 150Q138 120 156 112L170 140Q160 156 138 150Z" fill="#9CC07A"/>
      <path d="M32 150Q36 82 94 82Q152 82 156 150Z" fill="#5E8C4A"/>
      <ellipse cx="94" cy="112" rx="20" ry="16" fill="#8DB56F"/><ellipse cx="58" cy="130" rx="13" ry="11" fill="#8DB56F"/><ellipse cx="130" cy="130" rx="13" ry="11" fill="#8DB56F"/>
      <rect x="26" y="144" width="136" height="13" rx="6.500" fill="#3F6B33"/>
      <circle cx="166" cy="112" r="21" fill="#9CC07A"/>
      ${eye(172, 108, .9)}<ellipse cx="160" cy="120" rx="6" ry="4" fill="#F29C8E" opacity=".55"/>
      <path d="M166 122Q174 128 182 121" stroke="#2A211C" stroke-width="3" fill="none" stroke-linecap="round"/>
      <ellipse cx="164" cy="93" rx="25" ry="6" fill="#D9A441"/><path d="M148 92Q150 72 166 72Q180 72 182 92Z" fill="#E9BD5C"/><path d="M149 89H181" stroke="#C1793C" stroke-width="4"/>`,
    // 틈새의 다람쥐 — 초시계를 안은 다람쥐
    quick: `<path d="M128 194C182 190 190 124 158 100C138 86 116 104 128 122" stroke="#C9753B" stroke-width="36" fill="none" stroke-linecap="round"/>
      <path d="M128 194C182 190 190 124 158 100C138 86 116 104 128 122" stroke="#EDB07A" stroke-width="12" fill="none" stroke-linecap="round"/>
      <ellipse cx="96" cy="180" rx="36" ry="30" fill="#D98848"/>
      <path d="M62 78Q56 44 78 54Q86 64 80 80Z" fill="#C9753B"/><path d="M130 78Q136 44 114 54Q106 64 112 80Z" fill="#C9753B"/>
      <circle cx="96" cy="102" r="45" fill="#D98848"/>
      <ellipse cx="96" cy="120" rx="31" ry="23" fill="#FBE3C4"/>
      <ellipse cx="96" cy="111" rx="5.500" ry="4.200" fill="#3B2418"/>
      <path d="M96 115V121" stroke="#3B2418" stroke-width="2.800" stroke-linecap="round"/><rect x="91" y="121" width="10" height="9" rx="2.500" fill="#fff" stroke="#E6C9A6" stroke-width="1.500"/>
      ${eye(79, 98, 1.1)}${eye(113, 98, 1.1)}${blush(68, 124, 116)}
      <path d="M96 146V139M88 139H104" stroke="#7A4E10" stroke-width="6" stroke-linecap="round"/>
      <circle cx="96" cy="170" r="22" fill="#FFFDF7" stroke="#7A4E10" stroke-width="6"/>
      <path d="M96 170V156M96 170L106 176" stroke="#D9653B" stroke-width="5" stroke-linecap="round"/>
      <circle cx="70" cy="172" r="10" fill="#C9753B"/><circle cx="122" cy="172" r="10" fill="#C9753B"/>`,
  };

  const has = id => Object.prototype.hasOwnProperty.call(BODY, id);

  /* 유형 id → <svg> 문자열. 모르는 id 면 빈 문자열(그림 없이도 화면은 그대로 나온다). */
  function svg(id, size = 160, label = ''){
    if (!has(id)) return '';
    const clip = `sa-${id}`;
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" width="${size}" height="${size}" role="img" aria-label="${label}"><defs><clipPath id="${clip}"><rect width="200" height="200" rx="46"/></clipPath></defs><g clip-path="url(#${clip})"><rect width="200" height="200" fill="${TONE[id][0]}"/>${BODY[id]}</g></svg>`;
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
